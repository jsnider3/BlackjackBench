#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


Cell = Tuple[str, str, str]  # (p1, p2, du)
Key = Tuple[str, str, str, int]  # (p1, p2, du, rep)


def grid_weights_infinite_deck() -> Dict[Cell, float]:
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    pr = {r: (4/13 if r == "10" else 1/13) for r in ranks}
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
    pd = {d: pr[d] for d in dealer_up}
    weights: Dict[Cell, float] = {}
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:  # combinations with repetition for player cards
            p_player = (pr[r1] ** 2) if r1 == r2 else (2 * pr[r1] * pr[r2])
            for du in dealer_up:
                weights[(r1, r2, du)] = p_player * pd[du]
    return weights


def discover_files(inputs: List[str]) -> List[Path]:
    files: List[Path] = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            files.extend(sorted(p.glob("*.jsonl")))
        elif any(ch in inp for ch in "*?["):
            files.extend(sorted(Path().glob(inp)))
        else:
            files.append(p)
    # Deduplicate while preserving order
    out: List[Path] = []
    seen = set()
    for f in files:
        if f.exists() and f.suffix == ".jsonl" and f not in seen:
            out.append(f)
            seen.add(f)
    return out


def load_events(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


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
            def norm(r: str) -> str:
                return "10" if r in {"10", "J", "Q", "K"} else r
            w = weights.get((norm(r1), norm(r2), norm(du)), 0.0)
        weighted_return += avg * w
        sum_w += w
        cells_covered += 1

    # Unweighted EV over executed hands (for reference)
    total_hands = len(per_hand)
    ev_unweighted = (sum(per_hand.values()) / total_hands) if total_hands else 0.0
    mistake_rate = (mistakes / decisions) if decisions else 0.0

    # Extract a short model tag from filename
    name = path.name
    model = name
    parts = name.split("_")
    # heuristic: last segment without extension often contains the model
    try:
        model = parts[-1].rsplit(".", 1)[0]
    except Exception:
        pass

    return {
        "file": str(path),
        "model": model,
        "ev_weighted": weighted_return if sum_w else 0.0,
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
    # Pretty print compact table
    headers = ["model", "ev_weighted", "sum_weights", "cells_covered", "hands", "mistake_rate", "file"]
    def fmt(x):
        if isinstance(x, float):
            return f"{x:.6f}"
        return str(x)
    # widths
    widths = {h: max(len(h), max(len(fmt(r.get(h, ''))) for r in rows)) for h in headers}
    print("  ".join(h.ljust(widths[h]) for h in headers))
    for r in rows:
        vals = [fmt(r.get(h, '')) for h in headers]
        print("  ".join(vals[i].ljust(widths[headers[i]]) for i in range(len(headers))))


if __name__ == "__main__":
    main()
