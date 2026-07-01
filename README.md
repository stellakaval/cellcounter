# cellcounter

AI-powered cell counting web app for fluorescence microscopy. Upload `.czi` or `.tiff` images, get automatic DAPI nucleus counts and EdU+ proliferation ratios, review and correct detections interactively, then export to Excel.

**Live app: [https://cellcounter-api.fly.dev](https://cellcounter-api.fly.dev)**

---

## What it does

- **Segment nuclei** with StarDist `2D_versatile_fluo` — purpose-built for DAPI fluorescence, no tuning needed
- **EdU+ classification** via Otsu thresholding on per-nucleus EdU/DAPI intensity ratio
- **Interactive review** — click to add or remove individual cells, toggle DAPI/EdU channels with `1`/`2`, keyboard-driven (`N`/`P` next/prev image, `O` overlay toggle, `A`/`R` approve/flag)
- **Corrections are channel-aware** — DAPI additions (green) and EdU+ additions (orange) are tracked separately
- **Per-project filters** — min/max cell area (µm²), circularity, NMS threshold, model sensitivity
- **Excel export** — one row per image with DAPI count, EdU count, EdU%, and all filter settings
- **Multi-scene `.czi` support** — each scene imported as a separate image

---

## Architecture

```
Browser (React + Vite + Tailwind)
    │  HTTPS
    ▼
Fly.io  (FastAPI + uvicorn, Docker)
    ├── Supabase Postgres  — projects, images, counts
    ├── /data volume (1 GB) — uploaded CZI files, labels, renders, CSVs
    └── Supabase Auth      — Google OAuth, JWT verification
```

- **Backend**: FastAPI, SQLModel, StarDist/TensorFlow, scikit-image, tifffile, czifile
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Supabase JS client
- **Auth**: Supabase Google OAuth → JWT → FastAPI `python-jose` verification
- **Storage**: Fly.io persistent volume for image artifacts; Supabase Postgres for metadata
- **Deploy**: Multi-stage Dockerfile (Node build → Python 3.11 slim), Fly.io

---

## Using the app

1. Go to **[https://cellcounter-api.fly.dev](https://cellcounter-api.fly.dev)**
2. Sign in with Google
3. Create a project, upload `.czi` or `.tiff` files (up to 300 MB each)
4. Wait for segmentation to complete (StarDist loads on first run — ~30s cold start)
5. Click any image to review detections
6. Export results to Excel when done

### Review keyboard shortcuts

| Key | Action |
|-----|--------|
| `1` | Switch to DAPI channel |
| `2` | Switch to EdU channel |
| `Tab` | Cycle channels |
| `O` | Toggle detection overlay |
| `N` / `P` | Next / previous image |
| `A` | Approve image |
| `R` | Flag as needs review |
| Click image | Add nucleus (channel-aware) |
| Click detection | Remove detection |

---

## Local development

### Prerequisites

- Python 3.11 (arm64 on Apple Silicon)
- Node 20+

### Backend

```bash
pip install -r webapp/requirements.txt
pip install -e . --no-deps
cd /path/to/cellcounter
uvicorn webapp.backend.app:app --reload
```

No auth in local dev — the backend falls back to `"dev-user"` when `SUPABASE_JWT_SECRET` is not set.

### Frontend

```bash
cd webapp/frontend
npm install
npm run dev
```

Set `webapp/frontend/.env.local` if you want Supabase auth locally:
```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

---

## Deployment

The app is deployed on Fly.io as a single service (FastAPI serves the built React assets as static files).

### Environment secrets (Fly.io)

```bash
fly secrets set \
  SUPABASE_JWT_SECRET="..." \
  DATABASE_URL="postgresql://..." \
  ALLOWED_ORIGINS="https://cellcounter-api.fly.dev"
```

### Deploy

```bash
flyctl deploy \
  --build-arg VITE_SUPABASE_URL=https://your-project.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=eyJ...
```

The Dockerfile is multi-stage: Node 20 builds the frontend, Python 3.11-slim runs the server. Image size is ~755 MB (StarDist + TensorFlow only — napari/PyQt6/torch are excluded from the server image).

### Infrastructure costs

| Service | Tier | Cost |
|---------|------|------|
| Fly.io machine | shared-cpu-1x, 256 MB | ~$0–5/mo |
| Fly.io volume | 1 GB persistent disk | ~$0.15/mo |
| Supabase | Free tier (500 MB Postgres) | $0 |
| **Total** | | **~$0–5/mo** |

---

## Project structure

```
cellcounter/
├── src/cellcounter/        # Core library (IO, segmentation, measurement)
├── webapp/
│   ├── backend/            # FastAPI app
│   │   ├── app.py          # Lifespan, CORS, static file mount
│   │   ├── auth.py         # Supabase JWT verification
│   │   ├── worker.py       # Background segmentation thread
│   │   ├── models.py       # SQLModel DB models
│   │   ├── db.py           # Engine setup (Postgres or SQLite)
│   │   └── routers/        # projects, images, settings, review, export
│   ├── frontend/           # React app
│   │   └── src/
│   │       ├── pages/      # ProjectsPage, ProjectPage, ImageReviewPage, LoginPage
│   │       ├── components/ # OverlayCanvas, Sidebar, etc.
│   │       └── api/        # Axios client + TypeScript types
│   └── requirements.txt    # Web-only Python deps (no napari/torch)
├── Dockerfile              # Multi-stage build
├── fly.toml                # Fly.io config
└── NEXT_VERSION.md         # Upcoming features + pre-release checklist
```

---

## Accuracy

Validated on 100 real DAPI/EdU images (Zeiss `.czi`, DAPI = channel 0). StarDist `2D_versatile_fluo` with a 30 µm² minimum area filter:
- AI total within **~1%** of hand-verified ground truth
- **85% of images within ±2 cells**, 94% within ±3

---

## License

BSD-3-Clause. Cellpose pretrained weights (optional, not used in the web app) are trained on CC-BY-NC data — non-commercial research use only.
