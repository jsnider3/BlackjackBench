#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List, Tuple


def read_confusion_csv(path: Path) -> Tuple[List[str], List[str], List[List[int]]]:
    rows: List[str] = []
    cols: List[str] = []
    data: List[List[int]] = []
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header:
            raise SystemExit("Empty CSV")
        # header: baseline\agent, HIT, STAND, DOUBLE, SPLIT, row_total, row_mistake_rate
        # columns are from index 1..N until we hit row_total
        try:
            end_idx = header.index("row_total")
        except ValueError:
            end_idx = len(header)
        cols = header[1:end_idx]
        for line in reader:
            if not line:
                continue
            if line[0] in ("total", "baseline\\agent"):
                continue
            rname = line[0]
            rows.append(rname)
            vals = [int(line[i]) for i in range(1, 1 + len(cols))]
            data.append(vals)
    return rows, cols, data


def color_scale(value: float) -> str:
    """Map 0..1 to a red-scale hex color (white->red)."""
    # simple linear scale: white (255) to red (255, 0, 0) via green/blue decreasing
    value = max(0.0, min(1.0, value))
    r = 255
    g = int(255 * (1.0 - value))
    b = int(255 * (1.0 - value))
    return f"#{r:02x}{g:02x}{b:02x}"


def render_svg(rows: List[str], cols: List[str], data: List[List[int]], out: Path, title: str | None = None) -> None:
    n_rows = len(rows)
    n_cols = len(cols)
    # compute max for normalization (exclude diagonal dominance if desired)
    max_val = max((v for row in data for v in row), default=1) or 1

    cell_w = 48
    cell_h = 36
    pad_l = 120
    pad_t = 60
    pad_r = 20
    pad_b = 60
    width = pad_l + n_cols * cell_w + pad_r
    height = pad_t + n_rows * cell_h + pad_b

    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts: List[str] = []
    parts.append(f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>")
    parts.append("<style> .lbl{font: 12px sans-serif; fill:#333} .title{font: 14px sans-serif; font-weight:600} .val{font: 11px monospace; fill:#111} </style>")
    if title:
        parts.append(f"<text class='title' x='{pad_l}' y='24'>{esc(title)}</text>")

    # column labels
    for j, c in enumerate(cols):
        x = pad_l + j * cell_w + cell_w / 2
        parts.append(f"<text class='lbl' x='{x}' y='{pad_t - 12}' text-anchor='middle'>{esc(c)}</text>")
    # row labels
    for i, r in enumerate(rows):
        y = pad_t + i * cell_h + cell_h / 2 + 4
        parts.append(f"<text class='lbl' x='{pad_l - 8}' y='{y}' text-anchor='end'>{esc(r)}</text>")

    # cells
    for i in range(n_rows):
        for j in range(n_cols):
            v = data[i][j]
            frac = (v / max_val) if max_val else 0.0
            fill = color_scale(frac)
            x = pad_l + j * cell_w
            y = pad_t + i * cell_h
            parts.append(f"<rect x='{x}' y='{y}' width='{cell_w}' height='{cell_h}' fill='{fill}' stroke='#ccc' />")
            parts.append(f"<text class='val' x='{x + cell_w/2}' y='{y + cell_h/2 + 4}' text-anchor='middle'>{v}</text>")

    # axes titles
    parts.append(f"<text class='lbl' x='{pad_l + (n_cols*cell_w)/2}' y='{height - 20}' text-anchor='middle'>Agent action</text>")
    parts.append(f"<text class='lbl' x='20' y='{pad_t + (n_rows*cell_h)/2}' transform='rotate(-90,20,{pad_t + (n_rows*cell_h)/2})' text-anchor='middle'>Baseline action</text>")

    parts.append("</svg>")
    out.write_text("".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Generate an SVG heatmap from a confusion CSV produced by summarize_confusion.py")
    ap.add_argument("csv", help="Path to confusion CSV (from summarize_confusion.py)")
    ap.add_argument("--out", default="figures/confusion_heatmap.svg", help="Output SVG path")
    ap.add_argument("--title", default=None, help="Optional title text")
    args = ap.parse_args()

    p = Path(args.csv)
    rows, cols, data = read_confusion_csv(p)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_svg(rows, cols, data, out, title=args.title)
    print(f"wrote SVG to {out}")


if __name__ == "__main__":
    main()

