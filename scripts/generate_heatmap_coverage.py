#!/usr/bin/env python3
"""Generate deterministic demo heatmap coverage for every kecamatan.

The project currently has administrative boundaries but no scored grid cells in
NTB or Central Kalimantan.  This workflow creates a *clearly labelled demo*
Tier-1 coverage dataset: each selected kecamatan receives at least four cell
centroids inside its own GADM polygon.  It is idempotent with respect to
coverage: existing cells are retained and only missing cells are inserted.

It is not a replacement for a production RF/Ookla/GEE scoring pipeline.  The
synthetic scores are deterministic so map demos and spatial-filtering tests
remain reproducible until that pipeline is available.

Usage:
  python scripts/generate_heatmap_coverage.py --dry-run
  python scripts/generate_heatmap_coverage.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from shapely.geometry import Point, shape
from supabase import create_client


REGIONS = ("ntt", "ntb", "central_kalimantan")
MODEL_VERSION = "coverage-demo-v1"
RESOLUTION_M = 100
MIN_CELLS_PER_KECAMATAN = 4


def stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def coverage_attributes(kecamatan_id: str, ordinal: int) -> tuple[float, str, list[dict[str, Any]]]:
    """Return a deterministic score with every heatmap tier represented."""
    rng = random.Random(stable_seed(f"{kecamatan_id}:{ordinal}:coverage"))
    tier = ordinal % 3
    if tier == 0:
        score = round(rng.uniform(18, 39), 1)  # explicit coverage gap
        confidence = "Low"
    elif tier == 1:
        score = round(rng.uniform(40, 69), 1)
        confidence = "Med"
    else:
        score = round(rng.uniform(70, 92), 1)
        confidence = "High"
    shap = [
        {"feature_name": "Distance to BTS", "value": round(rng.uniform(0.15, 0.50), 3), "direction": "negative"},
        {"feature_name": "Terrain accessibility", "value": round(rng.uniform(0.10, 0.35), 3), "direction": "positive"},
        {"feature_name": "Population proximity", "value": round(rng.uniform(0.08, 0.30), 3), "direction": "positive"},
    ]
    return score, confidence, shap


def points_inside_boundary(boundary: dict[str, Any], count: int, seed: int) -> list[Point]:
    """Produce unique deterministic points within Polygon or MultiPolygon."""
    geometry = shape(boundary)
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("boundary is empty or invalid")

    points = [geometry.representative_point()]
    min_x, min_y, max_x, max_y = geometry.bounds
    rng = random.Random(seed)
    attempts = 0
    while len(points) < count and attempts < 10_000:
        attempts += 1
        candidate = Point(rng.uniform(min_x, max_x), rng.uniform(min_y, max_y))
        if geometry.contains(candidate) and all(candidate.distance(existing) > 1e-8 for existing in points):
            points.append(candidate)
    if len(points) != count:
        raise ValueError(f"could not place {count} distinct points in boundary after {attempts} attempts")
    return points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--min-cells", type=int, default=MIN_CELLS_PER_KECAMATAN)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.min_cells < 1:
        parser.error("--min-cells must be at least 1")

    load_dotenv()
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY are required.", file=sys.stderr)
        return 2
    client = create_client(url, key)

    boundaries = client.table("admin_boundaries").select(
        "kecamatan_id,kecamatan_name,region_id,boundary_geojson"
    ).in_("region_id", args.regions).execute().data or []
    if not boundaries:
        print("No administrative boundaries found for selected regions.", file=sys.stderr)
        return 1

    cells = client.table("grid_cells").select("region_id,lat,lon").in_("region_id", args.regions).execute().data or []
    cells_by_region: dict[str, list[Point]] = defaultdict(list)
    for cell in cells:
        cells_by_region[cell["region_id"]].append(Point(cell["lon"], cell["lat"]))

    planned: list[dict[str, Any]] = []
    uncovered: list[str] = []
    summary: dict[str, tuple[int, int]] = {}
    for boundary in sorted(boundaries, key=lambda row: (row["region_id"], row["kecamatan_name"])):
        try:
            geometry = shape(boundary["boundary_geojson"])
            existing = sum(geometry.covers(cell) for cell in cells_by_region[boundary["region_id"]])
            missing = max(0, args.min_cells - existing)
            if missing:
                uncovered.append(f"{boundary['region_id']}/{boundary['kecamatan_name']} (+{missing})")
                for ordinal, generated in enumerate(points_inside_boundary(boundary["boundary_geojson"], missing, stable_seed(boundary["kecamatan_id"])), start=existing):
                    score, confidence, shap = coverage_attributes(boundary["kecamatan_id"], ordinal)
                    planned.append({
                        "cell_id": str(uuid.uuid4()), "region_id": boundary["region_id"],
                        "lat": round(generated.y, 7), "lon": round(generated.x, 7),
                        "resolution_m": RESOLUTION_M, "coverage_score": score,
                        "confidence_tag": confidence, "tier_used": "1", "shap_top3": shap,
                        "model_version": MODEL_VERSION,
                    })
        except Exception as exc:  # preserve a complete, actionable report
            print(f"Invalid boundary {boundary['region_id']}/{boundary['kecamatan_name']}: {exc}", file=sys.stderr)
            return 1

    for region in args.regions:
        total = sum(1 for row in boundaries if row["region_id"] == region)
        additions = sum(1 for row in planned if row["region_id"] == region)
        summary[region] = (total, additions)

    print("Heatmap coverage plan")
    for region, (districts, additions) in summary.items():
        print(f"  {region}: {districts} kecamatan, {additions} cells to insert")
    print(f"  Total: {len(planned)} new cells; minimum {args.min_cells} per kecamatan")
    if uncovered:
        print("  Districts receiving cells: " + ", ".join(uncovered))
    if args.dry_run:
        print("Dry run only; no database changes made.")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    client.table("model_artifacts").upsert({
        "version_id": MODEL_VERSION, "tier": "1", "algorithm": "Deterministic demo coverage baseline",
        "training_run_id": run_id, "artifact_path": "/demo/model_artifacts/coverage-demo-v1", "created_at": now,
    }).execute()
    client.table("scoring_runs").insert({
        "run_id": run_id, "model_version": MODEL_VERSION, "tier": "1", "resolution_m": RESOLUTION_M,
        "region_kecamatans": [row["kecamatan_id"] for row in boundaries], "input_checksums": {},
        "candidate_count": 0, "timestamp": now, "retained_for_months": 12,
    }).execute()
    for row in planned:
        row["scoring_run_id"] = run_id
    if planned:
        client.table("grid_cells").insert(planned).execute()
    print(f"Inserted {len(planned)} cells with scoring run {run_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
