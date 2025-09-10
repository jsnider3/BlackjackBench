#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


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


RANK_ORDER = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]


def norm_rank(r: str) -> str:
    return "10" if r in {"10", "J", "Q", "K"} else r


def grid_weights_infinite_deck() -> Dict[Tuple[str, str, str], float]:
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    pr = {r: (4 / 13 if r == "10" else 1 / 13) for r in ranks}
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
    pd = {d: pr[d] for d in dealer_up}
    weights: Dict[Tuple[str, str, str], float] = {}
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:
            p_player = (pr[r1] ** 2) if r1 == r2 else (2 * pr[r1] * pr[r2])
            for du in dealer_up:
                weights[(r1, r2, du)] = p_player * pd[du]
    return weights


def classify(ev: dict) -> Tuple[str, Optional[Tuple[str, str, str]]]:
    """Return (category_key, start_cell) where start_cell is (p1,p2,du) if decision_idx==0 else None.

    category_key is one of:
      - "pair X/X" for first decision pairs (normalized 10-group)
      - "soft N" for soft totals
      - "hard N" for hard totals
    """
    obs = ev.get("obs") or {}
    player = obs.get("player") or {}
    total = player.get("total")
    is_soft = bool(player.get("is_soft"))
    didx = ev.get("decision_idx")
    cell = ev.get("cell") or {}
    start: Optional[Tuple[str, str, str]] = None
    if didx == 0 and cell:
        p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
        p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
        du = norm_rank(str(cell.get("du"))) if cell.get("du") else None
        if p1 and p2 and du:
            # ensure sorted for pair detection and weighting lookup
            p1s, p2s = sorted([p1, p2], key=lambda x: RANK_ORDER.index(x))
            start = (p1s, p2s, du)
            if p1s == p2s:
                return (f"pair {p1s}/{p2s}", start)
    if is_soft:
        return (f"soft {total}", start)
    else:
        return (f"hard {total}", start)


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
            cat, start = classify(ev)
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
    rows = []
    for k in sorted(class_total.keys(), key=lambda x: (0 if x.startswith("pair") else (1 if x.startswith("soft") else 2), x)):
        tot = class_total.get(k, 0)
        mis = class_mis.get(k, 0)
        mr = (mis / tot) if tot else 0.0
        rows.append((k, tot, mis, mr))
    # widths
    if rows:
        w0 = max(len(r[0]) for r in rows + [("class", 0, 0, 0.0)])
        print(f"{'class'.ljust(w0)}  total  mistakes  rate")
        for k, tot, mis, mr in rows:
            print(f"{k.ljust(w0)}  {tot:5d}  {mis:8d}  {mr:0.3f}")
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
    print("category\tdealer\tbaseline\tagent\tmistakes\tweighted_share")
    shown = 0
    for (cat, du, b, a), n in items:
        if shown >= top_n:
            break
        w = conf_wsum.get((cat, du, b, a), 0.0)
        share = (w / total_w) if total_w else 0.0
        print(f"{cat}\t{du}\t{b}\t{a}\t{n}\t{share:.6f}")
        shown += 1


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

