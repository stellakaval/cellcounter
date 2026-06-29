# Plan — cellcounter Phase 1: the tool her lab will actually use

## Context

Phase 0 passed: StarDist `2D_versatile_fluo` cleanly and accurately segments the real DAPI
nuclei in the user's Zeiss `.czi` images (verified visually on 512² and 2586² fields, E3/E4).
Now we build the human-facing tool that replaces her sister's manual Fiji pipeline
(B&C → Gaussian blur → Otsu threshold → mask → watershed → Analyze Particles → ROI Manager,
repeated per channel). The lab's audience is non-programmers; the product promise is:
**drop an image → AI count appears → see it, fix it, filter by size, export.**

**Grounding from research (imagej.net/StarDist + image.sc/Reddit sentiment):** scientists want
zero-config AI counting, *visible* and *editable* results (trust is the #1 adoption blocker),
sensible defaults instead of parameter dialogs, a real µm² size filter, auto CSV, and batch
that "just works." The StarDist *Fiji* plugin has none of the last three, requires a multi-site
TensorFlow install, exposes confusing dialogs (normalization percentiles, prob/NMS thresholds,
n_tiles), and **does not run on Apple-Silicon Macs at all**. Our Python build sidesteps every
one of these.

**Locked decisions:**
- **Default model = StarDist** (validated on her data; runs on M1; Cellpose weights can't be
  downloaded here — HuggingFace is blocked). Cellpose-SAM stays selectable and auto-enables if
  its weights are ever present. This reverses the earlier Cellpose-default choice for the
  reasons above.
- **Hide all Fiji preprocessing knobs.** AI replaces blur/threshold/watershed. Expose only:
  min/max area (µm²), circularity, and ONE "sensitivity" slider. (A hidden advanced panel is
  out of scope for now.)
- **Three readouts** the lab reports: per-channel counts, **% EdU+ nuclei**, and **% EdU+
  within PDGFRa+ OPCs**. Marker positivity = mean marker intensity inside (EdU) or around
  (PDGFRa, via dilation) each segmented nucleus, vs an adjustable threshold.

## Key design decisions (Fiji friction → our fix)

| Fiji pain (sourced) | cellcounter |
|---|---|
| Subjective per-image Otsu threshold; irreproducible | AI segments; no threshold dialog |
| Watershed over/under-splits touching nuclei | StarDist separates instances natively |
| Trial-and-error size filter, must reopen file | **Live, non-destructive** min/max µm² + circularity sliders; original image untouched |
| Confusing StarDist dialogs (norm %, prob, NMS, n_tiles) | one **sensitivity** slider → `prob_thresh`; normalization auto (1, 99.8); tiling auto for big images |
| Silent accuracy loss off ~0.5 µm/px | **auto-rescale** to ~0.5 µm/px for StarDist; show pixel size |
| No measurement table / CSV | auto per-cell + summary CSV |
| Per-channel colocalization is manual | built-in EdU% / PDGFRa-gated readouts |
| Black box → distrust | dim-image **contrast slider** + overlay + brush-edit + recount |
| Batch needs brittle macros | folder → one combined CSV |
| Fiji-StarDist won't run on M1 | our Python StarDist does |

## Architecture — fill the existing stubs (`src/cellcounter/`)

Pure functions in io/segment/measure/compare/batch; `widget.py` only wires them to napari.
Reuse the working CZI loader and StarDist/normalize invocation already in
`scripts/phase0_validate.py` (`_load_czi_2d`, `run_stardist`).

- **`io.py`** — `load_image(path) -> ImageData` (dataclass: `array`, `channel_axis`,
  `channel_names`, `pixel_um`). CZI via `czifile` (DAPI=ch0, max-project Z, pixel size from
  `<Distance Id="X">`×1e6); TIFF via tifffile/OME. Plus **`napari_get_reader(path)`** for `.czi`
  (npe2 contract) so drag-drop works — napari's builtin reader does **not** handle `.czi`.
- **`segment.py`** — `list_models()` (StarDist always; Cellpose only if weights present),
  `segment(image2d, model_name, sensitivity, pixel_um) -> int labels`. Lazy-import per backend;
  percentile-normalize; **per-backend sensitivity mapping** (StarDist `prob_thresh = 0.7 −
  0.6*sensitivity`, nms 0.3; Cellpose `cellprob/flow_threshold`); **auto-scale** to ~0.5 µm/px
  via `predict_instances(scale=…)`; auto `n_tiles` for large arrays; graceful-degrade missing
  backend.
- **`measure.py`** — `measure(labels, pixel_um, min_um2, max_um2, min_circ, intensity=None)`
  using `skimage.measure.regionprops_table` (props `label`, `centroid`, `area`, `perimeter`,
  and `intensity_mean` when an intensity image is given — note the 0.26 name). `area_um2 =
  area_px*pixel_um²`; `circularity = 4π·area/perimeter²` clamped ≤1, perimeter==0 guarded.
  Filtering is **row selection only — never mutate labels**. `count(...)`. CSV export helpers
  (two files: `*_cells.csv`, `*_summary.csv`).
- **`compare.py`** — marker positivity + readouts. Per-nucleus EdU mean intensity (in mask) and
  PDGFRa mean intensity (in a peri-nuclear ring via `skimage.segmentation.expand_labels`, ring
  width = µm/pixel_um). Positivity threshold adjustable (default Otsu on per-nucleus means).
  Return per-channel counts, `%EdU+`, `%EdU+ within PDGFRa+` (guard empty denominators).
- **`widget.py`** — magicgui `Container` dock widget + `main()` entry point (already declared in
  pyproject). See UI below.
- **`batch.py`** — folder → apply current model/pixel/filters to each image → one combined CSV
  (per-image counts + readouts; progress off the UI thread).
- **`session.py`** — save/load labels (TIFF) + params (JSON).

## UI (magicgui `Container`, docked right)

```
████  21 cells  ████          ← big live readout
Channel:[DAPI ▾]  Model:[StarDist ▾]
Display contrast: [==|====]    ← so dim DAPI is visible (view only)
Pixel size: 0.62 µm/px (from file, editable)
Min area [=|====] µm²   Max [====|=] µm²   Circularity [|=====]
Sensitivity [===|==]           ← prob_thresh; re-runs model (on release)
[Recount]  [Export CSV]  [Colocalization…]  [Batch folder…]
brush / erase = fix AI → count updates
```

Wiring (verified APIs): `viewer.layers.events.inserted` → on a new **Image** layer
(`isinstance(event.value, Image)`, skip our own Labels via a `metadata` flag) auto-run
segmentation in a `napari.qt.threading.thread_worker`; on `returned`, add a `Labels` layer
named `nuclei`, set `contrast_limits` to the [1, 99.5] percentile, and recount. Area/circularity
sliders' `.changed` re-filter cached regionprops (cheap, live); the **sensitivity** slider
re-runs the model (debounced / on release). All viewer mutation on the main thread only.

## Milestones (commit + acceptance check after each; matches spec's phased gates)

- **M1 — Headline loop.** CZI reader + `io.load_image`; drag a `.czi` → DAPI auto-segments
  (StarDist) in a worker → big count + overlaid `nuclei` Labels + auto-contrast. *Accept:* drop
  a real image, count appears, no button, window never freezes.
- **M2 — Human-in-the-loop + live filters.** Brush/erase edits + Recount; min/max µm² +
  circularity recount live off current labels; sensitivity slider. *Accept:* paint a blob →
  count +1; erase → −1; raise min area → specks drop, count falls.
- **M3 — Measurement + export.** `measure.py` + CSV (per-cell µm² + summary row: count,
  channel, pixel size, filters, timestamp). *Accept:* CSV matches on-screen count; areas in µm².
- **M4 — Multi-channel + colocalization.** Per-channel counts; `%EdU+`; `%EdU+ within PDGFRa+`
  with adjustable positivity threshold; export. *Accept:* on a 2-ch file, EdU% computes and
  matches a hand check on a tiny synthetic case.
- **M5 — Batch + session.** Folder → one combined CSV (replaces the macro; ~100 files); save/load
  session. *Accept:* batch N images → CSV with N rows; reload reproduces counts/params.

Tests (`tests/`, CPU-only, GUI-skipped): `test_measure` (exact count, µm² scaling, filter
boundaries), `test_compare` (known overlap + EdU%), `test_segment` (each available backend ±1 on
an easy synthetic image; skip if backend absent), `test_batch` (CSV shape). Logic lives in pure
functions so most coverage needs no GUI.

## Risks / gotchas
- **CZI drag-drop** needs the npe2 `napari_get_reader` (+ `napari.yaml` manifest & pyproject
  entry point) — builtin napari can't read `.czi`. Wire first or the headline silently fails.
- **inserted-event loop:** must guard so adding our own `nuclei` Labels doesn't re-trigger.
- **Sensitivity slider re-runs the model** (expensive) — debounce; area/circularity only re-filter.
- **Pixel scale:** rescale to ~0.5 µm/px for StarDist or the fine 2586² images under-detect.
- **Cellpose** stays disabled until its HF weights exist; never let its absence crash the app.

## Verification (end-to-end)
1. `cellcounter` (entry point) opens napari; drag `~/Desktop/cellsamples/E4_LDHi_1_5_DAPI__Edu594.czi`
   → ~21 count + overlay appears with no clicks.
2. Brush a nucleus + Recount → +1; raise min area → count drops; numbers update live.
3. Export → open `*_cells.csv`/`*_summary.csv`; areas in µm², count matches screen.
4. A 2-channel file → EdU% and PDGFRa-gated EdU% compute; sanity-check on a synthetic case.
5. Batch `~/Desktop/cellsamples` (or a subset) → one CSV with one row per image.
6. `pytest` green on CPU (GUI tests skipped headless).
