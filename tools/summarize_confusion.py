#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from typing import Dict, Iterable, List


# Preferred display order; actual columns/rows are intersected with observed actions
PREF_ORDER: List[str] = ["HIT", "STAND", "DOUBLE", "SPLIT", "SURRENDER"]


def load_events(path: str) -> Iterable[dict]:
    with (open(path, "r", encoding="utf-8") if path != "-" else sys.stdin) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def confusion(path: str, track: str | None = None):
    """Return mapping baseline_action -> Counter(agent_action -> count) for one file."""
    conf: Dict[str, Counter] = defaultdict(Counter)
    total = 0
    mistakes = 0
    observed: set[str] = set()
    for ev in load_events(path):
        if track and ev.get("track") != track:
            continue
        a = ev.get("agent_action")
        b = ev.get("baseline_action")
        if not a or not b:
            continue
        conf[b][a] += 1
        observed.add(a)
        observed.add(b)
        total += 1
        if a != b:
            mistakes += 1
    return conf, total, mistakes, observed


def print_table(conf: Dict[str, Counter], total: int, mistakes: int, observed: set[str], *, csv: str | None = None) -> None:
    # Build row/col labels from observed actions, preserve preferred order, drop zero-only actions like SURRENDER when unused
    base = [a for a in PREF_ORDER if a in observed]
    extra = sorted(a for a in observed if a not in set(PREF_ORDER))
    cols = base + extra
    rows = cols
    # Header
    header = ["baseline\\agent"] + cols + ["row_total", "row_mistake_rate"]
    table = [header]
    for r in rows:
        ctr = conf.get(r, Counter())
        row = [r]
        row_total = 0
        row_correct = ctr.get(r, 0)
        for c in cols:
            v = ctr.get(c, 0)
            row.append(str(v))
            row_total += v
        mr = (1 - (row_correct / row_total)) if row_total else 0.0
        row.append(str(row_total))
        row.append(f"{mr:.3f}")
        table.append(row)
    # Totals
    total_row = ["total"]
    col_totals = [sum(conf.get(r, Counter()).get(c, 0) for r in rows) for c in cols]
    total_row += [str(v) for v in col_totals] + [str(total), f"{(mistakes/total if total else 0):.3f}"]
    table.append(total_row)

    # Print table
    widths = [max(len(row[i]) for row in table) for i in range(len(table[0]))]
    for row in table:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    if csv:
        import csv as _csv
        with open(csv, "w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh)
            for row in table:
                writer.writerow(row)
        print(f"wrote CSV to {csv}")


def main():
    ap = argparse.ArgumentParser(description="Summarize confusion matrix from JSONL logs.")
    ap.add_argument("paths", nargs="+", help="JSONL event files or '-' for stdin")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default=None)
    ap.add_argument("--csv", help="Optional output CSV path (only when a single input is provided)")
    ap.add_argument("--merge", action="store_true", help="Merge all inputs into one matrix (previous behavior)")
    args = ap.parse_args()

    if args.merge or len(args.paths) == 1:
        # Single matrix across all inputs
        merged_conf: Dict[str, Counter] = defaultdict(Counter)
        merged_total = 0
        merged_mistakes = 0
        merged_observed: set[str] = set()
        for p in args.paths:
            conf, total, mistakes, observed = confusion(p, args.track)
            for b, ctr in conf.items():
                for a, v in ctr.items():
                    merged_conf[b][a] += v
            merged_total += total
            merged_mistakes += mistakes
            merged_observed.update(observed)
        print_table(merged_conf, merged_total, merged_mistakes, merged_observed, csv=args.csv)
        return

    # Print a matrix per file
    for i, p in enumerate(args.paths):
        print(f"# {p}")
        conf, total, mistakes, observed = confusion(p, args.track)
        print_table(conf, total, mistakes, observed, csv=(args.csv if len(args.paths) == 1 else None))
        if i != len(args.paths) - 1:
            print()


if __name__ == "__main__":
    main()
