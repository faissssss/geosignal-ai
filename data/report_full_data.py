#!/usr/bin/env python3
"""Full data report: every layer per province and per kecamatan (read-only).

Outputs:
  1. Per-province summary table (all layers).
  2. Per-kecamatan table (heatmap cells, contours, villages, candidates, towers).
  3. Per-layer detail with source provenance.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

from dotenv import load_dotenv
from supabase import create_client

REGIONS = ("ntt", "ntb", "central_kalimantan")
REGION_LABELS = {"ntt": "NTT", "ntb": "NTB", "central_kalimantan": "Central Kalimantan"}


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

    boundaries = _fetch_all(client, "admin_boundaries", "kecamatan_id,kecamatan_name,region_id")
    by_region: dict[str, list[dict]] = defaultdict(list)
    for b in boundaries:
        by_region[b["region_id"]].append(b)

    # ── Per-region layer counts ──────────────────────────────────────────
    region_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in _fetch_all(client, "grid_cells", "region_id", data_source="real"):
        region_counts[r["region_id"]]["heatmap_cells"] += 1
    for r in _fetch_all(client, "contour_features", "region_id", status="real"):
        region_counts[r["region_id"]]["contours"] += 1
    for r in _fetch_all(client, "village_features", "region_id", status="real"):
        region_counts[r["region_id"]]["villages"] += 1
    for r in _fetch_all(client, "bts_locations", "region_id", status="real"):
        region_counts[r["region_id"]]["bts_towers"] += 1
    for r in _fetch_all(client, "landcover_tile_sets", "region_id", status="real"):
        region_counts[r["region_id"]]["landcover_tiles"] += 1
    for r in _fetch_all(client, "bts_candidates", "region_id", data_source="derived"):
        region_counts[r["region_id"]]["candidates"] += 1
    for r in _fetch_all(client, "whatif_grid", "region_id"):
        region_counts[r["region_id"]]["whatif"] += 1
    for r in _fetch_all(client, "los_results", "region_id"):
        region_counts[r["region_id"]]["los"] += 1
    for r in _fetch_all(client, "source_runs", "region_id"):
        region_counts[r["region_id"]]["source_runs"] += 1

    # ── Per-kecamatan counts ─────────────────────────────────────────────
    kec_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in _fetch_all(client, "grid_cells", "kecamatan_id", data_source="real"):
        kec_counts[r["kecamatan_id"]]["cells"] += 1
    for r in _fetch_all(client, "contour_features", "kecamatan_id", status="real"):
        kec_counts[r["kecamatan_id"]]["contours"] += 1
    for r in _fetch_all(client, "village_features", "kecamatan_id", status="real"):
        kec_counts[r["kecamatan_id"]]["villages"] += 1

    tas = _fetch_all(client, "target_areas", "target_area_id,region_id,kecamatan_id")
    cand_by_ta: dict[str, int] = defaultdict(int)
    for r in _fetch_all(client, "bts_candidates", "target_area_id", data_source="derived"):
        cand_by_ta[r["target_area_id"]] += 1
    for t in tas:
        kid = t.get("kecamatan_id")
        if kid:
            kec_counts[kid]["candidates"] += cand_by_ta.get(t["target_area_id"], 0)

    # ── 1. Per-province summary ──────────────────────────────────────────
    print("\n" + "=" * 78)
    print("PER-PROVINCE DATA SUMMARY (all layers)")
    print("=" * 78)
    layers = [
        ("heatmap_cells", "Heatmap cells"),
        ("contours", "Contours"),
        ("villages", "Villages"),
        ("bts_towers", "BTS towers"),
        ("landcover_tiles", "Landcover tile sets"),
        ("candidates", "BTS candidates"),
        ("whatif", "What-if rows"),
        ("los", "LOS results"),
        ("source_runs", "Source runs"),
    ]
    hdr = f"{'Layer':<22}" + "".join(f"{REGION_LABELS[r]:>22}" for r in REGIONS)
    print(hdr)
    print("-" * len(hdr))
    for key, label in layers:
        row = f"{label:<22}"
        for r in REGIONS:
            n = region_counts[r][key]
            row += f"{n:>22,}"
        print(row)

    # ── 2. Per-kecamatan table ───────────────────────────────────────────
    print("\n" + "=" * 78)
    print("PER-KECAMATAN DATA (45 kecamatan)")
    print("=" * 78)
    hdr2 = f"{'Kecamatan':<20} {'Province':<20} {'Cells':>8} {'Contours':>9} {'Villages':>9} {'Cands':>6}"
    print(hdr2)
    print("-" * len(hdr2))
    for r in REGIONS:
        for b in sorted(by_region.get(r, []), key=lambda x: x["kecamatan_id"]):
            kid = b["kecamatan_id"]
            print(
                f"{b['kecamatan_name']:<20} {REGION_LABELS[r]:<20} "
                f"{kec_counts[kid]['cells']:>8,} {kec_counts[kid]['contours']:>9,} "
                f"{kec_counts[kid]['villages']:>9,} {kec_counts[kid]['candidates']:>6,}"
            )

    # ── 3. Per-layer detail with provenance ──────────────────────────────
    print("\n" + "=" * 78)
    print("PER-LAYER DETAIL (source provenance)")
    print("=" * 78)

    print("\n-- BTS towers per province --")
    for r in REGIONS:
        rows = _fetch_all(client, "bts_locations", "region_id,source_run_id", status="real")
        n = sum(1 for x in rows if x["region_id"] == r)
        print(f"  {REGION_LABELS[r]:<20} {n:>6,} towers")

    print("\n-- Landcover tile sets per province --")
    for r in REGIONS:
        rows = _fetch_all(client, "landcover_tile_sets", "region_id,status", status="real")
        n = sum(1 for x in rows if x["region_id"] == r)
        print(f"  {REGION_LABELS[r]:<20} {n} tile set(s)")

    print("\n-- Source runs per province (by dataset/status) --")
    runs = _fetch_all(client, "source_runs", "region_id,dataset,status")
    for r in REGIONS:
        print(f"  {REGION_LABELS[r]}:")
        for ds in sorted({x["dataset"] for x in runs if x["region_id"] == r}):
            ok = sum(1 for x in runs if x["region_id"] == r and x["dataset"] == ds and x["status"] == "ok")
            un = sum(1 for x in runs if x["region_id"] == r and x["dataset"] == ds and x["status"] == "unavailable")
            print(f"    {ds:<22} ok={ok} unavailable={un}")

    # ── 4. Empty-data check ──────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("EMPTY-DATA CHECK")
    print("=" * 78)
    problems = []
    for r in REGIONS:
        for key, label in layers:
            if region_counts[r][key] == 0:
                problems.append(f"{REGION_LABELS[r]}/{label}")
    for b in boundaries:
        kid = b["kecamatan_id"]
        for key, label in (("cells", "cells"), ("contours", "contours"), ("villages", "villages")):
            if kec_counts[kid][key] == 0:
                problems.append(f"{b['kecamatan_name']}/{label}")
    if problems:
        print("EMPTY FOUND:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("No empty data in any province or kecamatan.")

    return 0


if __name__ == "__main__":
    sys.exit(main())