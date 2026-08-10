# Running GeoSignal AI Locally

## ✅ Prerequisites (Already Installed)

- ✅ Python 3.12.5
- ✅ Node.js v22.14.0
- ✅ Backend dependencies installed
- ✅ Frontend dependencies installed
- ✅ Environment variables configured

## 🚀 Quick Start

### Frontend Development Server

The frontend is **currently running** at:
- **URL**: http://localhost:3000
- **Framework**: Next.js 14.2.15
- **Map Library**: MapLibre GL JS 4.7.1

To start it manually in the future:
```bash
cd frontend
npm run dev
```

### Backend Python Package

The backend `geosignal` package is installed in editable mode and ready to use:

```bash
# Import and use the geosignal package
python
>>> from geosignal import pipeline
```

## 📋 Available Commands

### Frontend Commands (in `frontend/` directory)

```bash
npm run dev        # Start development server (currently running)
npm run build      # Build for production
npm run start      # Start production server
npm run lint       # Run ESLint
npm run typecheck  # TypeScript type checking
npm run test       # Run tests with Vitest
```

### Backend Commands

```bash
# Run the data pipeline (example for NTT region)
python -m geosignal.pipeline --region ntt --resolutions 100 250

# Run tests
pytest backend/

# Run specific test file
pytest backend/tests/test_specific.py
```

## 🗄️ Database Setup

Your Supabase database is configured at:
- **URL**: https://ljstbtohevwxfreexvuu.supabase.co
- **Schema**: `infra/migrations/001_initial_schema.sql`

The schema includes these main tables:
- `grid_cells` - Coverage score grid cells
- `bts_candidates` - BTS placement recommendations
- `target_areas` - Selected regions for analysis
- `whatif_grid` - Before/after simulation results
- `admin_boundaries` - Administrative boundary data
- `los_results` - Line-of-sight validation results
- `model_artifacts` - ML model versions
- `scoring_runs` - Audit log of scoring runs

To apply migrations manually:
1. Go to your Supabase dashboard
2. Navigate to SQL Editor
3. Copy and paste the content from `infra/migrations/001_initial_schema.sql`
4. Execute the migration

## 🗺️ Google Earth Engine Setup

Your GEE credentials are configured:
- **Project ID**: geosignal-ai
- **Service Account**: geosignal-gee-777@geosignal-ai.iam.gserviceaccount.com
- **Credentials File**: `infra/gee-service-account.json`

Make sure the service account has Earth Engine API enabled in your Google Cloud project.

## 📊 Data Sources

The system integrates multiple geospatial data sources:

| Source | Purpose | API Key Required |
|--------|---------|------------------|
| SRTM DEM | Elevation data | No (via GEE) |
| ESA WorldCover | Land cover | No (via GEE) |
| OpenGeoAI | Canopy height | No (via GEE) |
| OpenCellID | Tower locations | ✅ Configured |
| WorldPop | Population density | No (via GEE) |
| Ookla Open Data | Signal quality | No (public S3) |

## 🔧 Troubleshooting

### Frontend Issues

**Port 3000 already in use?**
```bash
# Find and kill the process
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

**Environment variables not loading?**
- Check `frontend/.env.local` exists
- Restart the dev server
- Variables must be prefixed with `NEXT_PUBLIC_` for browser access

### Backend Issues

**Import errors?**
```bash
# Reinstall the package
cd backend
pip install -e .
```

**GEE authentication errors?**
```bash
# Test GEE authentication
python -c "import ee; ee.Initialize(project='geosignal-ai'); print('GEE OK')"
```

### Database Issues

**Connection errors?**
- Verify Supabase project is active
- Check API keys in `.env` file
- Test connection from Supabase dashboard

## 📍 Next Steps

1. **Open the app**: Navigate to http://localhost:3000
2. **Explore the map**: The UI should load with MapLibre
3. **Test features**:
   - View coverage heatmap
   - Get BTS recommendations
   - Run before/after simulations
   - Drag-and-drop placement testing

4. **Run the pipeline** (optional):
   ```bash
   python -m geosignal.pipeline --region ntt --resolutions 100 250
   ```

## 🏗️ Project Structure

```
geosignal-ai/
├── backend/
│   └── geosignal/          # Python package
│       ├── pipeline.py     # Main data pipeline
│       ├── models.py       # ML models (XGBoost, LightGBM)
│       ├── scoring.py      # Coverage scoring
│       ├── candidates.py   # BTS candidate search
│       ├── simulation.py   # What-if scenarios
│       └── ...
├── frontend/
│   ├── app/                # Next.js 14 app directory
│   ├── components/         # React components
│   ├── lib/                # Utilities and Supabase client
│   └── ...
├── infra/
│   ├── migrations/         # Database schemas
│   └── gee-service-account.json
└── data/                   # Local data cache

```

## 🎯 Demo Regions

The MVP focuses on these regions:
- **Primary**: NTT Province (~700 blank-spot villages)
- **Secondary**: NTB Province (arid/elevation profile)
- **Secondary**: Central Kalimantan (dense forest profile)

## 📚 Documentation

- Project requirements: `.kiro/specs/geosignal-ai/requirements.md`
- System design: `.kiro/specs/geosignal-ai/design.md`
- Implementation tasks: `.kiro/specs/geosignal-ai/tasks.md`
- Data sources: `docs/data_sources.md`
- Team guide: `.kiro/specs/geosignal-ai/PANDUAN_TIM.md`

---

**Status**: ✅ Frontend is running at http://localhost:3000

**Need help?** Check the troubleshooting section above or review the documentation files.
