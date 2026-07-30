# **GeoSignal AI: Hackathon Project Proposal**

## **GeoAI-Assisted Coverage Gap Detection & BTS Placement Recommendation for Indonesia's 3T Regions**

Core Themes: Connectivity, Efficiency, Innovation, Sustainability, and Security. **Connectivity** is our primary mission: bridging the digital divide for Indonesia's underserved regions. Our site suggestions avoid unnecessary deforestation to maintain environmental integrity.

### **1. Project Vision & MVP Philosophy**

The most common pitfall in hackathons is scope creep. GeoSignal AI avoids this by deliberately shrinking the scope while maintaining technical credibility and ethical rigor. Our vision is to provide a decision-support system that is not only accurate but also transparent and responsible by design.

**The National Vision:** GeoSignal AI is designed as a province-by-province deployable framework, not a one-off analysis. The hackathon MVP validates the approach in **NTT Province** as the primary demo, with **NTB Province** and **Central Kalimantan Province** presented as secondary validation evidence that the underlying method generalizes across different terrain profiles (mountainous/valley vs. forest canopy). Phase 3 (Section 14) is explicitly the pathway from single-province proof-of-concept to nationwide coverage across all of Indonesia's 3T regions, including eventual generalization to Papua and Maluku.

**The MVP Goal:** Help telecom planners identify hidden coverage gaps in 3T regions and recommend exactly where a new BTS would have the greatest impact, backed by an ethical risk framework.

### **2. The Problem**

* Indonesia's geography comprises over 17,000 islands, vast mountainous terrains, dense forests, and highly remote areas.
* Current planning often relies superficially on population counts, existing BTS locations, and administrative boundaries.
* **The Reality Gap:** A village may appear geographically close to a BTS on a 2D map, but mountains, valleys, forests, or bodies of water can significantly attenuate or block signal quality.

**Success Criteria:** Model performance must be reported using **spatially-blocked cross-validation** (holding out entire geographic blocks, not random points) rather than in-sample fit or a random train-test split. Because nearby geospatial points share strong spatial autocorrelation, a random split leaks information between train and test sets and inflates reported accuracy. We validate by holding out entire sub-districts (kecamatan) so the model is scored only on terrain it has never seen, ensuring the reported accuracy reflects genuine generalizability across Indonesia's diverse landscapes rather than an artifact of the split.

* **The Result:** Communities experience poor connectivity, infrastructure investments are misallocated, and millions in 3T regions remain fundamentally underserved.

#### **Problem Validation & Citations**

* **Nationwide Scale:** As of April 2026, 3,029 villages nationwide are classified as blank-spots, identified by Kemenko Polkam as a key barrier to education and the digital economy.
* **Government Prioritization:** President Prabowo Subianto targets 2,500 connected 3T villages by end of 2026, supported by an Oct 2025 MoU between Kemkomdigi and Kemendes PDTT targeting ~2,300 initial villages.

**Sources:**
1. [ANTARA News](https://www.antaranews.com/berita/5547309/kemenko-3029-desa-di-indonesia-masih-blank-spot-hingga-tahun-ini)
2. [Reboart](https://www.reboart.net/2026/06/kemiskinan-digital-desa-kontras-5g-ibu.html)
3. [Nesabamedia](https://www.nesabamedia.com/kemkomdigi-dan-kemendes-pdtt-bersatu-padu-bangun-akses-internet-di-ribuan-desa-blank-spot/)

### **3. The Solution**

**GeoSignal AI** analyzes geographic conditions in tandem with telecom infrastructure to estimate potential coverage gaps. Instead of simply counting towers, the system answers the core question: *Can people actually receive a usable signal?*

### **4. Target Audience**

| Segment | Target Users |
| :---- | :---- |
| **Primary** | BAKTI Komdigi (Ministry of Communication and Digital) |
| **Secondary** | Telkomsel, XL Axiata, Indosat, Regional Governments |

### **5. Use Case Illustration**

**MVP Demo Focus — NTT Province:** ~700 blank-spot points remain as of April 2026. Within NTT Province, Kabupaten Kupang is a 2026 "Kampung Internet" priority, piloting Oelpuah, Kuanheun, and Tuatuka. Telkomsel activated new BTS in Desa Sanleo, Uabau, and Barang in April 2025. Resident Merry (Desa Sanleo) noted significant improvements in communication access. Network disruptions have severely impacted public safety, such as police (Polsek) operations in Malaka Timur. A DPR Komisi I delegation also visited Manggarai Barat in Nov 2025 to highlight urgent infrastructure needs. This is the region our live hackathon demo runs against.

**Secondary Validation Evidence (generalization, not live demo):**
* **NTB Province:** As of May 2026, Bima Regency (within NTB Province) has one remaining true blank-spot (Desa Kalodu, Langgudu) and ~40 locations with weak signals. Province-wide, NTB reported 103 blank-spot/weak-signal locations as of 2024. Used to sanity-check the model against a second, drier terrain profile.
* **Central Kalimantan Province:** Within Central Kalimantan Province, Kabupaten Lamandau has 38 of 85 villages remaining blank-spot or inadequately served as of mid-2026. Used to sanity-check the model against dense-canopy terrain, distinct from NTT's elevation-driven attenuation.

**Sources:**
4. [RRI Kupang](https://rri.co.id/kupang/daerah-3t/2366449/menjembatani-kesenjangan-digital-program-kampung-internet-hadir-di-ntt)
5. [Pikiran Rakyat Manggarai](https://manggarai.pikiran-rakyat.com/ntt/pr-3379295854/telkomsel-perluas-jaringan-di-ntt-tiga-desa-baru-kini-nikmati-akses-internet)
6. [Detik Bali](https://www.detik.com/bali/bisnis/d-7894165/telkomsel-perluas-jaringan-telekomunikasi-di-tiga-desa-di-nusa-tenggara-timur)
7. [Sergap](https://sergap.co.id/2025/08/16/jaringan-terganggu-warga-malaka-timur-harap-telkomsel-pulihkan-layanan-jelang-hut-ke-80-ri/)
8. [E-Media DPR RI](https://emedia.dpr.go.id/news/2025/12/01/komisi-i-tekankan-pemerataan-akses-internet-di-ntt-tak-boleh-ada-daerah-blank-spot)
9. [Suara NTB](https://suarantb.com/2026/05/20/tinggal-satu-desa-di-bima-blank-spot/)
10. [ANTARA Mataram](https://mataram.antaranews.com/berita/350703/dprd-ntb-atensi-keluhan-warga-terkait-blank-spot-di-langgudu-bima)
11. [Ini Kalteng](https://www.inikalteng.com/puluhan-desa-di-lamandau-masih-blank-spot-pemkab-dorong-perluasan-jaringan-telekomunikasi/)

| Province | Illustrative Kabupaten/Village | Tower Data | Terrain Driver | Target Context | Recommendation |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **NTT Province** — MVP demo | Kupang (Oelpuah) | OpenCellID Only | High Elevation | 2026 Pilot Point | **High Priority Placement** |
| **NTB Province** — validation | Bima (Kalodu, Langgudu) | OpenCellID Only | Arid/Elevation Mix | Last remaining true blank-spot | **Confirmatory Check** |
| **Central Kalimantan Province** — validation | Lamandau (38 Vills) | OpenCellID Only | Forest Canopy | 45% Blank-spots | **Blank-spot Optimization** |

### **6. Core Workflow Pipeline**

```
[Satellite Imagery] + [DEM] + [Land Cover] + [BTS Locations] + [Population] + [Ookla Signal Data]
                              ↓
                    GEE Fusion & Harmonization (Step 0: Data Quality Pass)
                              ↓
              ┌───────────────────────────────┐
              │  Tier 1: Cold-Start AHP        │  (zero ground-truth regions)
              │  Tier 2: XGBoost/LightGBM      │  (trained against Ookla ground truth)
              └───────────────────────────────┘
                              ↓
                     Coverage Gap Heatmap + Coverage Score
                              ↓
                BallTree Candidate Search → Priority Ranking
                              ↓
              DEM-Based Line-of-Sight Validation (precomputed)
                              ↓
              Suggested BTS Locations + Confidence Tag (Low/Med/High)
                              ↓
           Drag-and-Drop / Before-After Simulation (user-facing)
```

**Data-to-app flow:** Google Earth Engine handles multi-source fusion and export → Python (XGBoost/AHP/BallTree) handles modeling and candidate ranking → Next.js/Supabase serves the interactive map and simulation UI. Teams should register GEE accounts on day one — approval can take longer than expected and blocks the entire pipeline downstream.

### **7. MVP Features**

1. **Interactive Map:** Visualizes existing BTS, villages, terrain, and land cover in one unified view.
2. **Coverage Gap Heatmap:** Replaces standard tower radius circles with a dynamic "Coverage Quality" heatmap (🟢 Good, 🟡 Moderate, 🔴 Poor) factoring in terrain.
3. **Recommendation Engine:** Calculates a "Coverage Score" (e.g., 42/100) using the eight geospatial input features in the Consolidated Feature Reference Table (Section 8.1) — elevation, slope, land cover class, canopy height, distance-to-BTS, road distance, population density, and public facility proximity. Ookla signal quality is used separately as the Tier 2 training label and as a Confidence Tagging input, not as a scoring input (see Section 8.1, Note 3). Identifies where adding a BTS creates the highest expected percentage improvement.
4. **BTS Placement Suggestion:** GeoAI automatically suggests specific candidate coordinates (e.g., Candidate #1, Candidate #2), scored using the same consolidated feature set (Section 8.1) via BallTree-indexed candidate search.
5. **Confidence Tagging:** Every suggested site and heatmap cell is tagged Low/Med/High confidence, based on proximity to the nearest OpenCellID tower and nearest Ookla tile (see Section 9).
6. **Before / After Simulation:** A "wow" factor for judges. Users can click "Simulate New BTS" to instantly see the coverage heatmap update and metric improvements (e.g., jumping from 48% to 74% coverage), using precomputed what-if scenarios (see Section 8 note on live vs. precomputed).
7. **Drag-and-Drop Simulation:** Users can drag a candidate marker to any point on the map. The system **looks up a precomputed terrain-deformed coverage ring** for the nearest grid cell to that position, displays a live Coverage Score and confidence panel, and shows a side-by-side comparison against the model's own top-ranked suggestion for that area — including cases where the user's manual placement outperforms the model's recommendation. A secondary, optional **"power/energy feasibility"** toggle checks proximity to power grids or solar potential; this is a low-priority overlay that does not affect the core Coverage Score.

### **8. Technical Architecture: Two-Tier Modeling Design**

The backend backbone is powered by a Google Earth Engine (GEE) pipeline for multi-source data fusion and harmonization. The modeling follows a two-tier design:

* **Step 0: Data Quality Pass:** Comprehensive Attribute, Geometry, and Spatial QC to remove noise from crowd-sourced and satellite inputs.
* **Tier 1: Cold-start AHP:** An Analytic Hierarchy Process for regions with zero ground truth, using weighted geospatial drivers.
* **Tier 2: Trained ML Model:** An XGBoost/LightGBM model trained against Ookla Open Data ground truth for high-fidelity gap detection.
* **BTS Placement Strategy:** Scalable candidate selection using BallTree indexing to find optimal coordinates within massive point clouds.
* **Signal Simulation:** Lightweight DEM-based line-of-sight and path-loss simulations, run **precomputed** ahead of the demo to validate candidate sites and power the Before/After and Drag-and-Drop features within a hackathon's time and compute budget. This is explicitly *not* live recomputation against arbitrary points at demo time — see Section 7, Feature 7 for what is and isn't recomputed live versus looked up from a precomputed grid.
* **Validation:** Spatially-blocked cross-validation by kecamatan (see Section 2, Success Criteria) — never a random point-wise split.

#### **8.1 Consolidated Feature Reference Table**

> **Note on row count:** The table below contains **8 scoring features** (rows 1–8) plus **1 label-only row** (Ookla) = 9 rows total. Ookla is not a scoring input — it is the Tier 2 training label and Confidence Tagger input only. The "eight geospatial input features" referenced throughout this document refers to rows 1–8 exclusively.

| Feature | Data Source | Resolution | Used in (AHP / XGBoost / LOS / Confidence) |
| :---- | :---- | :---- | :---- |
| Elevation | SRTM DEM | 30m | AHP, LOS-simulation |
| Slope | SRTM DEM | 30m | AHP |
| Land Cover | ESA WorldCover | 10m | AHP, LOS-simulation |
| Canopy Height | OpenGeoAI canopy | 30m | AHP, LOS-simulation |
| Distance-to-BTS | OpenCellID | N/A | AHP, XGBoost |
| Road Distance | OSM | Vector | AHP |
| Population Density | WorldPop | 100m | AHP, XGBoost |
| Ookla signal quality | Ookla | Tile-based | Tier 2 training label only; Confidence-tagging |
| Public facility proximity | OSM POI data | N/A | AHP, XGBoost |

**Notes:**
1. "Dense vegetation" is deliberately split into a concrete land-cover-class layer and a separate canopy-height layer — do not use the vaguer phrase "dense vegetation" anywhere else in this document; always refer back to this table.
2. Public facility proximity supports equity prioritization. Administrative boundaries (village/regency labeling) are intentionally excluded from this table as they serve as a labeling/display layer, not a scoring input.
3. Ookla is **not** an input feature to either tier's Coverage Score computation — it is (a) the training label that Tier 2 (XGBoost/LightGBM) is fitted against, and (b) a separate input to the Confidence Tagger. Feeding Ookla in as both label and predictor would leak the target into the model; Tier 1 (AHP) and Tier 2 both score on the same **eight** geospatial input features (all rows above except Ookla), with Ookla used only downstream of scoring to validate Tier 2 and to set confidence.
4. Confidence tagging is explicitly tied to the nearest OpenCellID tower and nearest Ookla tile — this is the only place Ookla proximity feeds back into system output.

### **9. Explainability & Trust**

To build trust with government stakeholders, we use SHAP (SHapley Additive exPlanations) to provide feature importance for every recommendation. Each suggested BTS site is tagged with a confidence level (Low/Med/High) based on data density and model certainty, per the Consolidated Feature Reference Table above.

### **10. Ethics & Responsible AI**

#### **10.1 Ethical Risk Register**

| Risk | Impact | Mitigation | Owner |
| :---- | :---- | :---- | :---- |
| Digital Exclusion | Low-population clusters get systematically deprioritized despite genuine need | Explicit equity weighting in AHP via public facility proximity and population density | Model/Data Lead |
| Environmental (Deforestation) | Recommended sites encourage clearing of forest canopy | Land cover and canopy-height constraints exclude high-canopy candidates by default | Model/Data Lead |
| OpenCellID sparsity misread as "confirmed no coverage" | A blank OpenCellID record gets treated as verified zero-signal rather than unknown/unmeasured, misdirecting investment | Confidence tagging explicitly flags "no nearby tower or Ookla tile" as Low-confidence unknown, not Red/poor coverage | Data Lead |
| Low-confidence scores driving real funding decisions | A government stakeholder acts on a Low-confidence recommendation as if it were high-fidelity | UI visually distinguishes confidence tiers; pitch and documentation explicitly frame output as "GeoAI-assisted estimates," not authoritative signal predictions | Product/Presentation Lead |
| Resampling/harmonization mismatch (MAUP) | Combining 10m, 30m, and 100m-resolution layers at a single grid size can distort scores depending on the chosen cell size | Test Coverage Score output at more than one grid resolution before finalizing; document the chosen resolution and why | Model/Data Lead |

#### **10.2 7-Dimension Ethics Self-Audit**

| Dimension | Status/Commitment |
| :---- | :---- |
| Fairness | Coverage Score is evaluated per-region, not only in aggregate, so accuracy in low-data areas (e.g., Central Kalimantan Province's dense canopy, illustrated by Kabupaten Lamandau) is checked separately rather than masked by strong performance in well-mapped areas. |
| Privacy | Aggregated, non-PII data used throughout (WorldPop density grids, not individual records; no household-level location data collected or stored). |
| Transparency | SHAP explainability integrated — every recommendation shows its top contributing factors in plain language, not just a bare score. |
| Accountability | Each risk in the Ethical Risk Register (10.1) has a named owner role; no recommendation is presented as fully automated or free of a responsible human reviewer. |
| Safety & Reliability | Confidence tagging (Low/Med/High) lets the system visibly flag uncertainty rather than presenting all recommendations with false equal confidence. |
| Sustainability | Two-tier design deliberately favors a lightweight AHP fallback and a right-sized XGBoost/LightGBM model over training a large model from scratch; land-cover constraints also reduce downstream environmental cost of acting on recommendations. |
| Human Oversight | Explicitly positioned as decision-support only — recommendations are inputs to a human planner's decision, not an auto-executed placement; users can override any suggested candidate via the Drag-and-Drop feature (Section 7). |

### **11. Technology Stack**

| Domain | Tools & Technologies |
| :---- | :---- |
| **Architecture** | Google Earth Engine (GEE), Next.js, Supabase |
| **Models & Logic** | XGBoost/LightGBM, SHAP, BallTree (Scikit-Learn), AHP |
| **Data** | Ookla Open Data, OpenCellID, WorldPop, SRTM DEM |
| **Stretch Goal** | Graph Neural Networks (GNN) for spatial topology |

*Note: "Simulate New BTS" and the Drag-and-Drop panel both read from a precomputed what-if grid rather than performing live DEM recomputation at demo time — this keeps compute costs and demo latency predictable within a hackathon weekend. See Section 8 for the full rationale.*

### **12. Benefits**

* **Government:** Better investment decisions, drastically reduced waste on infrastructure spending.
* **Telecom Operators:** Faster planning cycles, optimized network expansion.
* **Citizens:** Improved connectivity, leading to enhanced access to education, healthcare, and emergency services.

### **13. Challenges & Mitigation**

* **Data Completeness:** OpenCellID coverage is incomplete. *Mitigation for Hackathon:* Focus the live demo on a single province (NTT Province) as proof-of-concept and acknowledge data limitations transparently, using NTB Province and Central Kalimantan Province only as secondary generalization evidence (see Section 5).
* **Signal Propagation Complexity:** Real RF models are incredibly dense. *Mitigation:* Frame output as "GeoAI-assisted coverage potential estimates" rather than pretending to replace commercial radio-planning software like Okumura-Hata.
* **Validation:** Validating signal quality without operator measurements is tough. *Mitigation:* Compare recommendations against known underserved regions or government reports, using spatially-blocked cross-validation (Section 2) rather than in-sample fit.

**Terrain Differentiator:** In NTT Province, signal difficulty is primarily driven by sharp elevation and valley blocking. In Central Kalimantan Province, the primary barrier is dense forest canopy attenuation. This contrast is exactly why Central Kalimantan Province is retained as validation evidence even though NTT Province is the live demo — it proves the model isn't overfit to one terrain type.

**Validation Approach:** We use named village-level targets (Oelpuah in NTT Province, the 38 Lamandau blank-spots in Central Kalimantan Province, Desa Kalodu in NTB Province) as comparison points for model output. **Caveat:** Low/zero tower data in OpenCellID signifies unknown status, not necessarily zero coverage — this caveat is enforced directly in the Confidence Tagging feature (Section 7) and the Ethical Risk Register (Section 10.1), not just stated here.

### **14. Future Enhancements**

* Weather-aware propagation adjustments and seasonal vegetation tracking.
* Integration with drone imagery for micro-level planning.
* Generalization to Papua and Maluku regions with local data partnerships.
* Cost-aware BTS placement optimization models.

### **15. Hackathon Potential (Why This Wins)**

Most GeoAI telecom projects stop at visualization ("Here is a map of towers"). This project explicitly answers a planning decision: *"Given Indonesia's unique geography, where should we build the next BTS to connect the greatest number of people hidden behind terrain and vegetation?"*

By framing it as a planning-support prototype rather than a flawless signal predictor, it remains technically achievable over a weekend while demonstrating profound, actionable innovation.

### **16. Phase 3: Path to National Scale — 5 Pillars of Scalable GeoAI**

1. **Algorithm Choice:** Transition from single-province XGBoost/AHP to distributed Graph Neural Networks (GNNs) for national-scale spatial topology.
2. **Distributed Processing:** Leveraging Spark/Dask for parallel raster analysis across all 3T regions simultaneously, rather than one province at a time.
3. **Parallelisation:** Splitting candidate-search (BallTree) and simulation workloads across compute nodes to keep per-province turnaround time constant as coverage expands nationally.
4. **Containerization & CI/CD:** Docker-based deployment with automated pipelines so each new province's data pass runs through the same validated Step 0 quality checks without manual intervention.
5. **Versioning & Auditability:** Every model version and every scoring run is logged and reproducible — this is what lets the team answer "why did this score change?" for a government stakeholder months after a recommendation was made, and is treated as a distinct, non-negotiable pillar rather than folded into general "Ops Maturity."