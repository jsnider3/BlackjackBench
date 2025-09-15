#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

from common import format_table

# Optional baseline recomputation using current code
try:
    from blackjack_bench.types import Action as _ActionEnum, Observation as _Observation, HandView as _HandView
    from blackjack_bench.agents.basic import BasicStrategyAgent as _BasicStrategyAgent
    _HAVE_BENCH = True
except Exception:
    _HAVE_BENCH = False


# Preferred display order; actual columns/rows are intersected with observed actions
PREF_ORDER: List[str] = ["HIT", "STAND", "DOUBLE", "SPLIT", "SURRENDER"]


def load_events(path: str) -> Iterable[dict]:
    """
    Load JSONL events from file path or stdin.
    
    Args:
        path: File path or "-" for stdin
        
    Yields:
        Parsed JSON events, skipping malformed lines
        
    Note:
        This is a specialized version that handles stdin, 
        unlike the common.load_events which only handles Path objects.
    """
    with (open(path, "r", encoding="utf-8") if path != "-" else sys.stdin) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _obs_from_event(ev: dict) -> _Observation:
    obs = ev.get("obs") or {}
    p = obs.get("player", {})
    # Map string actions to enum
    allowed_raw = obs.get("allowed_actions", []) or []
    allowed = []
    for a in allowed_raw:
        try:
            allowed.append(_ActionEnum[a])
        except Exception:
            continue
    hv = _HandView(
        cards=list(p.get("cards", []) or []),
        total=int(p.get("total", 0) or 0),
        is_soft=bool(p.get("is_soft", False)),
        can_split=bool(p.get("can_split", False)),
        can_double=bool(p.get("can_double", False)),
    )
    return _Observation(
        player=hv,
        dealer_upcard=str(obs.get("dealer_upcard")),
        hand_index=int(obs.get("hand_index", 0) or 0),
        num_hands=int(obs.get("num_hands", 1) or 1),
        allowed_actions=allowed,
    )


def confusion(path: str, track: str | None = None, recompute_baseline: bool = False) -> tuple[Dict[str, Counter], int, int, set[str]]:
    """
    Generate confusion matrix data from JSONL events.
    
    Args:
        path: File path or "-" for stdin
        track: Filter to specific track (e.g., "policy-grid")
    
    Returns:
        Tuple of (confusion_matrix, total_decisions, total_mistakes, observed_actions)
        where confusion_matrix maps baseline_action -> Counter(agent_action -> count)
    """
    conf: Dict[str, Counter] = defaultdict(Counter)
    total = 0
    mistakes = 0
    observed: set[str] = set()
    
    # Optional agent for recomputing baseline decisions
    basic = _BasicStrategyAgent() if (recompute_baseline and _HAVE_BENCH) else None

    for ev in load_events(path):
        if track and ev.get("track") != track:
            continue
            
        a = ev.get("agent_action")
        if basic is not None:
            try:
                obs = _obs_from_event(ev)
                b = basic.act(obs, info={}).name
            except Exception:
                b = ev.get("baseline_action")
        else:
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
    
    # Build table data
    headers = ["baseline\\agent"] + cols + ["row_total", "row_mistake_rate"]
    table_rows = []
    
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
        table_rows.append(row)
    
    # Totals row
    total_row = ["total"]
    col_totals = [sum(conf.get(r, Counter()).get(c, 0) for r in rows) for c in cols]
    total_row += [str(v) for v in col_totals] + [str(total), f"{(mistakes/total if total else 0):.3f}"]
    table_rows.append(total_row)

    # Print formatted table
    print(format_table(headers, table_rows))

    if csv:
        import csv as _csv
        with open(csv, "w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh)
            writer.writerow(headers)
            for row in table_rows:
                writer.writerow(row)
        print(f"wrote CSV to {csv}")


def main():
    ap = argparse.ArgumentParser(description="Summarize confusion matrix from JSONL logs.")
    ap.add_argument("paths", nargs="+", help="JSONL event files or '-' for stdin")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default=None)
    ap.add_argument("--csv", help="Optional output CSV path (only when a single input is provided)")
    ap.add_argument("--merge", action="store_true", help="Merge all inputs into one matrix (previous behavior)")
    ap.add_argument("--recompute-baseline", action="store_true", help="Recompute baseline decisions using current BasicStrategyAgent instead of trusting log field")
    args = ap.parse_args()

    if args.merge or len(args.paths) == 1:
        # Single matrix across all inputs
        merged_conf: Dict[str, Counter] = defaultdict(Counter)
        merged_total = 0
        merged_mistakes = 0
        merged_observed: set[str] = set()
        for p in args.paths:
            conf, total, mistakes, observed = confusion(p, args.track, recompute_baseline=args.recompute_baseline)
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
        conf, total, mistakes, observed = confusion(p, args.track, recompute_baseline=args.recompute_baseline)
        print_table(conf, total, mistakes, observed, csv=(args.csv if len(args.paths) == 1 else None))
        if i != len(args.paths) - 1:
            print()


if __name__ == "__main__":
    main()
