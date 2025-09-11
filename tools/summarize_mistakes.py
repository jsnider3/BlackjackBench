#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional

from common import (
    discover_files, load_events, grid_weights_infinite_deck, 
    classify_decision, format_table, norm_rank
)


def summarize(files: List[Path], track: Optional[str], top_n: int, first_only: bool) -> None:
    weights = grid_weights_infinite_deck()
    # Per-class totals/mistakes
    class_total: Dict[str, int] = {}
    class_mis: Dict[str, int] = {}
    # Top confusions: (category, dealer, baseline, agent) -> counts and weighted share
    conf_counts: Dict[Tuple[str, str, str, str], int] = {}
    conf_wsum: Dict[Tuple[str, str, str, str], float] = {}
    total_events = 0
    total_mistakes = 0
    total_w = 0.0

    for f in files:
        for ev in load_events(f):
            if track and ev.get("track") != track:
                continue
            # Only consider decision events
            if ev.get("decision_idx") is None:
                continue
            if first_only and ev.get("decision_idx") != 0:
                continue

            a = ev.get("agent_action")
            b = ev.get("baseline_action")
            if not isinstance(a, str) or not isinstance(b, str):
                continue
            cat, start = classify_decision(ev)
            class_total[cat] = class_total.get(cat, 0) + 1
            total_events += 1
            mistake = (a != b)
            if mistake:
                class_mis[cat] = class_mis.get(cat, 0) + 1
                total_mistakes += 1
                # dealer rank normalized
                obs = ev.get("obs") or {}
                du_full = obs.get("dealer_upcard")
                du = None
                if isinstance(du_full, str) and len(du_full) >= 1:
                    du = norm_rank(du_full[:-1])
                du = du or "?"
                key = (cat, du, b, a)
                conf_counts[key] = conf_counts.get(key, 0) + 1
                # Weighted share only for first decisions where we know start cell
                if start is not None:
                    w = weights.get(start)
                    if w is None:
                        # try without sorting fallbacks
                        w = 0.0
                    conf_wsum[key] = conf_wsum.get(key, 0.0) + float(w or 0.0)
                    total_w += float(w or 0.0)

    # Print overall
    print(f"events={total_events} mistakes={total_mistakes} mistake_rate={(total_mistakes/total_events if total_events else 0):.3f}")

    # Per-class mistake rates
    print("\n# Per-class mistake rates")
    class_rows = []
    for k in sorted(class_total.keys(), key=lambda x: (0 if x.startswith("pair") else (1 if x.startswith("soft") else 2), x)):
        tot = class_total.get(k, 0)
        mis = class_mis.get(k, 0)
        mr = (mis / tot) if tot else 0.0
        class_rows.append([k, str(tot), str(mis), f"{mr:.3f}"])
    
    if class_rows:
        print(format_table(["class", "total", "mistakes", "rate"], class_rows, right_align=["total", "mistakes", "rate"]))
    else:
        print("(no decisions)")

    # Top confusions
    print("\n# Top confusions")
    items = list(conf_counts.items())
    # Sort by weighted share when available, else by raw mistakes
    def sort_key(it):
        key, n = it
        w = conf_wsum.get(key, 0.0)
        return (w, n)
    items.sort(key=sort_key, reverse=True)
    
    confusion_rows = []
    shown = 0
    for (cat, du, b, a), n in items:
        if shown >= top_n:
            break
        w = conf_wsum.get((cat, du, b, a), 0.0)
        share = (w / total_w) if total_w else 0.0
        confusion_rows.append([cat, du, b, a, str(n), f"{share:.6f}"])
        shown += 1

    if confusion_rows:
        headers = ["category", "dealer", "baseline", "agent", "mistakes", "weighted_share"]
        print(format_table(headers, confusion_rows, right_align=["mistakes", "weighted_share"]))
    else:
        print("(no confusions)")


def main():
    ap = argparse.ArgumentParser(description="Summarize top confusions and per-class mistake rates from JSONL logs.")
    ap.add_argument("inputs", nargs="+", help="Files, dirs, or globs (e.g., logs/*.jsonl)")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default="policy-grid")
    ap.add_argument("--top", type=int, default=20, help="Top N confusion rows")
    ap.add_argument("--first-only", action="store_true", help="Only consider first decisions (decision_idx==0)")
    args = ap.parse_args()

    files = discover_files(args.inputs)
    if not files:
        raise SystemExit("No input files found")
    summarize(files, args.track, args.top, args.first_only)


if __name__ == "__main__":
    main()

