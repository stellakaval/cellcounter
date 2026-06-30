# Research notes & design rationale

Captured knowledge behind cellcounter's design — the real Fiji workflow it replaces, what
scientists say is wrong with the status quo, the StarDist-in-Fiji friction we eliminate, and
the environment/network findings on the target machine. Sources are linked inline.

## 1. The manual Fiji workflow we're replacing

The target user (a wet-lab scientist) currently counts nuclei in Fiji/ImageJ via a fragile,
order-dependent, per-image, per-channel pipeline:

1. `Image → Adjust → Brightness/Contrast → Auto` — just to *see* the dim signal.
2. `Process → Filters → Gaussian Blur` (σ ~1–3) — smooth jagged edges; too much merges cells.
3. `Image → Adjust → Threshold` — intensity threshold, **Otsu**, but "very sus", per-image,
   trial-and-error.
4. `Process → Binary → Convert to Mask` — binarize.
5. `Process → Binary → Watershed` — split touching cells (creates "sussy small" artifacts).
6. `Analyze → Analyze Particles` with a **size filter in µm²** — count, drop background/specks.
7. Repeat for the 2nd channel; cross-compare via the **ROI Manager** (Show All + labels).

Stated pain: thresholds differ per image, watershed mis-splits and invents tiny objects, the
size filter is trial-and-error, and applying filters means **reopening the file from scratch**.
The macro (`Plugins → Macros → Run`) batches it but is brittle.

**Key insight:** steps 1–6 are a hand-built instance segmentation. A pretrained AI model
(StarDist) does this in one shot, so we *retire* steps 2–5 entirely and keep only the
scientifically meaningful knobs (size µm², circularity) as live, non-destructive filters.

## 2. What scientists actually want (sentiment research)

Synthesized from the image.sc forum, Reddit (r/labrats, r/microscopy), and the literature:

- **Threshold subjectivity / irreproducibility is the #1 complaint.** Different people pick
  different cutoffs → "markedly different" counts; 10–40% count-to-count variability.
  [Quanty-cFOS](https://pmc.ncbi.nlm.nih.gov/articles/PMC10000431/)
- **Watershed brittleness** on touching/clumped nuclei is a recurring, unsolved forum topic.
  [image.sc](https://forum.image.sc/t/best-way-to-segment-clumped-nuclei-better-segmentation-or-just-clump-splitting-in-any-tool/57865)
- **One-click automation** with sensible defaults is "strongly required"; no parameter dialogs.
- **Human-in-the-loop correction is non-negotiable for trust** — adoption stalls on black
  boxes. Tools that let users toggle/merge/draw masks visually (no code) succeed.
  [Toggle-Untoggle](https://pmc.ncbi.nlm.nih.gov/articles/PMC12669964/)
- **Install / GPU / environment pain** blocks AI-tool adoption (conda, CUDA, "Cellpose runs on
  CPU on my M1"). [image.sc GPU threads](https://forum.image.sc/t/how-to-run-cellpose-through-gpu-on-mac-ios-m1/104423)
- AI tools (StarDist/Cellpose) are wanted but still need correction, still confuse users with
  model/diameter/threshold choices. [Usability study](https://pmc.ncbi.nlm.nih.gov/articles/PMC11495889/)

## 3. StarDist-in-Fiji: what it fixes and what it leaves broken

Source: [imagej.net/plugins/stardist](https://imagej.net/plugins/stardist), [stardist.net/faq](https://stardist.net/faq/).

It replaces threshold+watershed with a learned star-convex nuclei detector (models
`2D_versatile_fluo` for fluorescence, `2D_versatile_he` for H&E), outputs a label image and/or
ROI Manager ROIs, and lets users delete/add/edit ROIs and re-measure. Good — but the friction
it *leaves*, which we eliminate:

- Confusing command dialog: normalization percentiles, **probability/score threshold**,
  **overlap/NMS threshold**, **n_tiles**, output type → we collapse to **one sensitivity
  slider** (→ `prob_thresh`), auto-normalization, auto-tiling.
- **No built-in µm² size filter; no measurement table/CSV** → we provide both.
- **Awkward batch** (macro/`Command From Macro`, ROI-Manager state juggling) → folder → one CSV.
- **Silent accuracy loss off ~0.5 µm/px** → we auto-rescale to ~0.5 µm/px and show pixel size.
- **Multi-step TensorFlow update-site install**, protobuf/version breakage, and **no Apple-
  Silicon support at all** in Fiji → our Python StarDist runs natively on M1 (see §5).

## 4. Design decisions (Fiji friction → cellcounter)

| Fiji pain | cellcounter |
|---|---|
| Subjective per-image Otsu threshold | AI segments; no threshold dialog |
| Watershed over/under-splits | StarDist separates instances natively |
| Trial-and-error size filter, reopen file | live, non-destructive min/max µm² + circularity |
| StarDist dialog soup (norm/prob/NMS/tiles) | one **sensitivity** slider; rest automatic |
| Off-0.5 µm/px degradation | auto-rescale to ~0.5 µm/px; show pixel size |
| No CSV / table | auto per-cell + summary CSV |
| Per-channel colocalization is manual | built-in EdU% / PDGFRa-gated readouts |
| Black box → distrust | contrast slider + overlay + brush-edit + live recount |
| Brittle batch macros | folder → one combined CSV |
| Fiji-StarDist won't run on M1 | our Python StarDist does |

The three lab readouts to support: per-channel counts, **% EdU+ nuclei**, **% EdU+ within
PDGFRa+ OPCs** (marker positivity = mean intensity in/around each segmented nucleus vs an
adjustable threshold).

## 5. Environment & network findings (target machine: Apple M1 Pro, arm64)

- **Must use a native arm64 Python** (uv-managed 3.11.15). The machine's default `python3.11`
  is Anaconda **x86_64** → a Rosetta venv with no TensorFlow wheel and no MPS. See
  `env/environment.md`. Verified stack: TF 2.21.0 (Keras 3), torch 2.12.1 + **MPS True**,
  stardist 0.9.2, cellpose 4.2.1.1, napari 0.7.1 (PyQt6).
- **HuggingFace access is network-dependent.** On the original network, `huggingface.co` was
  **SNI-blocked**: TCP to `:443` connected but the TLS handshake was reset the moment the SNI
  hostname appeared (plain HTTP/80 reset too) — a network middlebox, not a code bug. On a
  later (faster) network the TLS handshake succeeded and the official weights downloaded
  normally. So if Cellpose weights won't download, it's the network, not the tool.
- **Cellpose is now enabled.** The official `cpsam_v2` (~1.23 GB, Cellpose-SAM) was fetched
  from `huggingface.co/mouseland/cellpose-sam` into `~/.cellpose/models/` and validated:
  `list_models()` returns both, and on `E4_LDHi_1_5` StarDist→21 vs Cellpose-SAM→19.
- **Default model = StarDist.** Validated on the real DAPI `.czi` images (Phase 0), runs on M1.
  **Cellpose-SAM is now selectable too** (auto-enabled because its weights are present). Note
  Cellpose hardcodes the huggingface.co URL, so `HF_ENDPOINT` won't redirect it — fetch the
  weights from the official source on an unfiltered network if moving to another machine.

## 6. Real data format (Phase 0)

Zeiss `.czi` (`czifile`), axes `HTCZYX0`, uint8. **Channel 0 = DAPI** (nuclei to count); other
channels are EdU-594 / 488-PDGFRa. Some files are Z-stacks (max-project). Pixel size in
metadata `<Distance Id="X">` (m/px): ~0.62 µm/px @512², ~0.124 µm/px @2586² (same ~320 µm FOV).
Phase 0 result: StarDist `2D_versatile_fluo` segments these cleanly (synthetic: exact 25/20;
real: clean overlays on 512² and 2586², E3/E4). **No fine-tuning (Phase 3) needed.**
