# GeoSignal AI — Full Data Report

**Generated:** 2026-08-11 (live Supabase database)
**Scope:** All 3 provinces, 45 kecamatan, all data layers
**Source:** `data/report_full_data.py` (regenerate with `python data/report_full_data.py`)

---

## 1. Per-Province Summary (all layers)

| Layer | NTT | NTB | Central Kalimantan | Total |
|---|---|---|---|---|
| Heatmap cells | 58,945 | 24,729 | 41,462 | 125,136 |
| Contours | 505 | 137 | 37,584 | 38,226 |
| Villages | 6,183 | 3,053 | 5,138 | 14,374 |
| BTS towers | 33 | 3,390 | 318 | 3,741 |
| Landcover tile sets | 1 | 1 | 1 | 3 |
| BTS candidates | 50 | 40 | 140 | 230 |
| What-if rows | 50 | 40 | 140 | 230 |
| LOS results | 2,494 | 4,158 | 30,718 | 37,370 |
| Source runs | 23 | 19 | 39 | 81 |

> **Note on LOS results:** after the 2026-08-11 storage fix, LOS is persisted only for
> the top-10 ranked candidates per target area (the frontend reads `bts_candidates`
> with `los_validated`, never `los_results`). This reduced the database from
> 1,205 MB to 113 MB, comfortably within the Supabase free-tier 500 MB limit.

---

## 2. Per-Kecamatan Data (45 kecamatan)

### NTT (21 kecamatan)

| Kecamatan | Cells | Contours | Villages | Candidates |
|---|---|---|---|---|
| Alor | 2,939 | 9 | 319 | 10 |
| Belu | 2,976 | 10 | 192 | 0 |
| Ende | 2,958 | 9 | 206 | 30 |
| FloresTimur | 2,963 | 9 | 536 | 10 |
| KotaKupang | 621 | 3 | 49 | 0 |
| Kupang | 2,995 | 12 | 177 | 0 |
| Lembata | 2,951 | 9 | 192 | 0 |
| Manggarai | 2,988 | 12 | 197 | 0 |
| ManggaraiBarat | 2,944 | 12 | 393 | 0 |
| ManggaraiTimur | 2,983 | 12 | 112 | 0 |
| Nagekeo | 2,998 | 11 | 90 | 0 |
| Ngada | 2,994 | 174 | 92 | 0 |
| RoteNdao | 2,986 | 166 | 90 | 0 |
| SabuRaijua | 1,843 | 2 | 63 | 0 |
| Sikka | 2,983 | 9 | 212 | 0 |
| SumbaBarat | 2,844 | 5 | 179 | 0 |
| SumbaBaratDaya | 2,996 | 5 | 730 | 0 |
| SumbaTengah | 2,999 | 5 | 78 | 0 |
| SumbaTimur | 2,992 | 7 | 326 | 0 |
| TimorTengahSelatan | 2,994 | 12 | 241 | 0 |
| TimorTengahUtara | 2,998 | 12 | 163 | 0 |

### NTB (10 kecamatan)

| Kecamatan | Cells | Contours | Villages | Candidates |
|---|---|---|---|---|
| Bima | 2,949 | 14 | 575 | 20 |
| Dompu | 2,964 | 14 | 337 | 10 |
| KotaBima | 841 | 8 | 100 | 0 |
| LombokBarat | 2,946 | 15 | 366 | 10 |
| LombokTengah | 2,947 | 19 | 571 | 0 |
| LombokTimur | 2,957 | 19 | 275 | 0 |
| LombokUtara | 2,949 | 19 | 170 | 0 |
| Mataram | 212 | 5 | 450 | 0 |
| Sumbawa | 2,985 | 14 | 198 | 0 |
| SumbawaBarat | 2,979 | 10 | 40 | 0 |

### Central Kalimantan (14 kecamatan)

| Kecamatan | Cells | Contours | Villages | Candidates |
|---|---|---|---|---|
| BaritoSelatan | 2,948 | 720 | 106 | 10 |
| BaritoTimur | 2,993 | 349 | 127 | 10 |
| BaritoUtara | 2,947 | 2,354 | 106 | 10 |
| GunungMas | 2,968 | 2,628 | 131 | 10 |
| Kapuas | 2,826 | 2,319 | 233 | 10 |
| Katingan | 2,959 | 6,252 | 163 | 10 |
| KotawaringinBarat | 2,993 | 1,056 | 100 | 10 |
| KotawaringinTimur | 2,970 | 1,511 | 190 | 10 |
| Lamandau | 2,984 | 2,256 | 90 | 10 |
| MurungRaya | 2,990 | 9,255 | 134 | 10 |
| PalangkaRaya | 2,962 | 203 | 30 | 10 |
| PulangPisau | 2,984 | 744 | 98 | 10 |
| Seruyan | 2,957 | 6,942 | 102 | 10 |
| Sukamara | 2,981 | 995 | 33 | 10 |

> **Candidates note:** candidates exist for the 23 target areas (Alor, Ende ×3,
> FloresTimur, Bima ×2, Dompu, LombokBarat, and all 14 CK kecamatan). Target areas
> are the operator-defined scopes where what-if analysis runs; every kecamatan has
> full map layers regardless.

---

## 3. Per-Layer Detail (source provenance)

### BTS towers (real, per province)

| Province | Towers |
|---|---|
| NTT | 33 |
| NTB | 3,390 |
| Central Kalimantan | 318 |
| **Total** | **3,741** |

### Landcover tile sets (real, per province)

| Province | Tile sets |
|---|---|
| NTT | 1 |
| NTB | 1 |
| Central Kalimantan | 1 |

### Source runs per province (dataset / ok / unavailable)

| Dataset | NTT | NTB | CK |
|---|---|---|---|
| bts_candidates | ok=10, unavail=2 | ok=8 | ok=17, unavail=11 |
| gee_landcover_tiles | ok=1 | ok=1 | ok=1 |
| gee_raster_sample | ok=2 | ok=2 | ok=2 |
| ookla_fixed | ok=1 | ok=1 | ok=1 |
| ookla_mobile | ok=1 | ok=1 | ok=1 |
| opencellid_towers | ok=2, unavail=1 | ok=2, unavail=1 | ok=2, unavail=1 |
| osm_villages | ok=1 | ok=1 | ok=1 |
| srtm_contours | ok=1, unavail=1 | ok=1, unavail=1 | ok=1, unavail=1 |

> `unavailable` runs are recorded honestly (OpenCellID API quota, SRTM retries,
> early CK candidate attempts) — no fabricated data is ever inserted.

---

## 4. Empty-Data Check

**Result: No empty data in any province or kecamatan.** ✅

- Heatmap cells: 45/45 kecamatan
- Contours: 45/45 kecamatan
- Villages: 45/45 kecamatan
- Landcover tile sets: 3/3 provinces
- BTS towers: 3/3 provinces
- BTS candidates: 23/23 target areas
- Demo segregation: 0 demo rows in grid_cells / bts_candidates

---

## 5. Validation Status

`scripts/validate_production.py` — **7/7 checks PASS** (manifest: `data/manifests/validate-2026-08-11.json`)

| Check | Result |
|---|---|
| heatmap_45_45 | PASS |
| contours_all_kecamatan | PASS |
| villages_all_kecamatan | PASS |
| landcover_tiles_all_regions | PASS |
| bts_towers_regions | PASS |
| candidates_all_target_areas | PASS |
| demo_segregation | PASS |

Frontend: **330/330 tests pass**; `/api/recommendations` returns live candidates for all 3 provinces.