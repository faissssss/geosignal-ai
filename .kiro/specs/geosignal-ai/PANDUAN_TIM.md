# Panduan Lanjutan Proyek GeoSignal AI — Tim Hackathon

## 📋 Status Proyek Saat Ini

**✅ Tasks 1–10 SELESAI** (Member 1)
- Setup infrastruktur dasar (Supabase, Google Earth Engine, dependencies)
- Data models dan schema database
- Feature engineering framework
- Pipeline dasar scoring dan training
- Migrasi database Supabase sudah dijalankan

**✅ INFRASTRUKTUR READY:**
- Database: 9 tabel, 3 ENUM types, indexes, retention policy ter-deploy
- Frontend scaffold: Next.js + MapLibre setup lengkap
- Environment variables: `.env` dan `frontend/.env.local` configured
- Design spec: UI specifications lengkap di `.kiro/specs/geosignal-ai/design.md`

**🚀 SIAP UNTUK DEVELOPMENT PARALLEL** — Member 2 dan Member 3 bisa langsung mulai!

---

## 👥 Pembagian Tugas

### Member 2 — Tasks 11–20 (Backend ML Lanjutan + Simulation Engine)

#### Apa yang akan dibangun:

| Task | Deskripsi |
|------|-----------|
| **11** | Canopy exclusion constraint (`is_high_canopy`) |
| **12** | DEM LOS precomputation + BTS candidate ranking dengan BallTree |
| **13** | Spatial cross-validation berdasarkan kecamatan |
| **14** | Model versioning + scoring run audit log |
| **15** | ✅ Checkpoint validasi |
| **16** | Ethical Risk Register |
| **17** | `resolve_target_area` (resolusi area target dari drawn polygon atau kecamatan) |
| **18** | What-if grid precomputation |
| **19** | `simulate_bts_placement` + `drag_drop_lookup` (Simulation Engine) |
| **20** | ✅ Checkpoint final |

#### Yang dibutuhkan dari Member 1:

1. **Full repository** dengan tasks 1–10 sudah selesai
2. **File `.env`** lengkap dengan semua API keys:
   ```bash
   SUPABASE_URL=...
   SUPABASE_SERVICE_KEY=...
   GEE_PROJECT_ID=...
   GEE_SERVICE_ACCOUNT_EMAIL=...
   GEE_SERVICE_ACCOUNT_JSON_PATH=...
   OPENCELLID_API_KEY=...
   ```
3. **File `infra/gee-service-account.json`** (Google Earth Engine credentials)

#### ⚠️ PENTING — JANGAN LAKUKAN INI:

- **JANGAN REDEFINE** `CONSOLIDATED_FEATURES`, `ConfidenceThresholds`, atau `FeatureVector`
- **HARUS IMPORT** dari `models.py`:
  ```python
  from geosignal.models import CONSOLIDATED_FEATURES, ConfidenceThresholds, FeatureVector
  ```
- Semua definisi canonical types hanya boleh ada **SATU KALI** di `models.py`

#### Testing & Validasi:

Setelah menyelesaikan setiap task, jalankan:

```bash
cd backend/
python -m pytest ../tests/ -v
```

Pastikan **semua tests pass** sebelum lanjut ke task berikutnya. Tests ini termasuk Hypothesis property tests yang menjaga correctness.

---

### Member 3 — Tasks 21–30 (Frontend + Integration)

#### Apa yang akan dibangun:

| Task | Deskripsi |
|------|-----------|
| **21–24** | Interactive Map (Next.js + MapLibre) |
| - | • Heatmap grid coverage |
| - | • Layer controls (grid/candidates/admin boundaries) |
| - | • Side panel informasi |
| - | • Region selector |
| **25** | Low-confidence acknowledgement gate |
| **26** | Kecamatan dropdown + target-area selector |
| **27** | End-to-end integration backend ↔ frontend |
| **28** | Supabase wiring (queries, API routes) |
| **29** | Docker containerization |
| **30** | README final + dokumentasi deployment |

#### Yang dibutuhkan dari Member 1:

1. ✅ **Full repository** — direktori `frontend/` sudah ter-scaffold dengan:
   - Next.js setup
   - MapLibre GL JS di `package.json`
   - Struktur folder dasar

2. ✅ **File `.env`** untuk frontend (copy ke `frontend/.env.local`):
   ```bash
   NEXT_PUBLIC_SUPABASE_URL=https://ljstbtohevwxfreexvuu.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

3. ✅ **File `.kiro/specs/geosignal-ai/design.md`** — berisi spec lengkap untuk UI:
   - Warna heatmap (hijau/kuning/merah untuk Low/Med/High confidence)
   - Layer stack dan kontrol
   - Side panel content
   - Behaviour confidence gate

4. ✅ **Database Supabase sudah ready** — tabel sudah ada dan bisa diquery (migrasi sudah dijalankan)

#### ⚠️ DEPENDENCY PENTING:

**Tasks 11–12 (LOS + candidate ranking) HARUS SELESAI** sebelum Member 3 bisa wire up frontend candidate display.

**Koordinasi dengan Member 2!**

#### Setup Awal:

```bash
cd frontend/
npm install
npm run dev
```

Frontend akan jalan di `http://localhost:3000`

---

## 🔍 Peran Member 1 sebagai Reviewer

### Ketika Member 2 & 3 selesai, check hal ini:

#### 1. **No Type Redefinitions** ❌
Jalankan check ini:
```bash
grep -r "class ConfidenceThresholds" backend/
grep -r "CONSOLIDATED_FEATURES =" backend/
```

**Harus hanya muncul SATU KALI** (di `backend/geosignal/models.py`). Jika lebih dari satu, ada redefinisi yang harus diperbaiki.

#### 2. **All Tests Pass** ✅
```bash
cd backend/
python -m pytest ../tests/ -v --tb=short
```

Semua tests (termasuk Hypothesis property tests) harus pass. Ini adalah safety net untuk correctness.

#### 3. **Schema Compliance** 📊
Pastikan kode menggunakan nama kolom yang sesuai dengan `infra/migrations/001_initial_schema.sql`:

**Contoh kolom yang sering salah:**
- `grid_cells.confidence_tag` (bukan `confidence_level`)
- `bts_candidates.los_validated` (boolean, bukan nullable)
- `scoring_runs.retained_for_months` (integer, default 12)

#### 4. **Integration Testing** 🔗
Test end-to-end flow:
1. Jalankan backend pipeline untuk generate data
2. Buka frontend, pilih region
3. Pastikan heatmap muncul dengan data real dari Supabase
4. Test drag-drop BTS simulation
5. Check low-confidence warning muncul jika ada

---

## 📦 File & Resource yang Dibutuhkan Tim

### Member 2 needs:
- ✅ `.env` (full credentials)
- ✅ `infra/gee-service-account.json`
- ✅ `backend/geosignal/models.py` (jangan diubah!)
- ✅ Access ke Supabase project

### Member 3 needs:
- ✅ `frontend/.env.local` (NEXT_PUBLIC_* variables) — **SUDAH ADA**
- ✅ `.kiro/specs/geosignal-ai/design.md` (UI spec) — **SUDAH ADA**
- ✅ Access ke Supabase project — **SUDAH SETUP, MIGRASI SELESAI**
- ✅ Koordinasi dengan Member 2 untuk task 11–12

---

## 🚀 Quick Start Commands

### Backend (Member 2):
```bash
cd backend/
pip install -e .
python -m pytest ../tests/ -v
python -m geosignal.pipeline --region Jakarta --resolution 500
```

### Frontend (Member 3):
```bash
cd frontend/
npm install
npm run dev
# Open http://localhost:3000
```

### Database Check (Both):
```bash
# Install Supabase CLI (sudah ada)
supabase --version

# Check tables
# Go to: https://supabase.com/dashboard
# Project: ljstbtohevwxfreexvuu
# SQL Editor → Run:
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```

---

## 📊 Definition of Done

### Member 2 (Tasks 11–20):
- [ ] Semua 10 tasks implemented
- [ ] All pytest tests pass
- [ ] No type redefinitions
- [ ] LOS computation working (task 12)
- [ ] Simulation engine working (task 19)
- [ ] Ethical risk register populated (task 16)

### Member 3 (Tasks 21–30):
- [ ] Interactive map dengan heatmap working
- [ ] Layer controls functional
- [ ] Drag-drop BTS simulation integrated
- [ ] Low-confidence gate implemented
- [ ] Kecamatan selector working
- [ ] Docker compose ready
- [ ] README updated

---

## 🆘 Troubleshooting

### Import Error: `cannot import name 'ConfidenceThresholds'`
**Fix:** Pastikan import dari `models.py`, bukan redefine:
```python
from geosignal.models import ConfidenceThresholds
```

### Supabase Connection Error
**Fix:** Check `.env` file memiliki credentials yang benar:
```bash
SUPABASE_URL=https://ljstbtohevwxfreexvuu.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Google Earth Engine Authentication Failed
**Fix:** Pastikan file `infra/gee-service-account.json` ada dan path di `.env` benar:
```bash
GEE_SERVICE_ACCOUNT_JSON_PATH=infra/gee-service-account.json
```

### Frontend Can't Fetch Data
**Fix:** 
1. Check backend pipeline sudah generate data ke Supabase
2. Check `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_ANON_KEY` di `frontend/.env.local`
3. Check CORS settings di Supabase dashboard

---

## 📞 Koordinasi Tim

**Critical Path Dependency:**
```
Member 2 Task 11–12 → Member 3 Task 23–24
(LOS + Ranking)      (Candidate Display)
```

**Recommended Sequence:**
1. Member 2: Complete tasks 11–14 first (core ML)
2. Member 3: Start tasks 21–22 (map setup) in parallel
3. **SYNC POINT**: After Member 2 finishes task 12
4. Member 3: Continue tasks 23–24 (candidate display)
5. Both: Integration testing (tasks 27–28)

---

## ✅ Checklist Sebelum Submit

- [ ] All tests pass (`pytest -v`)
- [ ] No duplicate type definitions (`grep` check)
- [ ] Database schema compliance verified
- [ ] Frontend connects to backend successfully
- [ ] Docker compose works (`docker-compose up`)
- [ ] README updated with setup instructions
- [ ] `.env.example` updated
- [ ] Demo video recorded (jika required)

---

**Good luck, team! 🚀**

*Jika ada pertanyaan atau blocker, koordinasi di group chat atau raise issue di repo.*
