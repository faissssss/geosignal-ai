# Map Layer Filter Guide

Complete guide to each map layer in GeoSignal AI, including what data it shows, visualization style, and how to use it.

---

## 1. 🟢🟡🔴 **Heatmap** (Coverage Quality)

### What It Shows
**Mobile network coverage quality** across the region, displayed as a color-coded grid of cells.

### Data Source
- **Table**: `grid_cells` (50 rows in your database)
- **Coverage Score**: 0-100 indicating signal quality
- **Confidence Tag**: High/Med/Low reliability of the prediction

### Visualization
**Color-coded grid cells** overlaid on the map:
- 🟢 **Green** (Score ≥70): **Good coverage** - Strong mobile signal, no issues
- 🟡 **Yellow** (Score 40-69): **Moderate coverage** - Usable but could be better
- 🔴 **Red** (Score <40): **Poor coverage / Coverage gaps** - Weak or no signal

### How It Looks
```
┌─────────────────────────────┐
│  🟢🟢🟢  🟡🟡  🔴🔴🔴      │  Each square = 100m x 100m grid cell
│  🟢🟢🟢  🟡🟡  🔴🔴🔴      │  Color shows signal strength
│  🟢🟢🟢  🟡🟡  🔴🔴🔴      │  Red areas = where new towers are needed
│           🔴🔴🔴          │
└─────────────────────────────┘
```

### What It's For
- **Identify coverage gaps** (red areas need new towers)
- **Understand signal quality** across the region
- **Prioritize where to build** new cell towers
- **Show before/after** when simulating new tower placement

### Interactive Features
- **Click a cell** → Opens side panel with:
  - Exact coverage score
  - Confidence level
  - SHAP values (why this score was predicted)
  - GPS coordinates

### Current State in Your App
✅ **Working** - 50 grid cells loaded, will display when toggled ON

---

## 2. 🌳 **Land Cover** (Terrain Type)

### What It Shows
**Land use classification** - what type of terrain/vegetation is in each area.

### Data Source
- **External API**: ESA WorldCover 2021 (European Space Agency)
- **URL**: `https://services.terrascope.be/wmts/v2`
- **Resolution**: 10 meters globally
- **Categories**: 11 land cover types

### Visualization
**Semi-transparent overlay** showing different terrain types:
- 🌳 **Dark Green**: Trees/forests
- 🌾 **Light Green**: Grassland/crops
- 🏙️ **Red/Orange**: Built-up areas (cities/towns)
- 🏔️ **Gray**: Bare/sparse vegetation
- 💧 **Blue**: Water bodies
- ❄️ **White**: Snow/ice
- 🌊 **Dark Blue**: Permanent water
- 🏞️ **Yellow**: Shrubland
- 🌴 **Olive**: Mangroves
- 🪨 **Brown**: Moss/lichen

### How It Looks
```
┌─────────────────────────────┐
│  🌳🌳🌳🏙️🏙️🌾🌾          │  Colored overlay on base map
│  🌳🌳🏙️🏙️🏙️🌾🌾          │  Shows what land type is where
│  🏔️🏔️🏙️🏙️🌾🌾💧          │  Semi-transparent (55% opacity)
│     🏔️🏔️🌾💧💧💧          │
└─────────────────────────────┘
```

### What It's For
- **Understand terrain impact** on signal propagation
- **Plan construction** (avoid forests, water bodies)
- **Assess accessibility** for building crews
- **Explain coverage** (forests block signals more than open fields)

### Current State in Your App
⚠️ **Service Error** (External API unreliable):
- ESA service returns `ERR_HTTP2_PROTOCOL_ERROR`
- **Warning indicator (⚠️)** displays next to checkbox
- **Graceful degradation**: Other layers continue working
- **Not a bug**: External service issue, handled correctly

### Interactive Features
- **Hover** → Shows land cover type (if service working)
- **Toggle opacity** → See more or less of underlying map

---

## 3. 🗺️ **Contours** (Elevation Lines)

### What It Shows
**Topographic contour lines** showing elevation/terrain height.

### Data Source
- **Planned**: SRTM (Shuttle Radar Topography Mission) elevation data
- **Resolution**: 30 meters
- **Lines**: Every 50m or 100m elevation change

### Visualization
**Brown curved lines** showing equal elevation:
- Thin lines = terrain contours
- Close together = steep slope
- Far apart = flat/gentle terrain
- Line labels = elevation in meters

### How It Looks
```
┌─────────────────────────────┐
│    ╱────╲                    │  Each line = same elevation
│   ╱  500m ╲                  │  Tight lines = steep mountain
│  ╱    ╱─╲  ╲                 │  Wide lines = flat valley
│ ╱    ╱300m╲  ╲               │  Numbers = meters above sea level
│╱    ╱      ╲  ╲              │
└─────────────────────────────┘
```

### What It's For
- **Assess line-of-sight** (mountains block signals)
- **Plan tower placement** (high ground = better coverage)
- **Understand terrain challenges** for construction
- **Validate AI predictions** (check if terrain explains coverage gaps)

### Current State in Your App
⚠️ **Placeholder** (No data loaded yet):
- Layer exists but has no contour data
- Toggle works but nothing displays
- Requires running backend pipeline to generate

### Interactive Features (when data loaded)
- **Hover** → Shows elevation at that point
- **Click** → Opens side panel with elevation profile

---

## 4. 🏘️ **Villages** (Administrative Boundaries)

### What It Shows
**Village/settlement boundaries** - where people actually live.

### Data Source
- **Planned**: Village-level administrative boundaries
- **Source**: OpenStreetMap or government GIS data
- **Granularity**: Individual villages/settlements

### Visualization
**Yellow/orange polygons** with borders:
- **Fill**: Semi-transparent yellow (8% opacity)
- **Outline**: Solid orange line
- **Label**: Village name (when zoomed in)

### How It Looks
```
┌─────────────────────────────┐
│   ┌────────┐                 │  Yellow shaded areas = villages
│   │Village │  ┌──────┐       │  Orange borders
│   │   A    │  │Vill B│       │  Shows where people live
│   └────────┘  └──────┘       │  Smaller than kecamatan boundaries
│      ┌──────────┐            │
│      │ Village C│            │
└─────────────────────────────┘
```

### What It's For
- **Prioritize coverage** for populated areas
- **Measure impact** (how many villages newly covered?)
- **Equity analysis** (are remote villages underserved?)
- **Target area definition** (select specific villages)

### Current State in Your App
⚠️ **Placeholder** (No data loaded yet):
- Layer exists but has no village data
- Toggle works but nothing displays
- Requires loading village boundaries dataset

### Interactive Features (when data loaded)
- **Click village** → Shows village name, population
- **Highlight** → On hover
- **Filter** → By population size or coverage status

---

## 5. 📡 **BTS Towers** (Existing Cell Towers)

### What It Shows
**Existing cell tower locations** currently providing coverage.

### Data Source
- **Table**: Would be `bts_locations` or similar (not currently loaded)
- **Source**: OpenCellID database (open-source cell tower database)
- **Data**: GPS coordinates, cell ID, operator, technology (2G/3G/4G)

### Visualization
**Small purple/blue circles** with white borders:
- 🔵 **Blue circle** = Cell tower location
- **Size**: 5-7 pixels radius
- **White stroke**: Makes them visible on any background
- **Clustered**: Multiple towers may overlap in cities

### How It Looks
```
┌─────────────────────────────┐
│    🔵     🔵🔵               │  Each blue dot = existing tower
│        🔵     🔵             │  Shows current infrastructure
│  🔵              🔵          │  Helps understand coverage baseline
│     🔵  🔵🔵  🔵             │  More dots = better coverage
│              🔵              │
└─────────────────────────────┘
```

### What It's For
- **See existing infrastructure** before adding new towers
- **Avoid duplication** (don't build where towers already exist)
- **Understand coverage baseline** (why some areas have good coverage)
- **Analyze gaps** (areas with no nearby towers)

### Current State in Your App
⚠️ **No data** (OpenCellID not loaded yet):
- Toggle works but no markers display
- Would need to fetch OpenCellID data for NTT region
- API key exists in .env: `OPENCELLID_API_KEY`

### Interactive Features (when data loaded)
- **Click tower** → Shows:
  - Operator name
  - Technology (4G/3G/2G)
  - Cell ID
  - Coverage radius estimate
- **Hover** → Highlights tower
- **Filter** → By operator or technology

---

## 6. 🟠 **Candidates** (Recommended New Tower Sites)

### What It Shows
**AI-recommended locations** for building NEW cell towers to improve coverage.

### Data Source
- **Table**: `bts_candidates` (10 rows in your database)
- **Generated by**: Machine learning model analyzing coverage gaps
- **Ranked**: Best locations first (Rank 1 = highest priority)

### Visualization
**Larger orange circles** with white borders:
- 🟠 **Orange circle** = Recommended tower site
- **Size**: 7-9 pixels radius (larger than existing towers)
- **White stroke**: 2px thick for visibility
- **Numbered** (optional): Rank 1, 2, 3...

### How It Looks
```
┌─────────────────────────────┐
│    ①🟠                       │  Each orange dot = AI recommendation
│           ②🟠                │  Numbers = priority rank
│  ③🟠              ⑤🟠        │  Larger than existing towers
│        ④🟠                   │  Click to see why it was recommended
│                   ⑥🟠        │
└─────────────────────────────┘
```

### What It's For
- **Identify where to build** new towers
- **Prioritize investment** (Rank 1 = highest impact)
- **Understand AI reasoning** (SHAP values explain why)
- **Simulate placement** (see before/after coverage)

### Current State in Your App
✅ **Working** - 10 candidates loaded:
- Rank 1-10 (best to worst)
- 4 High confidence, 3 Med, 3 Low
- 7 have line-of-sight validation
- Located around Alor region, NTT

### Interactive Features
✅ **Click marker** → Opens side panel with:
- **Rank**: 1-10 (priority)
- **Expected Improvement**: % coverage increase
- **Confidence Tag**: High/Med/Low
- **LOS Validated**: Yes/No (line-of-sight check)
- **SHAP Values**: Why this location? (e.g., high population, low current coverage, good terrain)
- **Coordinates**: Exact GPS location

### What the Data Means
```json
{
  "rank": 1,                          // Best candidate
  "expected_improvement": 18.5,       // Would improve coverage by 18.5%
  "confidence_tag": "High",           // AI is confident in this prediction
  "los_validated": true,              // Line-of-sight check passed
  "shap_values": {                    // Why this location?
    "population": 0.38,               //   - High population nearby
    "terrain": 0.29,                  //   - Good terrain (high ground)
    "land_cover": 0.19,               //   - Open land (no forests)
    "distance_to_grid": 0.09          //   - Close to power grid
  }
}
```

---

## Layer Interaction & Stacking

### Visibility Toggle
Each checkbox controls a layer independently:
- ✅ **Checked** = Layer visible
- ☐ **Unchecked** = Layer hidden
- Changes happen **instantly** without page reload

### Layer Order (Bottom to Top)
1. **Base map** (OpenStreetMap terrain)
2. **Heatmap** (coverage cells)
3. **Land Cover** (terrain types)
4. **Contours** (elevation lines)
5. **Villages** (settlement boundaries)
6. **BTS Towers** (existing towers)
7. **Candidates** (recommended sites)

### Best Combinations

#### **Planning Mode**: Heatmap + Candidates
```
✅ Heatmap     ✅ Candidates
☐ Land Cover  ☐ BTS Towers
☐ Contours    ☐ Villages
```
**Why**: See coverage gaps (red cells) + where to build (orange markers)

#### **Analysis Mode**: All Layers
```
✅ Heatmap     ✅ Candidates
✅ Land Cover  ✅ BTS Towers
✅ Contours    ✅ Villages
```
**Why**: Full context - terrain, existing towers, coverage, recommendations

#### **Terrain Analysis**: Land Cover + Contours
```
☐ Heatmap     ☐ Candidates
✅ Land Cover  ☐ BTS Towers
✅ Contours    ☐ Villages
```
**Why**: Understand how terrain/land use affects signal propagation

#### **Impact Assessment**: Heatmap + Villages + Candidates
```
✅ Heatmap     ✅ Candidates
☐ Land Cover  ☐ BTS Towers
☐ Contours    ✅ Villages
```
**Why**: See which villages are underserved + where new towers would help

---

## Current Status Summary

| Layer | Status | Data Rows | Working? |
|-------|--------|-----------|----------|
| 🟢 Heatmap | ✅ Ready | 50 cells | Yes |
| 🌳 Land Cover | ⚠️ External error | N/A (API) | Handled gracefully |
| 🗺️ Contours | ⚠️ No data | 0 | Toggle works, no display |
| 🏘️ Villages | ⚠️ No data | 0 | Toggle works, no display |
| 📡 BTS Towers | ⚠️ No data | 0 | Toggle works, no display |
| 🟠 Candidates | ✅ Ready | 10 sites | Yes |

### To Fully Populate All Layers

1. **Heatmap** ✅ - Already working
2. **Land Cover** ⚠️ - External service (out of our control)
3. **Contours** - Load SRTM data via backend pipeline
4. **Villages** - Import village boundaries from OpenStreetMap
5. **BTS Towers** - Fetch from OpenCellID API
6. **Candidates** ✅ - Already working

---

## How to Test Each Layer

### 1. Heatmap
1. Toggle ON
2. Look for colored grid squares
3. Red areas = coverage gaps
4. Click a cell → See coverage score in side panel

### 2. Land Cover
1. Toggle ON
2. Look for ⚠️ warning icon (expected)
3. Hover over icon → See error message
4. Other layers should still work

### 3. Contours
1. Toggle ON
2. Nothing displays (expected - no data yet)
3. Toggle OFF
4. No errors should occur

### 4. Villages
1. Toggle ON
2. Nothing displays (expected - no data yet)
3. Toggle OFF
4. No errors should occur

### 5. BTS Towers
1. Toggle ON
2. Nothing displays (expected - no data yet)
3. Toggle OFF
4. No errors should occur

### 6. Candidates ✅
1. Toggle ON
2. **10 orange markers should appear** (Alor region)
3. Click any marker → Side panel opens
4. Panel shows: Rank, expected improvement, confidence, SHAP values
5. Toggle OFF → Markers disappear

---

## Visual Reference

### What Your Map Should Look Like

**With All Working Layers ON** (Heatmap + Candidates):
```
┌─────────────────────────────────────────────────────────┐
│  Controls                                        Panels │
│  ┌──────────────┐                         ┌──────────┐ │
│  │ Region: NTT▼ │                         │ Selected │ │
│  └──────────────┘                         │ Candidate│ │
│  ☑Heatmap ☐LC⚠️ ☐Contours                 │ Rank: 3  │ │
│  ☐Villages ☐BTS ☑Candidates               │ Conf:High│ │
│                                            │ Improve  │ │
│     🟢🟢🟢🟡🟡🔴🔴                          │ +15.2%   │ │
│     🟢🟢🟠①🟡🔴🔴🔴                         │ ...      │ │
│     🟢🟠③🟡🟡🟡🔴                           └──────────┘ │
│     🟠④🟡🟡🟠②🔴                                        │
│     🟡🟡🟠⑤🔴🔴                                         │
│                                                        │
│  Map: Alor region, NTT Province                        │
│  Colors: Coverage quality (green=good, red=gaps)       │
│  Orange dots: AI recommendations for new towers        │
└─────────────────────────────────────────────────────────┘
```

**Legend**:
- 🟢 = Good coverage (score ≥70)
- 🟡 = Moderate coverage (40-69)
- 🔴 = Poor coverage / gaps (<40)
- 🟠① = Candidate site (number = rank)

---

## Troubleshooting

### Layer doesn't display when toggled
1. Check browser console for errors
2. Verify data exists: `python check_data.py`
3. Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
4. Check if layer has data (see table above)

### Land Cover shows ⚠️
This is **expected**! ESA WorldCover service is unreliable. The warning indicator is correct behavior, not a bug.

### Candidates don't appear
1. Refresh browser after applying the region query fix
2. Check console: Should see `POST /api/recommendations 200` (not 500)
3. Toggle Candidates checkbox ON
4. Look around Alor region (coordinates: -8.2°, 124.5°)

### No data in Contours/Villages/BTS layers
This is **expected** until you load the respective datasets. The toggles work, but there's nothing to display yet.

---

This guide explains all 6 map layers and how they work together to help planners make decisions about where to build new cell towers!
