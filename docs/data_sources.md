# GeoSignal AI — Data Sources

This document lists every external dataset used by the GeoSignal AI pipeline, with
source URLs, resolutions, licenses, and any registration or access notes.

---

## 1. SRTM Digital Elevation Model (DEM)

| Attribute | Detail |
|-----------|--------|
| **Source** | NASA / USGS via Google Earth Engine: `USGS/SRTMGL1_003` |
| **URL** | <https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003> |
| **Resolution** | 1 arc-second (~30 m at the equator) |
| **License** | Public Domain (U.S. Government Work) |
| **Notes** | Elevation in metres. Used for DEM-based line-of-sight (LOS) precomputation and `elevation_m` / `slope_deg` feature derivation. Indonesia elevation range: −11 m (coastal reclaimed land) to 4 884 m (Puncak Jaya). |

---

## 2. ESA WorldCover

| Attribute | Detail |
|-----------|--------|
| **Source** | European Space Agency via Google Earth Engine: `ESA/WorldCover/v200` |
| **URL** | <https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200> |
| **Resolution** | 10 m |
| **License** | CC BY 4.0 |
| **Notes** | Global land-cover map at 10 m resolution (2021 epoch). Provides `land_cover_class` integer codes (e.g., 10 = Tree cover, 20 = Shrubland, 40 = Cropland, 50 = Built-up). Used both as a scoring feature and as part of the joint deforestation-constraint check (`is_high_canopy`). |

---

## 3. OpenGeoAI Canopy Height

| Attribute | Detail |
|-----------|--------|
| **Source** | Meta / WRI High Resolution Canopy Height Maps via Google Earth Engine: `projects/meta-forest-monitoring-okw37vi/assets/CanopyHeight` |
| **URL** | <https://developers.google.com/earth-engine/datasets/catalog/projects_meta-forest-monitoring-okw37vi_assets_CanopyHeight> |
| **Resolution** | 1 m (resampled to analysis grid) |
| **License** | CC BY 4.0 |
| **Notes** | Global canopy height in metres derived from satellite imagery. Provides `canopy_height_m`. Used jointly with `land_cover_class` in `is_high_canopy()` — a cell is excluded only when BOTH the land-cover class is in `{10, 20}` AND canopy height ≥ 15 m. Valid range: 0–100 m; values outside this range are flagged by the attribute-range validation step. |

---

## 4. OpenCellID

| Attribute | Detail |
|-----------|--------|
| **Source** | Unwired Labs / OpenCellID |
| **URL** | <https://opencellid.org> |
| **License** | CC BY-SA 4.0 |
| **Registration required** | Yes — an API key is required to download bulk cell tower data. Register at <https://opencellid.org/register.php>. Set the key in `OPENCELLID_API_KEY` in your `.env` file. |
| **Notes** | Provides existing BTS tower locations for `distance_to_bts_m` feature computation and Confidence_Tagger proximity thresholds. Data sparsity in 3T regions is a known risk (see Ethical Risk Register entry `opencellid_sparsity_misread`). Absence of a record must NOT be treated as confirmed zero coverage. |

---

## 5. OpenStreetMap (OSM)

| Attribute | Detail |
|-----------|--------|
| **Source** | OpenStreetMap contributors |
| **URL** | <https://www.openstreetmap.org> / Overpass API: <https://overpass-api.de> |
| **License** | Open Database License (ODbL) 1.0 — <https://opendatacommons.org/licenses/odbl/> |
| **Notes** | Used for two features: (1) `road_distance_m` — nearest OSM road segment per grid cell; (2) `facility_proximity_m` — nearest OSM POI tagged as school, clinic, government office, or emergency service. Attribution to "© OpenStreetMap contributors" is required in any published output. |

---

## 6. WorldPop Population Density

| Attribute | Detail |
|-----------|--------|
| **Source** | WorldPop / University of Southampton via Google Earth Engine: `WorldPop/GP/100m/pop` |
| **URL** | <https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop> |
| **Resolution** | 100 m |
| **License** | CC BY 4.0 |
| **Notes** | Gridded population count estimates. Provides `population_density_per_km2`. Population data is referenced only through the aggregated raster — never disaggregated to individual records (see PII Absence Invariant, Property 26). Values > 1 000 000 per km² are flagged as anomalous by the attribute-range validation step. |

---

## 7. Ookla Open Data (Speedtest Intelligence)

| Attribute | Detail |
|-----------|--------|
| **Source** | Ookla / Speedtest |
| **GitHub repository** | <https://github.com/teamookla/ookla-open-data> |
| **License** | [Ookla Open Data License](https://github.com/teamookla/ookla-open-data/blob/master/LICENSE.md) — attribution required; not for commercial redistribution |
| **Tile format** | Parquet files keyed by Bing Maps quadkey at zoom level 16 (~610 m cell side); columns include `avg_d_kbps`, `avg_u_kbps`, `avg_lat_ms`, `tests`, `devices` |
| **Notes** | Ookla tiles are the **Tier 2 training label only** — they are NEVER a scoring input feature (`CONSOLIDATED_FEATURES` does not include any Ookla field). The absence of Ookla tiles for a kecamatan triggers automatic Tier 1 (AHP) routing via `select_tier`. |

### Ookla Q1 2024 Indonesia Tiles — Download and Checksum Instructions

The MVP analysis uses **Q1 2024 fixed-broadband and mobile tiles** covering NTT Province,
NTB Province, and Central Kalimantan Province:

1. Navigate to the Ookla Open Data GitHub repository:
   <https://github.com/teamookla/ookla-open-data>

2. Follow the README instructions to identify and download the Q1 2024 Parquet tiles
   for the quadkeys covering the three target provinces. Tile URLs follow the pattern
   documented in the repository.

3. After download, compute and record SHA-256 checksums for each tile file:
   ```bash
   sha256sum ookla-fixed-2024-01-01_performance_fixed_z16.parquet > checksums.sha256
   sha256sum ookla-mobile-2024-01-01_performance_mobile_z16.parquet >> checksums.sha256
   ```

4. Store the checksum file alongside the raw tiles and reference it in the
   `DataQualityReport.dataset_checksums` dict under keys `ookla_fixed` and `ookla_mobile`.

5. Set `OOKLA_FIXED_TILE_URL` and `OOKLA_MOBILE_TILE_URL` in your `.env` file to the
   exact download URLs obtained from step 2.

---

## 8. Google Earth Engine Access

| Attribute | Detail |
|-----------|--------|
| **Registration URL** | <https://code.earthengine.google.com/register> |
| **Approval time** | 24–48 hours (non-commercial/research projects); longer for new accounts |

> **⚠️ Register GEE access on Day 1 of the project.**
> GEE approval is required before Tasks 3 onward (all pipeline tasks) can run.
> Do not defer registration. Set `GEE_PROJECT_ID`, `GEE_SERVICE_ACCOUNT_EMAIL`,
> and `GEE_SERVICE_ACCOUNT_JSON_PATH` in your `.env` file once approved.

---

## Attribution Summary

| Dataset | Required Attribution |
|---------|---------------------|
| SRTM DEM | "SRTM data courtesy of the U.S. Geological Survey" |
| ESA WorldCover | "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium" |
| OpenGeoAI Canopy Height | "© Meta / WRI High Resolution Canopy Height Maps, CC BY 4.0" |
| OpenStreetMap | "© OpenStreetMap contributors, ODbL 1.0" |
| WorldPop | "WorldPop (www.worldpop.org — School of Geography and Environmental Science, University of Southampton), CC BY 4.0" |
| Ookla Open Data | "Speedtest by Ookla Global Fixed and Mobile Network Performance Map. Derived from Ookla® Speedtest Intelligence® Data [Q1 2024]." |
