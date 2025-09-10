#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


Cell = Tuple[str, str, str]  # (p1, p2, du)


def grid_weights_infinite_deck() -> Dict[Cell, float]:
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    pr = {r: (4 / 13 if r == "10" else 1 / 13) for r in ranks}
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
    pd = {d: pr[d] for d in dealer_up}
    weights: Dict[Cell, float] = {}
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:
            p_player = (pr[r1] ** 2) if r1 == r2 else (2 * pr[r1] * pr[r2])
            for du in dealer_up:
                weights[(r1, r2, du)] = p_player * pd[du]
    return weights


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


def norm_rank(r: str) -> str:
    return "10" if r in {"10", "J", "Q", "K"} else r


def summarize_top_leaks(inputs: List[Path], track: str = "policy-grid", top_n: int = 15) -> List[Dict[str, object]]:
    weights = grid_weights_infinite_deck()
    # key: (category, du, baseline, agent)
    counts: Dict[Tuple[str, str, str, str], int] = defaultdict(int)
    wsum: Dict[Tuple[str, str, str, str], float] = defaultdict(float)
    total_w = 0.0

    for p in inputs:
        for ev in load_events(p):
            if ev.get("track") != track:
                continue
            if ev.get("decision_idx") != 0:
                # focus on first decision (two-card start)
                continue
            a = ev.get("agent_action")
            b = ev.get("baseline_action")
            if not isinstance(a, str) or not isinstance(b, str) or a == b:
                continue
            cell = ev.get("cell") or {}
            p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
            p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
            du = norm_rank(str(cell.get("du"))) if cell.get("du") else None
            if not (p1 and p2 and du):
                continue
            # categorize: pair vs soft vs hard
            obs = ev.get("obs") or {}
            player = obs.get("player") or {}
            total = player.get("total")
            is_soft = bool(player.get("is_soft"))
            if p1 == p2:
                cat = f"pair {p1}/{p2}"
            elif is_soft:
                cat = f"soft {total}"
            else:
                cat = f"hard {total}"

            key = (cat, du, b, a)
            counts[key] += 1
            # weight by natural frequency of the starting cell
            w = weights.get((p1, p2, du))
            if w is None:
                # ensure order (p1<=p2) for lookup
                r1, r2 = sorted([p1, p2], key=lambda x: ["A","2","3","4","5","6","7","8","9","10"].index(x))
                w = weights.get((r1, r2, du), 0.0)
            wsum[key] += float(w or 0.0)
            total_w += float(w or 0.0)

    rows: List[Dict[str, object]] = []
    for (cat, du, b, a), n in counts.items():
        w = wsum[(cat, du, b, a)]
        share = (w / total_w) if total_w else 0.0
        rows.append({
            "category": cat,
            "dealer": du,
            "baseline": b,
            "agent": a,
            "mistakes": n,
            "weighted_share": share,
        })

    rows.sort(key=lambda r: (r["weighted_share"], r["mistakes"]), reverse=True)
    return rows[:top_n]


def main():
    ap = argparse.ArgumentParser(description="Compute a compact 'top leaks' table from policy-grid logs (decision_idx==0 only)")
    ap.add_argument("inputs", nargs="+", help="One or more JSONL log files or globs")
    ap.add_argument("--out-csv", default=None, help="Optional CSV output path")
    ap.add_argument("--out-md", default=None, help="Optional Markdown table output path")
    ap.add_argument("--top", type=int, default=15, help="Number of rows to output")
    args = ap.parse_args()

    # expand globs
    files: List[Path] = []
    for inp in args.inputs:
        p = Path(inp)
        if any(ch in inp for ch in "*?["):
            files.extend(sorted(Path().glob(inp)))
        else:
            files.append(p)
    files = [f for f in files if f.exists() and f.suffix == ".jsonl"]
    if not files:
        raise SystemExit("No JSONL inputs found")

    rows = summarize_top_leaks(files, top_n=args.top)

    # print to stdout
    headers = ["category", "dealer", "baseline", "agent", "mistakes", "weighted_share"]
    def fmt(x):
        return f"{x:.4f}" if isinstance(x, float) else str(x)
    print("\t".join(headers))
    for r in rows:
        print("\t".join(fmt(r[h]) for h in headers))

    if args.out_csv:
        Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            for r in rows:
                w.writerow([r[h] if h != "weighted_share" else f"{r[h]:.6f}" for h in headers])
        print(f"wrote CSV to {args.out_csv}")

    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        lines = ["| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |", "|---|:---:|:---:|:---:|---:|---:|"]
        for r in rows:
            lines.append(f"| {r['category']} | {r['dealer']} | {r['baseline']} | {r['agent']} | {r['mistakes']} | {r['weighted_share']*100:.2f}% |")
        Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote Markdown to {args.out_md}")


if __name__ == "__main__":
    main()

