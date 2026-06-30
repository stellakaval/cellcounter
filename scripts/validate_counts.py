"""Validate AI nucleus counts against a ground-truth spreadsheet.

Compares cellcounter's counts (StarDist + a minimum-size filter) to hand-verified counts in
an .xlsx (default: ``Book.xlsx`` with Sheet1 = [filename, correct_count, EdU+, %EdU+]). Reads
the .xlsx with the standard library only (it's a zip of XML), so no extra dependency.

Usage:
    python scripts/validate_counts.py --folder ~/Desktop/cellsamples \
        --truth ~/Desktop/Book.xlsx --min-um2 30 [--max N] [--out compare.csv]

Prints an accuracy summary (over/under, mean abs error, % within ±2 / ±3, AI/truth ratio)
and writes a per-file ``image, ai, truth, error`` CSV. This is the regression check for
counting accuracy — re-run it after any change to segmentation or the size default.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from cellcounter import io, measure, segment

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_ground_truth(xlsx: Path) -> dict[str, int]:
    """Read Sheet1 of an .xlsx → {filename_stem: correct_count} (cols A=name, B=count)."""
    z = zipfile.ZipFile(xlsx)
    shared = [
        "".join(t.text or "" for t in si.iter(f"{_NS}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS}si")
    ]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    gt: dict[str, int] = {}
    for row in sheet.findall(f".//{_NS}row"):
        cells = {}
        for c in row.findall(f"{_NS}c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find(f"{_NS}v")
            val = v.text if v is not None else None
            if c.get("t") == "s" and val is not None:
                val = shared[int(val)]
            cells[col] = val
        if cells.get("A") and cells.get("B"):
            gt[str(cells["A"]).replace(".czi", "")] = int(float(cells["B"]))
    return gt


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate AI counts vs ground truth.")
    ap.add_argument("--folder", type=Path, required=True, help="Folder of images to count.")
    ap.add_argument("--truth", type=Path, default=Path.home() / "Desktop" / "Book.xlsx")
    ap.add_argument("--min-um2", type=float, default=30.0)
    ap.add_argument("--sensitivity", type=float, default=0.5)
    ap.add_argument("--max", type=int, default=0, help="Validate only the first N matches.")
    ap.add_argument("--out", type=Path, default=Path("count_comparison.csv"))
    args = ap.parse_args()

    gt = read_ground_truth(args.truth)
    keys = sorted(gt)
    if args.max:
        keys = keys[: args.max]
    print(f"Validating {len(keys)} files against {args.truth.name} (min {args.min_um2} µm²)\n")

    rows = []
    for i, k in enumerate(keys, 1):
        path = args.folder / f"{k}.czi"
        if not path.exists():
            continue
        img = io.load_image(path)
        labels = segment.segment(img.nuclei(), segment.STARDIST, args.sensitivity, img.pixel_um)
        ai = measure.count(labels, img.pixel_um, min_um2=args.min_um2)
        rows.append({"image": k, "ai": ai, "truth": gt[k], "error": ai - gt[k]})
        if i % 20 == 0:
            print(f"  {i}/{len(keys)}")

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    err = df["error"].to_numpy()
    print("\n=== accuracy ===")
    print(f"files: {len(df)}")
    print(f"AI total {df.ai.sum()} vs truth {df.truth.sum()}  (ratio {df.ai.sum()/df.truth.sum():.3f})")
    print(f"mean abs error: {np.abs(err).mean():.2f}  |  mean signed: {err.mean():+.2f}")
    print(f"within ±2: {(np.abs(err) <= 2).mean()*100:.0f}%   within ±3: {(np.abs(err) <= 3).mean()*100:.0f}%")
    print(f"over: {(err > 0).sum()}  exact: {(err == 0).sum()}  under: {(err < 0).sum()}")
    print(f"\nper-file comparison written to {args.out}")


if __name__ == "__main__":
    main()
