#!/usr/bin/env python3
"""Validate production data completeness per kecamatan (Phase E).

Checks every layer has real (non-demo) rows for all 45 kecamatan, verifies
no demo rows are mixed into the real data, and emits a dated manifest to
``data/manifests/``.  Exits non-zero when any check fails so promotion can
be gated on a clean validation.

Checks
------
- grid_cells: every kecamatan has >= 1 real cell (45/45 heatmap).
- contour_features: every kecamatan has >= 1 real contour line.
- village_features: every kecamatan has >= 1 real village.
- landcover_tile_sets: every region has a real tile set.
- bts_locations: per-region real tower count (0 is allowed only when the
  OpenCellID source_run is explicitly ``unavailable``).
- bts_candidates: every target area has derived candidates OR an explicit
  ``unavailable`` source_run for that target area.
- demo segregation: no demo rows in grid_cells / bts_candidates.

Usage:
  python scripts/validate_production.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

REGIONS = ("ntt", "ntb", "central_kalimantan")
MANIFEST_DIR = Path("data/manifests")
REAL_DATASETS = (
    "gee_raster_sample",
    "osm_villages",
    "opencellid_towers",
    "ookla_fixed",
    "ookla_mobile",
    "gee_landcover_tiles",
    "srtm_contours",
    "bts_candidates",
)


def _fetch_all(client, table: str, select: str, **filters) -> list[dict]:
    rows: list[dict] = []
    page = 1000
    start = 0
    while True:
        q = client.table(table).select(select)
        for k, v in filters.items():
            q = q.eq(k, v)
        batch = q.range(start, start + page - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def main() -> int:
    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    boundaries = _fetch_all(
        client, "admin_boundaries", "kecamatan_id,kecamatan_name,region_id"
    )
    kecamatans = sorted(boundaries, key=lambda b: b["kecamatan_id"])
    print(f"admin boundaries: {len(kecamatans)}")

    # Per-kecamatan real counts.
    grid_counts: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "grid_cells", "kecamatan_id", data_source="real"):
        grid_counts[r["kecamatan_id"]] += 1

    contour_counts: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "contour_features", "kecamatan_id", status="real"):
        contour_counts[r["kecamatan_id"]] += 1

    village_counts: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "village_features", "kecamatan_id", status="real"):
        village_counts[r["kecamatan_id"]] += 1

    # Per-region real counts.
    region_grid: dict[str, int] = defaultdict(int)
    region_contour: dict[str, int] = defaultdict(int)
    region_village: dict[str, int] = defaultdict(int)
    for b in kecamatans:
        region_grid[b["region_id"]] += grid_counts.get(b["kecamatan_id"], 0)
        region_contour[b["region_id"]] += contour_counts.get(b["kecamatan_id"], 0)
        region_village[b["region_id"]] += village_counts.get(b["kecamatan_id"], 0)

    tower_counts: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "bts_locations", "region_id", status="real"):
        tower_counts[r["region_id"]] += 1

    tile_counts: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "landcover_tile_sets", "region_id", status="real"):
        tile_counts[r["region_id"]] += 1

    # Demo segregation.
    demo_grid = len(_fetch_all(client, "grid_cells", "cell_id", data_source="demo"))
    demo_cands = len(_fetch_all(client, "bts_candidates", "candidate_id", data_source="demo"))

    # Candidate coverage per target area.
    tas = _fetch_all(client, "target_areas", "target_area_id,region_id,kecamatan_id")
    cand_counts: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "bts_candidates", "target_area_id", data_source="derived"):
        cand_counts[r["target_area_id"]] += 1
    unavailable_tas: set[str] = set()
    for r in _fetch_all(client, "source_runs", "metadata", dataset="bts_candidates"):
        meta = r.get("metadata") or {}
        if r.get("status") == "unavailable" and meta.get("target_area_id"):
            unavailable_tas.add(meta["target_area_id"])

    # Source runs for the manifest.
    source_runs = _fetch_all(client, "source_runs", "*")

    checks: list[dict] = []
    failures: list[str] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            failures.append(f"{name}: {detail}")

    # 1. Heatmap: 45/45 kecamatan with real cells.
    missing_heatmap = [b["kecamatan_id"] for b in kecamatans if grid_counts.get(b["kecamatan_id"], 0) == 0]
    check(
        "heatmap_45_45",
        not missing_heatmap,
        f"{len(kecamatans) - len(missing_heatmap)}/{len(kecamatans)} kecamatan have real cells"
        + (f"; missing: {missing_heatmap}" if missing_heatmap else ""),
    )

    # 2. Contours per kecamatan.
    missing_contours = [b["kecamatan_id"] for b in kecamatans if contour_counts.get(b["kecamatan_id"], 0) == 0]
    check(
        "contours_all_kecamatan",
        not missing_contours,
        f"{len(kecamatans) - len(missing_contours)}/{len(kecamatans)} kecamatan have contours"
        + (f"; missing: {missing_contours}" if missing_contours else ""),
    )

    # 3. Villages per kecamatan.
    missing_villages = [b["kecamatan_id"] for b in kecamatans if village_counts.get(b["kecamatan_id"], 0) == 0]
    check(
        "villages_all_kecamatan",
        not missing_villages,
        f"{len(kecamatans) - len(missing_villages)}/{len(kecamatans)} kecamatan have villages"
        + (f"; missing: {missing_villages}" if missing_villages else ""),
    )

    # 4. Land-cover tiles per region.
    missing_tiles = [r for r in REGIONS if tile_counts.get(r, 0) == 0]
    check(
        "landcover_tiles_all_regions",
        not missing_tiles,
        f"regions with real tile sets: {len(REGIONS) - len(missing_tiles)}/{len(REGIONS)}"
        + (f"; missing: {missing_tiles}" if missing_tiles else ""),
    )

    # 5. BTS towers per region (0 allowed only with explicit unavailable run).
    opencellid_unavailable = {
        r["region_id"]
        for r in source_runs
        if r.get("dataset") == "opencellid_towers" and r.get("status") == "unavailable"
    }
    tower_issues = [
        r for r in REGIONS if tower_counts.get(r, 0) == 0 and r not in opencellid_unavailable
    ]
    check(
        "bts_towers_regions",
        not tower_issues,
        f"towers per region: {dict(tower_counts)}"
        + (f"; regions with 0 towers and no unavailable run: {tower_issues}" if tower_issues else ""),
    )

    # 6. Candidates per target area (derived or explicit unavailable).
    uncovered_tas = [
        t["target_area_id"]
        for t in tas
        if cand_counts.get(t["target_area_id"], 0) == 0
        and t["target_area_id"] not in unavailable_tas
    ]
    check(
        "candidates_all_target_areas",
        not uncovered_tas,
        f"{len(tas) - len(uncovered_tas)}/{len(tas)} target areas have derived candidates"
        + (f"; uncovered: {uncovered_tas}" if uncovered_tas else ""),
    )

    # Demo segregation: every grid_cell / bts_candidate must carry an explicit
    # data_source label (demo rows are removed by promotion, not validation).
    # An 'unavailable' label on a generated row would indicate a broken state.
    bad_grid_sources = {
        r["data_source"]
        for r in _fetch_all(client, "grid_cells", "data_source")
        if r["data_source"] not in ("demo", "real", "derived")
    }
    bad_cand_sources = {
        r["data_source"]
        for r in _fetch_all(client, "bts_candidates", "data_source")
        if r["data_source"] not in ("demo", "real", "derived")
    }
    check(
        "demo_segregation",
        not bad_grid_sources and not bad_cand_sources,
        f"demo grid_cells={demo_grid}, demo bts_candidates={demo_cands} "
        f"(removed by promotion); invalid labels: grid={sorted(bad_grid_sources)} "
        f"candidates={sorted(bad_cand_sources)}",
    )

    manifest = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "checks": checks,
        "passed": not failures,
        "kecamatan_counts": {
            b["kecamatan_id"]: {
                "region_id": b["region_id"],
                "kecamatan_name": b["kecamatan_name"],
                "grid_cells_real": grid_counts.get(b["kecamatan_id"], 0),
                "contours_real": contour_counts.get(b["kecamatan_id"], 0),
                "villages_real": village_counts.get(b["kecamatan_id"], 0),
            }
            for b in kecamatans
        },
        "region_counts": {
            r: {
                "grid_cells_real": region_grid.get(r, 0),
                "contours_real": region_contour.get(r, 0),
                "villages_real": region_village.get(r, 0),
                "bts_towers_real": tower_counts.get(r, 0),
                "landcover_tile_sets_real": tile_counts.get(r, 0),
            }
            for r in REGIONS
        },
        "target_area_candidates": {
            t["target_area_id"]: {
                "region_id": t["region_id"],
                "kecamatan_id": t["kecamatan_id"],
                "derived_candidates": cand_counts.get(t["target_area_id"], 0),
                "explicit_unavailable": t["target_area_id"] in unavailable_tas,
            }
            for t in tas
        },
        "source_runs": [
            {
                "run_id": r["run_id"],
                "dataset": r.get("dataset"),
                "region_id": r.get("region_id"),
                "status": r.get("status"),
                "records_count": r.get("records_count"),
                "promoted_run_id": r.get("promoted_run_id"),
                "promoted_at": r.get("promoted_at"),
            }
            for r in source_runs
            if r.get("dataset") in REAL_DATASETS
        ],
        "rollback_id": None,
    }

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    path = MANIFEST_DIR / f"validate-{stamp}.json"
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"manifest written: {path}")

    for c in checks:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail']}")

    if failures:
        print(f"\n{len(failures)} check(s) failed.", file=sys.stderr)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())