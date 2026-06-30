# cellcounter

A local, single-user desktop tool for counting cells in microscopy images. Drag an
image onto a [napari](https://napari.org) window and an AI model segments and counts the
cells; you can then correct mistakes by hand, filter by real-world size (µm²), and export
per-cell measurements to CSV — replacing a fragile Fiji/ImageJ "Analyze Particles" macro.

> **Status: Phase 1 MVP complete (pending live GUI check on a Mac with a display).** Phase 0
> passed (StarDist works on the real DAPI images). The tool now does the full loop: **drop a
> `.czi` → automatic cell count**, editable overlay, live µm²/circularity filters, CSV export,
> multi-channel colocalization (% EdU+ and % EdU+ within PDGFRa+), folder batch → one CSV, and
> save/load session. 23 unit tests pass on CPU.

## Models

- **Default: StarDist** `2D_versatile_fluo` (TensorFlow) — purpose-built for fluorescent
  nuclei (DAPI), validated on the real images, and runs on Apple Silicon.
- **Alternate: Cellpose-SAM** (`cellpose` ≥ 4.2, PyTorch/MPS) — generalist; enabled once its
  weights (`cpsam_v2`) are present in `~/.cellpose/models/`.

Both are available in the model dropdown so you can compare counts on your own data (e.g. on
`E4_LDHi_1_5`: StarDist → 21, Cellpose-SAM → 19).

## Install (Apple Silicon, verified)

Requires a **native arm64** Python 3.11 (an Intel/Rosetta Python will fail to find the
TensorFlow wheel and won't get Metal/MPS). We use a `uv`-managed arm64 build:

```bash
uv python install 3.11.15
uv venv --python cpython-3.11.15-macos-aarch64-none .venv
source .venv/bin/activate
uv pip install ".[dev]"
```

(Use a **regular** install, not `-e`/editable: this machine's Python doesn't process the
editable `.pth`, so an editable install makes `import cellcounter` fail. Re-run
`uv pip install .` after changing the source.)

See [`env/environment.md`](env/environment.md) for the exact step-by-step install order,
the resolved package versions, and platform notes.

## Use it

Open the **Terminal** app on the Mac and run these three lines (the first two are one-time
per terminal session):

```bash
cd ~/Desktop/cellcounter
source .venv/bin/activate
cellcounter
```

A napari window opens with the **cellcounter** panel docked on the right. (Tip: in this
project's terminal you can also type `! cellcounter` to launch it directly.)

> **Note:** the app must be started from a normal desktop login session (your Terminal) so it
> can open a window. It cannot be launched from a remote/headless/automated shell — that has no
> display to draw on.

Then **drag a `.czi` (or TIFF) onto the window** — the DAPI channel is segmented automatically
and a big cell count appears, with an editable `nuclei` overlay. From there:

- **Channels are split into named, colored layers** — `DAPI` (blue), `EdU` (red), `PDGFRa`
  (green) — in the layer list (top-left). DAPI shows by default; click a marker's eye icon to
  see it. So you always know which channel is which.
- **See the original photo**: click **"Show original (hide outlines)"**, or **hold the `H` key**
  to peek at the raw image while held (outlines reappear when you release).
- **Adjust display contrast** to actually see dim DAPI (view only; doesn't change the count).
- **Min/max area (µm²)** and **circularity** sliders filter the count live and
  non-destructively — this is the "Analyze Particles" step, made interactive. **Min area
  defaults to 30 µm²** to drop small noise/debris (see Accuracy below); lower it to 0 to see
  every raw detection.
- **Fix the AI** with napari's brush/erase on the `nuclei` layer, then click **Recount**.
- **Sensitivity** trades more vs. fewer detections (one knob instead of Fiji's threshold dialogs).
- **Export CSV** writes a per-cell table (areas in µm²) plus a one-row summary.
- **Colocalization**: pick the EdU (and optional PDGFRa) channel → get **% EdU+ nuclei** and
  **% EdU+ within PDGFRa+ OPCs** (positivity by per-nucleus marker intensity).
- **Batch folder…** runs the current settings over a whole folder → one combined CSV
  (one row per image) — this replaces the ImageJ macro.
- **Save/Load session** persists the (edited) labels + all parameters for reproducibility.

No Fiji concepts (blur, threshold, watershed) — the AI replaces all of that. See
[`docs/research_notes.md`](docs/research_notes.md) for the design rationale.

## Accuracy

Counts are validated against hand-verified ground truth (`Book.xlsx`, Sheet1) across all 100
real images. Without a size filter the AI over-counted by 26% (small noise/debris). With the
**default 30 µm² minimum** the AI total is within **~1%** of the correct total and **85% of
images are within ±2 cells** (94% within ±3). Re-check anytime with:

```bash
python scripts/validate_counts.py --folder ~/Desktop/cellsamples --truth ~/Desktop/Book.xlsx --min-um2 30
```

The remaining per-image differences are handled by adjusting the size slider and the
brush/erase hand-correction.

## Phase 0 — model validation

Generate synthetic test images, then run both models and compare:

```bash
python sample_data/make_synthetic.py          # writes TIFFs + prints ground-truth counts
python scripts/phase0_validate.py             # runs on sample_data/ by default
python scripts/phase0_validate.py --folder /path/to/real/images   # later, on real images
```

Per-image 3-panel figures (original | StarDist | Cellpose) are written to
`phase0_results/`, and a count table is printed. The choice of default model and whether
fine-tuning is needed is decided **after** validating on real microscopy images.

### Phase 0 results — REAL images (`cellsamples/`, Zeiss `.czi`)

Validated on a representative sample of 8 of the ~100 real DAPI/EdU images (the nuclei =
**DAPI = channel 0**; Z-stacks max-projected). Counts are per field; these are sparse
sorted-cell cultures, so per-field counts are naturally low (~8–21 over a ~320 µm field).

| image (DAPI channel) | StarDist | Cellpose |
|---|---|---|
| `APOE_LDSort_OPC…` (2586², 3ch, 5 Z) | 8 | n/a¹ |
| `E3_LDHi_3_2` (512²) | 9 | n/a¹ |
| `E3_LDLow_1_5` (2586²) | 14 | n/a¹ |
| `E3_LDLow_4_2` (512²) | 9 | n/a¹ |
| `E4_1_2_5` (512²) | 16 | n/a¹ |
| `E4_3_1_3` (512²) | 16 | n/a¹ |
| `E4_LDHi_1_5` (512²) | 21 | 19 |
| `E4_LDLow_1_3` (512²) | 10 | — |

**Gate: PASS.** Visual inspection of the overlays (in `phase0_results/`) shows StarDist
`2D_versatile_fluo` segments the DAPI nuclei **cleanly and accurately** on the real data —
each bright nucleus a tight distinct region, close pairs correctly split — on both 512² and
2586² fields and across all conditions. **No fine-tuning (Phase 3) is needed.** StarDist is
purpose-built for fluorescent nuclei, which is exactly this data, so it is the **default**;
Cellpose-SAM is selectable for comparison (e.g. `E4_LDHi_1_5`: StarDist 21 vs Cellpose 19).

Synthetic-data validation (run earlier) also passed: StarDist matched ground truth exactly
(`synthetic_single.tif` → 25/25, `synthetic_two_channel.tif` ch0 → 20/20).

> The 8-image table above is StarDist-only because the original validation network
> SNI-blocked `huggingface.co`, so Cellpose's weights couldn't be fetched then. On a later
> network the official `cpsam_v2` downloaded fine and Cellpose was validated. If Cellpose
> weights ever fail to download it's the network — fetch them from the official source and
> place in `~/.cellpose/models/`.

## License & non-commercial use

The cellcounter source code is BSD-3-Clause (see [`LICENSE`](LICENSE)). Cellpose pretrained
weights are trained on **CC-BY-NC** data, so use of this tool with Cellpose models — and any
model fine-tuned from them — is restricted to **non-commercial research use**. This tool is
intended for local, single-user, non-commercial research; no accounts, no cloud, no
telemetry, and your images never leave your machine.
