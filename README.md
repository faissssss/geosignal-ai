# GeoSignal AI

**GeoAI-Assisted Coverage Gap Detection & BTS Placement Recommendation for Indonesia's 3T Regions**

> A decision-support system that helps telecom planners identify where people *can't actually receive a usable signal* — and recommends exactly where to build next.

---

## The Problem

Indonesia has over 17,000 islands, vast mountain ranges, dense forests, and highly remote communities. As of April 2026, **3,029 villages** remain classified as blank-spots with zero cellular connectivity. A village may look close to a tower on a 2D map, but mountains, valleys, and forest canopy can completely block usable signal.

GeoSignal AI answers the real planning question: **"Can people in this location actually receive a usable signal?"**

---

## MVP Demo Region

**Primary:** NTT Province — ~700 remaining blank-spot points across the province, a 2026 "Kampung Internet" priority area.

**Secondary Validation:**
- NTB Province — arid/elevation terrain profile
- Central Kalimantan Province — dense forest canopy terrain profile

---

## Key Features

| Feature | Description |
|---|---|
| **Coverage Gap Heatmap** | Dynamic heatmap (🟢 Good / 🟡 Moderate / 🔴 Poor) factoring in actual terrain, not just tower radius circles |
| **BTS Placement Recommendations** | Ranked candidate coordinates scored using 8 geospatial features via BallTree-indexed candidate search |
| **Before/After Simulation** | Instantly preview how a new BTS changes coverage metrics (e.g., 48% → 74%) |
| **Drag-and-Drop Placement** | Drop a marker anywhere on the map and see a live Coverage Score + terrain-deformed coverage ring |
| **Confidence Tagging** | Every output tagged Low / Med / High based on proximity to OpenCellID and Ookla data |
| **SHAP Explainability** | Every recommendation shows its top 3 contributing factors in plain language |

---

## Technical Architecture

```
[SRTM DEM] + [ESA WorldCover] + [OpenGeoAI Canopy] + [OpenCellID] + [WorldPop] + [Ookla]
                                          ↓
                            Step 0: GEE Data Fusion & QA
                                          ↓
                   ┌──────────────────────────────────────┐
                   │  Tier 1: AHP (cold-start, no Ookla)  │
                   │  Tier 2: XGBoost/LightGBM (+ Ookla)  │
                   └──────────────────────────────────────┘
                                          ↓
                          Coverage Score per grid cell (0–100)
                                          ↓
                    BallTree Candidate Search → Priority Ranking
                                          ↓
                       DEM Line-of-Sight Validation (precomputed)
                                          ↓
                 BTS Candidates + Confidence Tags + SHAP Explanations
                                          ↓
                   Next.js / MapLibre Interactive Map (Supabase backend)
```

### Stack

| Layer | Technology |
|---|---|
| Geospatial fusion | Google Earth Engine |
| Modelling | Python 3.11+, XGBoost, LightGBM, scikit-learn (BallTree), SHAP |
| Backend API | Next.js API routes |
| Database / Storage | Supabase (PostgreSQL + Storage) |
| Frontend map | Next.js + MapLibre GL JS |
| Containerisation | Docker (per-province pipeline steps) |
| Phase 3 scale-out | Spark / Dask via abstracted model adapter |

---

## Modeling Approach

### Two-Tier Design

- **Tier 1 (AHP):** Analytic Hierarchy Process for regions with zero Ookla ground-truth data. Weighted scoring across 8 geospatial features.
- **Tier 2 (XGBoost/LightGBM):** Trained against Ookla Open Data signal quality tiles where available.

### Consolidated Feature Set (8 inputs)

| Feature | Source | Resolution |
|---|---|---|
| Elevation | SRTM DEM | 30m |
| Slope | SRTM DEM | 30m |
| Land Cover Class | ESA WorldCover | 10m |
| Canopy Height | OpenGeoAI | 30m |
| Distance to BTS | OpenCellID | — |
| Road Distance | OSM | Vector |
| Population Density | WorldPop | 100m |
| Public Facility Proximity | OSM POI | — |

> Ookla signal quality is **not** a scoring input — it is the Tier 2 training label only, to prevent target leakage.

### Validation

Spatially-blocked cross-validation by kecamatan (sub-district) — entire geographic blocks held out, never a random point split. This prevents spatial autocorrelation leakage and ensures reported accuracy reflects genuine generalisability.

---

## Ethical Design

| Risk | Mitigation |
|---|---|
| Digital exclusion of low-population clusters | Explicit equity weighting via facility proximity + population density in AHP |
| Deforestation from recommended sites | High-canopy forest sites excluded by default (joint land-cover + canopy-height check) |
| OpenCellID absence misread as "confirmed no coverage" | Absence → Low-confidence unknown, not red/poor |
| Low-confidence scores driving real funding decisions | UI gates Low-confidence actions behind explicit acknowledgement modal |
| MAUP resampling mismatch | Coverage Scores output at ≥2 grid resolutions before final selection |

All outputs are explicitly framed as **GeoAI-assisted estimates** and decision-support, not authoritative signal predictions.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Google Earth Engine account ([register here](https://earthengine.google.com/))
- Supabase project

### Installation

```bash
# Clone the repo
git clone https://github.com/faissssss/geosignal-ai.git
cd geosignal-ai

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
```

### Environment Setup

```bash
cp .env.example .env
# Fill in your GEE credentials, Supabase URL, and anon key
```

### Run the Data Pipeline

```bash
python pipeline/run_pipeline.py --region ntt --resolutions 100 250
```

### Run the App

```bash
cd frontend
npm run dev
```

---

## Target Users

| Segment | Users |
|---|---|
| Primary | BAKTI Komdigi (Ministry of Communication and Digital) |
| Secondary | Telkomsel, XL Axiata, Indosat, Regional Governments |

---

## Roadmap

- [x] NTT Province MVP demo
- [x] NTB Province validation
- [x] Central Kalimantan Province validation
- [ ] Weather-aware propagation adjustments
- [ ] Drone imagery integration for micro-level planning
- [ ] Graph Neural Networks for national-scale spatial topology (Phase 3)
- [ ] Full Papua & Maluku coverage

---

## License

This project was built for the GeoAI Hackathon. See [LICENSE](LICENSE) for details.
