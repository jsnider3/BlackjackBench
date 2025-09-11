#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict

from common import (
    Cell, Key, grid_weights_infinite_deck, discover_files, 
    load_events, norm_rank, extract_model_name, safe_float_format
)


def summarize_file(path: Path) -> dict:
    weights = grid_weights_infinite_deck()
    # Track per (cell, rep) reward; ignore duplicate events within the same hand
    per_hand: Dict[Key, float] = {}
    # Also accumulate decision/mistake counts for context
    decisions = 0
    mistakes = 0
    for ev in load_events(path):
        if ev.get("track") != "policy-grid":
            continue
        cell = ev.get("cell") or {}
        rep = ev.get("rep")
        if not isinstance(rep, int):
            continue
        p1, p2, du = cell.get("p1"), cell.get("p2"), cell.get("du")
        if not (isinstance(p1, str) and isinstance(p2, str) and isinstance(du, str)):
            continue
        key: Key = (p1, p2, du, rep)
        # Grab final.reward once per hand
        if key not in per_hand:
            final = ev.get("final") or {}
            reward = final.get("reward")
            if isinstance(reward, (int, float)):
                per_hand[key] = float(reward)
        # Decision and mistake counters
        a = ev.get("agent_action")
        b = ev.get("baseline_action")
        if isinstance(a, str) and isinstance(b, str):
            decisions += 1
            if a != b:
                mistakes += 1

    # Aggregate to per-cell averages across reps
    by_cell: Dict[Cell, List[float]] = defaultdict(list)
    for (p1, p2, du, _rep), rew in per_hand.items():
        by_cell[(p1, p2, du)].append(rew)

    # Weighted EV over available cells
    weighted_return = 0.0
    sum_w = 0.0
    cells_covered = 0
    for cell, rewards in by_cell.items():
        if not rewards:
            continue
        avg = sum(rewards) / len(rewards)
        w = weights.get(cell)
        if w is None:
            # Normalize face cards to '10' if necessary (defensive)
            r1, r2, du = cell
            w = weights.get((norm_rank(r1), norm_rank(r2), norm_rank(du)), 0.0)
        weighted_return += avg * w
        sum_w += w
        cells_covered += 1

    # Unweighted EV over executed hands (for reference)
    total_hands = len(per_hand)
    ev_unweighted = (sum(per_hand.values()) / total_hands) if total_hands else 0.0
    mistake_rate = (mistakes / decisions) if decisions else 0.0

    # Extract model name from filename
    model = extract_model_name(path)

    return {
        "file": str(path),
        "model": model,
        "ev_weighted": (weighted_return / sum_w) if sum_w else 0.0,
        "sum_weights": sum_w,
        "cells_covered": cells_covered,
        "hands": total_hands,
        "ev_unweighted": ev_unweighted,
        "decisions": decisions,
        "mistake_rate": mistake_rate,
    }


def main():
    ap = argparse.ArgumentParser(description="Summarize weighted EV from policy-grid JSONL logs.")
    ap.add_argument("inputs", nargs="*", default=["baselines"], help="Files, directories, or globs (default: baselines)")
    ap.add_argument("--track", choices=["policy-grid"], default="policy-grid", help="Track to summarize (policy-grid only)")
    args = ap.parse_args()

    files = discover_files(args.inputs)
    if not files:
        print("No .jsonl files found.")
        return

    rows = [summarize_file(p) for p in files]
    
    # Format output table
    headers = ["model", "ev_weighted", "sum_weights", "cells_covered", "hands", "mistake_rate", "file"]
    
    def fmt(x):
        if isinstance(x, float):
            return safe_float_format(x)
        return str(x)
    
    table_rows = []
    for r in rows:
        table_rows.append([fmt(r.get(h, '')) for h in headers])
    
    # Print formatted table
    from common import format_table
    print(format_table(headers, table_rows))


if __name__ == "__main__":
    main()
