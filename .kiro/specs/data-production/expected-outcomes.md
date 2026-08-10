# Data Production Expected Outcomes

## Phase 0 — Access and safety

### Work

- Verify GEE authentication with the configured service account and a small
  read-only SRTM request.
- Verify configured Ookla archive endpoints and retain period, byte size, and
  SHA-256 checksum.
- Verify OpenCellID access without printing its key.
- Verify Supabase schema, storage, and write/read access.

### Expected outcome

- A dated access report proves each source is reachable before production
  writes begin.
- A failed source is visible as unavailable. It never produces random values,
  copied NTT features, or a silent zero-data success.

## Phase 1 — Provenance and storage

### Work

- Create a durable source-run record for each ingestion and scoring operation.
- Store real-source BTS points, village geometry, contour lines, and land-cover
  outputs with region, source date/version, source run, and timestamp.
- Mark existing sample rows explicitly as `demo`; do not merge them with a
  promoted real-data run.

### Expected outcome

- Every visible map feature can be traced to a source and production run.
- The UI/API can distinguish `real`, `derived`, `demo`, and `unavailable`.

## Phase 2 — Regional extraction

### Work

- Bound all GEE, Ookla, OpenCellID, and village extraction to the 45 stored
  kecamatan in NTT, NTB, and Central Kalimantan.
- Extract SRTM, ESA WorldCover, canopy, and WorldPop from GEE.
- Download Ookla once, verify checksum, and spatially filter before scoring.
- Ingest OpenCellID points and approved OSM/government village geometry with
  required attribution.

### Expected outcome

- Source extracts contain only target-province data and retain their version
  and attribution.
- Missing tower/Ookla records mean low-confidence unknown coverage, not a
  claimed coverage gap.

## Phase 3 — Heatmap scoring

### Work

- Generate valid analysis points within each kecamatan and sample real
  geospatial attributes.
- Build the eight-feature vector from GEE-derived values and real BTS distance.
- Use Tier 1 where Ookla labels are absent; use Tier 2 only after model
  training/validation against retained Ookla labels.
- Persist score, confidence, feature/source references, model version, source
  run, and scoring run.

### Expected outcome

- Each of 45 kecamatan has at least one non-demo heatmap cell contained by its
  own boundary.
- Low score cells are modelled coverage gaps; direct measured labels and model
  estimates remain visibly distinct in provenance.

## Phase 4 — Supporting map layers

### Work

- Publish land cover from GEE in a browser-efficient format.
- Derive 50 m or approved 100 m SRTM contours with elevation attributes.
- Persist village polygons and BTS tower points.
- Generate candidates only from real scored cells after constraints and LOS,
  then precompute what-if results.

### Expected outcome

- No layer is an empty placeholder: land cover, contours, villages, BTS, and
  candidates all contain source-backed features or show a clear unavailable
  source state.

## Phase 5 — Filtering and interaction

### Work

- Provide layer APIs scoped by region and optional target area.
- Use point containment for heatmap/BTS/candidates and geometry intersection
  for land cover/contours/villages.
- Reload MapLibre sources when region or selected boundary changes.
- Preserve visibility toggles; reset target area when region changes.

### Expected outcome

- Selecting a kecamatan immediately removes all out-of-boundary features from
  every active layer.
- Switching region cannot leave NTT data visible in NTB or Central Kalimantan.
- Toggling a layer restores the current filtered subset—not an unfiltered
  regional dataset.

## Phase 6 — Validation, promotion, rollback

### Work

- Report per-kecamatan counts for every applicable layer.
- Execute API and browser tests for filters, empty results, layer toggles,
  feature clicks, source errors, and region switches.
- Promote a complete real-source run; only then archive/delete explicitly
  marked demo rows. Retain a prior-run rollback reference.

### Expected outcome

- A final manifest reports 45/45 heatmap coverage, source metadata, known
  limitations, test results, and a rollback run ID.
- Production promotion is reversible and cannot partially remove working data.

## Definition of done

1. GEE dataset IDs, Ookla checksums, OpenCellID retrieval metadata, and village
   attribution are stored with the production run.
2. All 45 kecamatan have real-source heatmap coverage; no active demo heatmap
   rows remain after promotion.
3. Every applicable layer is filter-tested against every selected boundary.
4. The map accurately communicates unavailable/missing source data instead of
   fabricating a feature or score.
