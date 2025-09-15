#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

DEALER_COLS = ["2","3","4","5","6","7","8","9","10","A"]


def read_per_cell_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        rows = list(r)
        return r.fieldnames or [], rows


def parse_models(headers: List[str]) -> List[str]:
    """Return all model columns present (exact column names)."""
    return [h for h in headers if h.startswith("avg_think_")]


def filter_model_cols(all_cols: List[str], selectors: Optional[List[str]]) -> List[str]:
    """Filter model columns by optional selectors.

    - If selectors is None or empty, return all_cols.
    - Matching rules (case-insensitive):
      * Accept exact column name (e.g., 'avg_think_gpt-5-nano-med-thinking')
      * Accept suffix after 'avg_think_' (e.g., 'gpt-5-nano-med-thinking')
      * Accept substring in suffix (e.g., 'nano', 'gpt-5 nano med')
    - Selectors can include spaces/underscores; they will be normalized to hyphens.
    """
    if not selectors:
        return list(all_cols)

    # Preprocess columns into (col, suffix_lower)
    suffix_map = {col: col[len("avg_think_"):].lower() for col in all_cols}

    def norm(s: str) -> str:
        return s.strip().lower().replace(" ", "-").replace("_", "-")

    wanted: List[str] = []
    sel_norm = [norm(s) for s in selectors if s and s.strip()]
    for col, suffix in suffix_map.items():
        for sel in sel_norm:
            # Accept exact column name
            if norm(col) == sel:
                wanted.append(col)
                break
            # Accept exact suffix
            if suffix == sel:
                wanted.append(col)
                break
            # Accept substring match in suffix
            if sel in suffix:
                wanted.append(col)
                break
    # Deduplicate preserving order of all_cols
    seen = set()
    filtered = []
    for col in all_cols:
        if col in wanted and col not in seen:
            filtered.append(col)
            seen.add(col)
    return filtered


def combined_avg(row: Dict[str, str], model_cols: List[str]) -> float | None:
    vals: List[float] = []
    for m in model_cols:
        v = (row.get(m) or "").strip()
        if not v:
            continue
        try:
            vals.append(float(v))
        except ValueError:
            continue
    if not vals:
        return None
    return sum(vals) / len(vals)


def build_grids(rows: List[Dict[str, str]], model_cols: List[str]) -> Tuple[Dict[Tuple[int,str], float], Dict[Tuple[int,str], float], Dict[Tuple[str,str], float]]:
    """Return (hard_grid, soft_grid, pair_grid) mapping (row_label, dealer)->avg.
    - hard_grid: key (total:int, dealer)
    - soft_grid: key (total:int, dealer)
    - pair_grid: key (pair_label:str like 'A/A', dealer)
    """
    hard: Dict[Tuple[int,str], float] = {}
    soft: Dict[Tuple[int,str], float] = {}
    pairs: Dict[Tuple[str,str], float] = {}

    # We will average across duplicates if any (shouldn't be for per-cell first decisions)
    acc_h: Dict[Tuple[int,str], List[float]] = {}
    acc_s: Dict[Tuple[int,str], List[float]] = {}
    acc_p: Dict[Tuple[str,str], List[float]] = {}

    for row in rows:
        p1 = row.get("p1")
        p2 = row.get("p2")
        du = row.get("dealer")
        cat = row.get("category") or ""
        du = du if du in DEALER_COLS else None
        if not (p1 and p2 and du):
            continue
        avg = combined_avg(row, model_cols)
        if avg is None:
            continue
        if cat.startswith("pair "):
            pair_label = f"{p1}/{p2}"
            acc_p.setdefault((pair_label, du), []).append(avg)
        elif cat.startswith("soft "):
            try:
                total = int(cat.split()[1])
            except Exception:
                continue
            acc_s.setdefault((total, du), []).append(avg)
        elif cat.startswith("hard "):
            try:
                total = int(cat.split()[1])
            except Exception:
                continue
            acc_h.setdefault((total, du), []).append(avg)

    # Aggregate to mean
    for k, vals in acc_h.items():
        hard[k] = sum(vals) / len(vals)
    for k, vals in acc_s.items():
        soft[k] = sum(vals) / len(vals)
    for k, vals in acc_p.items():
        pairs[k] = sum(vals) / len(vals)

    return hard, soft, pairs


def write_grid_csv(path: Path, title_rows: List[Any], grid: Dict[Tuple[Any,str], float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        header = ["player\\dealer"] + DEALER_COLS
        w.writerow(header)
        for rl in title_rows:
            row = [str(rl)]
            for du in DEALER_COLS:
                v = grid.get((rl, du))
                row.append(f"{v:.1f}" if isinstance(v, (int, float)) else "")
            w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Build combined thinking-load grids (hard/soft/pairs) from per-cell CSV")
    ap.add_argument("--per-cell", default="figures/thinking_load_by_cell.csv", help="Input per-cell CSV from aggregate_thinking.py")
    ap.add_argument("--out-dir", default="figures", help="Output directory for grid CSVs and SVGs")
    ap.add_argument("--no-svg", action="store_true", help="Do not render SVG heatmaps")
    ap.add_argument("--models", help="Comma-separated model names or substrings to include (matches columns after 'avg_think_'). Default: all models")
    args = ap.parse_args()

    headers, rows = read_per_cell_csv(Path(args.per_cell))
    all_model_cols = parse_models(headers)
    if not all_model_cols:
        raise SystemExit("No avg_think_* columns found in input CSV")

    # Filter by requested models (if any)
    selectors = None
    if args.models:
        selectors = [s.strip() for s in args.models.split(",") if s.strip()]
    model_cols = filter_model_cols(all_model_cols, selectors)
    if not model_cols:
        # Build helpful error message listing available suffixes
        available = ", ".join(col[len("avg_think_"):] for col in all_model_cols)
        raise SystemExit(f"No models matched --models='{args.models}'. Available: {available}")

    hard, soft, pairs = build_grids(rows, model_cols)

    # Determine row labels
    hard_rows = sorted({k[0] for k in hard.keys()})
    soft_rows = sorted({k[0] for k in soft.keys()})
    # Pairs: collect unique pair labels in canonical order (A,2,...,10)
    order = ["A","2","3","4","5","6","7","8","9","10"]
    pair_labels = [f"{r}/{r}" for r in order if any(k[0] == f"{r}/{r}" for k in pairs.keys())]

    out_dir = Path(args.out_dir)
    hard_csv = out_dir / "thinking_hard_grid.csv"
    soft_csv = out_dir / "thinking_soft_grid.csv"
    pairs_csv = out_dir / "thinking_pairs_grid.csv"
    write_grid_csv(hard_csv, hard_rows, hard)
    write_grid_csv(soft_csv, soft_rows, soft)
    write_grid_csv(pairs_csv, pair_labels, pairs)
    print(f"Wrote grids: {hard_csv}, {soft_csv}, {pairs_csv}")

    if not args.no_svg:
        # Render simple heatmaps using a local function (float-aware)
        def render_heatmap(csv_path: Path, out_svg: Path, title: str) -> None:
            import math
            # Read back the CSV
            with csv_path.open("r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                header = next(reader)
                cols = header[1:]
                row_labels: List[str] = []
                data: List[List[float]] = []
                for row in reader:
                    row_labels.append(row[0])
                    vals: List[float] = []
                    for x in row[1:]:
                        try:
                            vals.append(float(x))
                        except Exception:
                            vals.append(0.0)
                    data.append(vals)
            # Normalize by max value
            max_val = max((v for r in data for v in r), default=1.0) or 1.0
            cell_w, cell_h = 48, 28
            pad_l, pad_t, pad_r, pad_b = 120, 48, 20, 40
            width = pad_l + len(cols)*cell_w + pad_r
            height = pad_t + len(row_labels)*cell_h + pad_b
            def color_scale(v: float) -> str:
                frac = 0.0 if max_val <= 0 else max(0.0, min(1.0, v/max_val))
                # white to blue gradient
                r = int(255 * (1.0 - 0.5*frac))
                g = int(255 * (1.0 - 0.7*frac))
                b = 255
                return f"#{r:02x}{g:02x}{b:02x}"
            def esc(t: str) -> str:
                return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            parts: List[str] = []
            parts.append(f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>")
            # Light/dark mode aware styles and background
            parts.append(
                "<style>"
                " .lbl{font: 12px sans-serif; fill:#333}"
                " .title{font: 14px sans-serif; font-weight:600; fill:#222}"
                " .val{font: 11px monospace; fill:#111; paint-order: stroke fill; stroke: rgba(255,255,255,0.6); stroke-width: 1.2px;}"
                " .cell{stroke:#ccc}"
                " .bg{fill:#fff}"
                " @media (prefers-color-scheme: dark){"
                "  .lbl{fill:#eee} .title{fill:#eee} .val{fill:#f8f8f8; stroke: rgba(0,0,0,0.6);}"
                "  .cell{stroke:#555} .bg{fill:#111}"
                " }"
                "</style>"
            )
            parts.append(f"<text class='title' x='{pad_l}' y='22'>{esc(title)}</text>")
            # Background
            parts.append(f"<rect class='bg' x='0' y='0' width='{width}' height='{height}' />")
            # col labels
            for j, c in enumerate(cols):
                x = pad_l + j*cell_w + cell_w/2
                parts.append(f"<text class='lbl' x='{x}' y='{pad_t - 10}' text-anchor='middle'>{esc(c)}</text>")
            # row labels
            for i, rlbl in enumerate(row_labels):
                y = pad_t + i*cell_h + cell_h/2 + 4
                parts.append(f"<text class='lbl' x='{pad_l - 8}' y='{y}' text-anchor='end'>{esc(rlbl)}</text>")
            # cells
            for i, row_vals in enumerate(data):
                for j, v in enumerate(row_vals):
                    x = pad_l + j*cell_w
                    y = pad_t + i*cell_h
                    fill = color_scale(v)
                    parts.append(f"<rect class='cell' x='{x}' y='{y}' width='{cell_w}' height='{cell_h}' fill='{fill}' />")
                    parts.append(f"<text class='val' x='{x + cell_w/2}' y='{y + cell_h/2 + 4}' text-anchor='middle'>{v:.0f}</text>")
            parts.append("</svg>")
            out_svg.parent.mkdir(parents=True, exist_ok=True)
            out_svg.write_text("".join(parts), encoding="utf-8")
            print(f"Wrote SVG to {out_svg}")

        # Compose model descriptor for titles; if single model, label explicitly
        suffixes = ", ".join(col[len("avg_think_"):] for col in model_cols)
        if len(model_cols) == 1:
            tag = f"Model: {suffixes}"
            render_heatmap(hard_csv, out_dir/"thinking_hard_grid.svg", f"Thinking load — Hard totals (chars) — {tag}")
            render_heatmap(soft_csv, out_dir/"thinking_soft_grid.svg", f"Thinking load — Soft totals (chars) — {tag}")
            render_heatmap(pairs_csv, out_dir/"thinking_pairs_grid.svg", f"Thinking load — Pairs (chars) — {tag}")
        else:
            tag = f"Average across models: {suffixes}"
            render_heatmap(hard_csv, out_dir/"thinking_hard_grid.svg", f"Average thinking load — Hard totals (chars) — {tag}")
            render_heatmap(soft_csv, out_dir/"thinking_soft_grid.svg", f"Average thinking load — Soft totals (chars) — {tag}")
            render_heatmap(pairs_csv, out_dir/"thinking_pairs_grid.svg", f"Average thinking load — Pairs (chars) — {tag}")


if __name__ == "__main__":
    main()
