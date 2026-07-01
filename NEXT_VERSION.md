# Cellcounter Web App — Roadmap

## Pre-release blockers (must fix before hosting publicly)

These are **security / reliability gaps** that make the current build unsafe for internet exposure.

| # | Item | Why it's a blocker |
|---|------|--------------------|
| 1 | **Authentication** | Zero auth — any visitor can view all projects, delete data, trigger segmentation jobs |
| 2 | **Upload size cap** | Large files (`.czi` can be 500 MB+) are loaded fully into RAM with no limit — DoS risk |
| 3 | **Docker container** | No Dockerfile or compose file; can't deploy without it |
| 4 | **Processing error messages** | Worker silently swallows all exceptions; failed images appear stuck with no message |
| 5 | **Logging** | Nothing logged in production — impossible to diagnose issues remotely |
| 6 | **CORS policy** | Not set; needed if API and frontend are ever on separate origins |
| 7 | **HTTPS** | Needs TLS termination (nginx/Caddy reverse proxy in front) |

---

## Version 1 — Ranked feature/fix list (next session)

### Tier 1 — High impact, relatively quick

1. **Better error handling for failed images** — write the error message to the DB, surface it in the UI so users know why an image failed and can retry or skip
2. **Upload progress bar** — large `.czi` files (100–500 MB) upload silently; show bytes progress
3. **EdU channel auto-detection** — detect channel named "EdU", "488", "594", etc. automatically instead of requiring manual channel selection
4. **Re-run single image** — add per-image "Re-run" button so users don't have to rerun the whole project when one image fails
5. **Undo/redo for cell corrections** — Cmd+Z should undo the last add/delete on the review page

### Tier 2 — Bigger features, high value

6. **Split/merge correction tools** — when a cluster of nuclei is counted as one, allow splitting; when over-split, allow merging. Draw a line to split, click-drag two cells to merge.
7. **Confidence scores + triage mode** — use StarDist's per-object `prob` values (already computed but discarded in `segment.py details`) to flag images as High/Medium/Low confidence and sort the review queue by "needs attention most"
8. **Click-to-set cell size** — user clicks 3–5 typical nuclei, app reads their measured area and auto-sets min/max µm² filter instead of raw numbers
9. **Multi-group export** — tag images as Treatment A / Control / etc. and export a summary with group columns for statistics

### Tier 3 — Polish and power-user features

10. **Z-stack projection choice** — currently always max-projects Z; expose Single slice / Max project / Mean project per project
11. **PDF report** — one-click report with thumbnail grid, counts table, settings used, date
12. **PDGFRA / second proliferation marker** — count a second EdU-equivalent channel and include ratio in export
13. **Batch review shortcuts** — "approve all high-confidence" button to bulk-approve images above a confidence threshold, reducing manual clicks for clean datasets
14. **Cellpose model bundling** — bake Cellpose-SAM weights into Docker image so it works out-of-the-box without requiring manual download

### Tier 4 — Later / nice to have

15. Per-image notes/comments field
16. Dark/light mode toggle
17. Image zoom sync across channels (DAPI and EdU zoom together)
18. Minimap navigator for large images
19. Export corrections as corrected label masks (`.tif`)
20. Keyboard shortcut customization

---

## Known bugs to fix

- [ ] `viewportToImage` used a stale baseScale computation (fixed in this session — verify)
- [ ] Silent `except: pass` in worker.py — images silently fail
- [ ] EdU channel detection on images processed before the ratio feature was added requires a page reload to trigger lazy re-computation
- [ ] `corrections.json` grows without bound if users repeatedly add/delete the same cell (no dedup)

---

## Architecture notes for hosting

- Single-worker queue is fine for a small lab (5–10 concurrent users); add Celery + Redis only if needed
- SQLite is adequate for single-server deploy; use a mounted volume so data survives container restarts
- StarDist weights (~50 MB) should bake into the Docker image — don't download at runtime
- Serve frontend as FastAPI StaticFiles (single-origin, no CORS needed) — already wired, just needs `npm run build` step in Dockerfile
- Minimum VM: 4 GB RAM (StarDist + 2–3 active users), 2 vCPU, 20 GB disk
