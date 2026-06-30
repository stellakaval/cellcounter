"""Validate the marker classifier against the Shiverer ground-truth spreadsheet.

The sheet ("RAW CELL COUNT") holds, per mouse row (col A = blinded ID n) × 12 regions, four
counts: PDGFRa+/EdU+, PDGFRa+/EdU-, ASPA+/EdU+, ASPA+/EdU- (region r → columns C..F shifted by
4 per region). Image files are named ``M{n} #{r} ...`` → mouse n, region r.

For each projection image we segment DAPI nuclei, classify each cell, and compare the four
category counts to the matching sheet cells. Prints per-category accuracy (Pearson r + mean
abs error) and writes a per-image comparison CSV.

Usage:
    python scripts/validate_classification.py --folder "~/Desktop/Immuno 060324" \
        --truth "~/Desktop/Data Analysis_Shiverer mice.xlsx" [--sheet 2] [--max N]
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from cellcounter import classify, io, segment

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_CATS = classify.CATEGORIES  # [PDGFRa+/EdU+, PDGFRa+/EdU-, ASPA+/EdU+, ASPA+/EdU-]


def _col_num(ref: str) -> int:
    """Cell ref like 'AB12' → 1-based column number."""
    letters = re.match(r"[A-Z]+", ref).group()
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def read_truth(xlsx: Path, sheet: int) -> dict[tuple[int, int], list[int]]:
    """{(mouse_n, region_r): [4 category counts]} from the RAW CELL COUNT sheet."""
    z = zipfile.ZipFile(xlsx)
    shared = [
        "".join(t.text or "" for t in si.iter(f"{_NS}t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS}si")
    ]
    root = ET.fromstring(z.read(f"xl/worksheets/sheet{sheet}.xml"))
    gt: dict[tuple[int, int], list[int]] = {}
    started = False
    for row in root.findall(f".//{_NS}row"):
        cells: dict[int, str] = {}
        for c in row.findall(f"{_NS}c"):
            v = c.find(f"{_NS}v")
            val = v.text if v is not None else None
            if c.get("t") == "s" and val is not None:
                val = shared[int(val)]
            cells[_col_num(c.get("r"))] = val
        a = cells.get(1)  # col A = blinded mouse id (the "FAKE N" sequential id)
        if a is None or not str(a).strip().isdigit():
            # Only read the FIRST table (RAW CELL COUNT). A later table (DENSITY, cells/mm²)
            # reuses the same id column with huge values — stop once data has ended.
            if started:
                break
            continue
        started = True
        n = int(a)
        if (n, 1) in gt:  # safety: keep the first table's rows only
            continue
        for r in range(1, 13):  # regions 1..12, each a 4-column block from col C (=3)
            start = 3 + (r - 1) * 4
            block = [cells.get(start + k) for k in range(4)]
            vals = [int(float(x)) for x in block if x not in (None, "")]
            if len(vals) == 4:
                gt[(n, r)] = vals
    return gt


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate marker classification vs ground truth.")
    ap.add_argument("--folder", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--sheet", type=int, default=2, help="RAW CELL COUNT sheet number.")
    ap.add_argument("--min-um2", type=float, default=30.0)
    ap.add_argument("--ring-um", type=float, default=2.0)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("classification_comparison.csv"))
    args = ap.parse_args()

    folder = args.folder.expanduser()
    gt = read_truth(args.truth.expanduser(), args.sheet)
    print(f"ground-truth (mouse,region) entries: {len(gt)}")

    # Only the 2D orthogonal-projection files, parsed for mouse n + region r.
    imgs = []
    for p in sorted(folder.iterdir()):
        m = re.match(r"M(\d+) #(\d+)", p.name)
        if m and "Orthogonal Projection" in p.name and p.suffix.lower() == ".czi":
            imgs.append((int(m.group(1)), int(m.group(2)), p))
    if args.max:
        imgs = imgs[: args.max]
    print(f"projection images: {len(imgs)}\n")

    rows = []
    for i, (n, r, p) in enumerate(imgs, 1):
        truth = gt.get((n, r))
        if truth is None:
            continue
        image = io.load_image(p)
        labels = segment.segment(image.nuclei(), segment.STARDIST, 0.5, image.pixel_um)
        counts = classify.classify_counts(
            labels, image, min_um2=args.min_um2, ring_um=args.ring_um
        )
        row = {"mouse": n, "region": r}
        for k, cat in enumerate(_CATS):
            row[f"ai_{cat}"] = counts[cat]
            row[f"gt_{cat}"] = truth[k]
        rows.append(row)
        if i % 20 == 0:
            print(f"  {i}/{len(imgs)}")

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"\nmatched images: {len(df)}")
    print("\ncategory                 AI total  GT total   Pearson r   mean abs err")
    for cat in _CATS:
        ai = df[f"ai_{cat}"].to_numpy(dtype=float)
        gtv = df[f"gt_{cat}"].to_numpy(dtype=float)
        r = np.corrcoef(ai, gtv)[0, 1] if len(df) > 1 and ai.std() and gtv.std() else float("nan")
        print(f"{cat:<22}  {ai.sum():8.0f}  {gtv.sum():8.0f}   {r:8.2f}   {np.abs(ai-gtv).mean():10.1f}")
    print(f"\nper-image comparison written to {args.out}")


if __name__ == "__main__":
    main()
