# cellcounter

A local, single-user desktop tool for counting cells in microscopy images. Drag an
image onto a [napari](https://napari.org) window and an AI model segments and counts the
cells; you can then correct mistakes by hand, filter by real-world size (µm²), and export
per-cell measurements to CSV — replacing a fragile Fiji/ImageJ "Analyze Particles" macro.

> **Status: Phase 0 (setup + model validation).** The environment, synthetic test data, and
> the model-validation diagnostic are in place. The napari UI (drag-and-drop auto-count,
> editing, filtering, export) is **not built yet** — that is Phase 1.

## Models

- **Default: Cellpose-SAM** (`cellpose` ≥ 4.2, PyTorch/MPS) — robust on Apple Silicon,
  generalist, no diameter tuning needed.
- **Alternate: StarDist** `2D_versatile_fluo` (TensorFlow) — strong on fluorescent nuclei.

Phase 0 runs **both** on each image so you can compare counts before picking a default for
your own data.

## Install (Apple Silicon, verified)

Requires a **native arm64** Python 3.11 (an Intel/Rosetta Python will fail to find the
TensorFlow wheel and won't get Metal/MPS). We use a `uv`-managed arm64 build:

```bash
uv python install 3.11.15
uv venv --python cpython-3.11.15-macos-aarch64-none .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

See [`env/environment.md`](env/environment.md) for the exact step-by-step install order,
the resolved package versions, and platform notes.

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
| `E4_LDHi_1_5` (512²) | 21 | n/a¹ |
| `E4_LDLow_1_3` (512²) | 10 | n/a¹ |

**Gate: PASS.** Visual inspection of the overlays (in `phase0_results/`) shows StarDist
`2D_versatile_fluo` segments the DAPI nuclei **cleanly and accurately** on the real data —
each bright nucleus a tight distinct region, close pairs correctly split — on both 512² and
2586² fields and across all conditions. **No fine-tuning (Phase 3) is needed.** StarDist is
purpose-built for fluorescent nuclei, which is exactly this data.

> **Default-model note:** the build is currently configured with Cellpose-SAM as default,
> but (a) StarDist is validated and working on your real DAPI images, and (b) Cellpose's
> weights cannot be obtained on this machine (see ¹). Recommendation: **make StarDist the
> default** for this nuclei-counting workflow. This is your call — flagged for Phase 1.

Synthetic-data validation (run earlier) also passed: StarDist matched ground truth exactly
(`synthetic_single.tif` → 25/25, `synthetic_two_channel.tif` ch0 → 20/20).

¹ Cellpose could not be validated: its pretrained weights are hosted on **huggingface.co,
which is unreachable from this network** (TLS connection reset at byte 0, even with the
sandbox disabled; GitHub — StarDist's host — works fine). Environmental, not a code issue —
the Phase 0 script degraded gracefully and reported it rather than crashing. To validate
Cellpose, run on a network with HuggingFace access, or `export HF_ENDPOINT=https://hf-mirror.com`,
or manually place `cpsam_v2` in `~/.cellpose/models/`.

## License & non-commercial use

The cellcounter source code is BSD-3-Clause (see [`LICENSE`](LICENSE)). Cellpose pretrained
weights are trained on **CC-BY-NC** data, so use of this tool with Cellpose models — and any
model fine-tuned from them — is restricted to **non-commercial research use**. This tool is
intended for local, single-user, non-commercial research; no accounts, no cloud, no
telemetry, and your images never leave your machine.
