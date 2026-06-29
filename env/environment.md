# Environment setup

This documents the **actual** working install for cellcounter on the target machine.

## Target machine

- Apple Silicon **M1 Pro**, `arm64`, macOS (Darwin 25).
- Python **3.11.15**, native **arm64** (a `uv`-managed CPython build).

## Critical gotcha: use a NATIVE arm64 Python

The machine has an Anaconda Python 3.11 that is an **x86_64 (Intel)** build. Creating the
venv from it produces an x86_64/Rosetta environment, which:

- **Cannot install TensorFlow** — TF dropped macOS x86_64 wheels; only `macosx_*_arm64`
  wheels exist for current TF. `uv` reports `tensorflow==2.21.0 has no wheels with a
  matching platform tag (e.g. macosx_26_0_x86_64)`.
- **Loses MPS** — PyTorch Metal (MPS) acceleration requires arm64.

Fix: install and use a native arm64 interpreter via `uv`:

```bash
uv python install 3.11.15
uv venv --python cpython-3.11.15-macos-aarch64-none .venv
.venv/bin/python -c 'import platform; print(platform.machine())'   # must print: arm64
```

If `platform.machine()` prints `x86_64`, stop — you picked the Intel Python.

## Install order

Install order matters (heavy/fragile deps first, single Qt binding). From the repo root,
with the arm64 `.venv` created above:

```bash
source .venv/bin/activate
uv pip install "numpy>=1.26,<2.3" scipy pandas tifffile scikit-image matplotlib
uv pip install "tensorflow>=2.20,<2.22"        # arm64 CPU; do NOT set TF_USE_LEGACY_KERAS
uv pip install "csbdeep>=0.8" "stardist>=0.9.2"
uv pip install "cellpose>=4.2,<5"              # pulls torch (arm64 + MPS)
uv pip install "napari[pyqt6]" magicgui pytest
uv pip install -e .
```

Shortcut once the venv exists: `uv pip install -e ".[dev]"` resolves the same set from
`pyproject.toml`.

## Resolved versions (verified working)

| package | version |
|---|---|
| python | 3.11.15 (arm64) |
| numpy | 2.2.6 |
| scipy | 1.17.1 |
| pandas | 3.0.4 |
| scikit-image | 0.26.0 |
| tifffile | 2026.3.3 |
| tensorflow | 2.21.0 |
| keras | 3.15.0 |
| csbdeep | 0.8.2 |
| stardist | 0.9.2 |
| cellpose | 4.2.1.1 |
| torch | 2.12.1 |
| torchvision | 0.27.1 |
| napari | 0.7.1 |
| magicgui | 0.10.2 |
| pyqt6 | 6.10.2 / qtpy 2.4.3 |
| numba | 0.65.1 |

## Smoke-test results (each import checked in isolation)

| check | result |
|---|---|
| venv arch | `arm64` ✅ |
| `import tensorflow` | 2.21.0 ✅ (CPU; Keras 3) |
| `torch.backends.mps.is_available()` | **True** ✅ (Metal) |
| `from cellpose import models` + `CellposeModel` | available ✅ |
| StarDist `2D_versatile_fluo` | available ✅ (validated in Phase 0) |
| `import napari` (qt binding) | PyQt6, napari 0.7.1 ✅ |

All three backends (TensorFlow/StarDist, PyTorch/Cellpose, napari/Qt) are available on this
machine. No backend had to be disabled.

## Platform notes

- **CPU vs MPS:** TensorFlow runs on CPU here (fine for single-image StarDist inference).
  PyTorch/Cellpose uses **MPS (Metal)** automatically when `gpu=True`. We do not install
  `tensorflow-metal` (optional, Python-3.11-bound, unnecessary for counting).
- **Keras 3:** StarDist 0.9.2 supports Keras 3 natively. Do **not** set
  `TF_USE_LEGACY_KERAS` or install `tf-keras`.
- **One Qt binding only:** install PyQt6 only. Mixing PyQt5 + PyQt6 breaks `qtpy`.
- **Conda:** the local Anaconda install is broken (`conda-build` entry-point error) and is
  not used. `uv` + PyPI wheels replace it entirely.

## Model weight downloads (first run)

First inference downloads pretrained weights:

- **StarDist** `2D_versatile_fluo` (~5 MB) from **github.com** — works here.
- **Cellpose** `cpsam_v2` from **huggingface.co** — this host is **unreachable from the
  build network** (TLS connection reset, even outside the sandbox; DNS resolves fine). So
  Cellpose weights could not be fetched during Phase 0. Options to obtain them:
  - Run on a network with HuggingFace access (the weights cache to `~/.cellpose/models/`).
  - Or set a mirror before running: `export HF_ENDPOINT=https://hf-mirror.com`.
  - Or manually place `cpsam_v2` in `~/.cellpose/models/` from
    `https://huggingface.co/mouseland/cellpose-sam`.

## Graceful degradation (design rule for Phase 1)

If a backend import fails on another machine, the app must **drop that model from
`list_models()`** rather than crash — Phase 0's `scripts/phase0_validate.py` already wraps
each backend in try/except and reports an unavailable backend instead of aborting.
