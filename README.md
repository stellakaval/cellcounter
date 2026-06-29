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

## License & non-commercial use

The cellcounter source code is BSD-3-Clause (see [`LICENSE`](LICENSE)). Cellpose pretrained
weights are trained on **CC-BY-NC** data, so use of this tool with Cellpose models — and any
model fine-tuned from them — is restricted to **non-commercial research use**. This tool is
intended for local, single-user, non-commercial research; no accounts, no cloud, no
telemetry, and your images never leave your machine.
