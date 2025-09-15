#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Any

from common import discover_files, load_events, norm_rank, RANK_ORDER, categorize_hand, extract_model_name


def compute_metric(meta: Dict[str, Any]) -> float:
    """
    Compute a comparable 'thinking load' metric per event.

    Preference order:
    1) Length of llm_thinking text in characters (if present)
    2) Output tokens (total_tokens - prompt_tokens) from llm_usage
    3) 0.0 when neither available
    """
    thinking = meta.get("llm_thinking")
    if isinstance(thinking, str) and thinking:
        return float(len(thinking))
    usage = meta.get("llm_usage") or {}
    prompt = usage.get("prompt_tokens")
    total = usage.get("total_tokens")
    try:
        if isinstance(total, (int, float)) and isinstance(prompt, (int, float)):
            return float(total) - float(prompt)
    except Exception:
        pass
    return 0.0


def main():
    ap = argparse.ArgumentParser(description="Aggregate 'thinking load' per starting cell across models (decision_idx==0 only)")
    ap.add_argument("inputs", nargs="+", help="JSONL files, directories, or globs (thinking runs)")
    ap.add_argument("--out-csv", default="figures/thinking_load_by_cell.csv", help="Output CSV path (wide format)")
    args = ap.parse_args()

    files = discover_files(args.inputs)
    if not files:
        raise SystemExit("No input files found")

    # Map: model -> cell(str) -> list[metric]
    per_model: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    # Also store readable labels
    cell_info: Dict[str, Tuple[str, str, str, str]] = {}

    for f in files:
        model = extract_model_name(Path(f))
        for ev in load_events(Path(f)):
            if ev.get("track") != "policy-grid":
                continue
            if ev.get("decision_idx") != 0:
                continue
            cell = ev.get("cell") or {}
            p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
            p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
            du = norm_rank(str(cell.get("du"))) if cell.get("du") else None
            if not (p1 and p2 and du):
                continue
            # sort player cards for consistency
            p1s, p2s = sorted([p1, p2], key=lambda x: RANK_ORDER.index(x))
            key = f"{p1s},{p2s},{du}"
            cat = categorize_hand(ev)
            metric = compute_metric(ev.get("meta") or {})
            per_model[model][key].append(metric)
            cell_info[key] = (p1s, p2s, du, cat)

    # Collect model list (columns)
    models = sorted(per_model.keys())

    # All cells observed across any model
    all_cells = sorted(cell_info.keys(), key=lambda k: (cell_info[k][3], cell_info[k][2], cell_info[k][0], cell_info[k][1]))

    # Ensure output directory exists
    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)

    with open(args.out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        header = ["p1", "p2", "dealer", "category"] + [f"avg_think_{m}" for m in models] + [f"n_{m}" for m in models]
        w.writerow(header)
        for key in all_cells:
            p1s, p2s, du, cat = cell_info[key]
            row: List[Any] = [p1s, p2s, du, cat]
            # Averages per model
            for m in models:
                vals = per_model[m].get(key) or []
                avg = (sum(vals) / len(vals)) if vals else None
                row.append(f"{avg:.1f}" if avg is not None else "")
            # Counts per model
            for m in models:
                row.append(len(per_model[m].get(key) or []))
            w.writerow(row)

    print(f"Wrote per-cell thinking load table to {args.out_csv}")
    print(f"Models included: {', '.join(models)}")


if __name__ == "__main__":
    main()

