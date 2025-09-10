#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


Cell = Tuple[str, str, str]
Key = Tuple[str, str, str, int]


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


def norm_rank(r: str) -> str:
    return "10" if r in {"10", "J", "Q", "K"} else r


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


def per_hand_rewards(path: Path, track: str = "policy-grid") -> Dict[Key, float]:
    out: Dict[Key, float] = {}
    for ev in load_events(path):
        if ev.get("track") != track:
            continue
        cell = ev.get("cell") or {}
        rep = ev.get("rep")
        if not isinstance(rep, int):
            continue
        p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
        p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
        du = norm_rank(str(cell.get("du"))) if cell.get("du") else None
        if not (p1 and p2 and du):
            continue
        key: Key = (p1, p2, du, rep)
        if key in out:
            continue
        final = ev.get("final") or {}
        r = final.get("reward")
        if isinstance(r, (int, float)):
            out[key] = float(r)
    return out


def categorize(ev: dict) -> Tuple[str, str, str, str]:
    cell = ev.get("cell") or {}
    p1 = norm_rank(str(cell.get("p1")))
    p2 = norm_rank(str(cell.get("p2")))
    du = norm_rank(str(cell.get("du")))
    obs = ev.get("obs") or {}
    player = obs.get("player") or {}
    total = int(player.get("total", 0))
    is_soft = bool(player.get("is_soft"))
    if p1 == p2:
        cat = f"pair {p1}/{p2}"
    elif is_soft:
        cat = f"soft {total}"
    else:
        cat = f"hard {total}"
    b = str(ev.get("baseline_action"))
    a = str(ev.get("agent_action"))
    return cat, du, b, a


def impact_table(agent_path: Path, baseline_path: Path, top: int = 12) -> List[Dict[str, object]]:
    weights = grid_weights_infinite_deck()
    base_rewards = per_hand_rewards(baseline_path)
    # Aggregate weighted loss per leak key
    loss_w: Dict[Tuple[str, str, str, str], float] = defaultdict(float)
    count: Dict[Tuple[str, str, str, str], int] = defaultdict(int)
    total_loss_w = 0.0

    for ev in load_events(agent_path):
        if ev.get("track") != "policy-grid":
            continue
        if ev.get("decision_idx") != 0:
            continue
        a = ev.get("agent_action"); b = ev.get("baseline_action")
        if not isinstance(a, str) or not isinstance(b, str) or a == b:
            continue
        cell = ev.get("cell") or {}
        rep = ev.get("rep")
        if not isinstance(rep, int):
            continue
        p1 = norm_rank(str(cell.get("p1")))
        p2 = norm_rank(str(cell.get("p2")))
        du = norm_rank(str(cell.get("du")))
        key = (p1, p2, du, rep)
        # rewards
        agent_r = None
        final = ev.get("final") or {}
        r = final.get("reward")
        if isinstance(r, (int, float)):
            agent_r = float(r)
        base_r = base_rewards.get(key)
        if agent_r is None or base_r is None:
            continue
        delta = base_r - agent_r  # EV loss vs baseline for this hand
        # weight by natural frequency of starting cell
        r1, r2 = sorted([p1, p2], key=lambda x: ["A","2","3","4","5","6","7","8","9","10"].index(x))
        w = weights.get((r1, r2, du), 0.0)
        cat, du_s, b_s, a_s = categorize(ev)
        leak_key = (cat, du_s, b_s, a_s)
        loss_w[leak_key] += w * delta
        count[leak_key] += 1
        total_loss_w += w * delta

    rows: List[Dict[str, object]] = []
    for (cat, du, b, a), lw in loss_w.items():
        rows.append({
            "category": cat,
            "dealer": du,
            "baseline": b,
            "agent": a,
            "count": count[(cat, du, b, a)],
            "weighted_ev_loss": lw,
        })
    rows.sort(key=lambda r: r["weighted_ev_loss"], reverse=True)
    for r in rows:
        r["share"] = (r["weighted_ev_loss"] / total_loss_w) if total_loss_w else 0.0
    return rows[:top]


def main():
    ap = argparse.ArgumentParser(description="Quantify EV impact of first-decision leaks by aligning agent vs basic baseline")
    ap.add_argument("agent", help="Agent JSONL (policy-grid)")
    ap.add_argument("baseline", help="Basic-strategy JSONL (policy-grid)")
    ap.add_argument("--out-csv", default=None, help="Optional CSV output")
    ap.add_argument("--out-md", default=None, help="Optional Markdown output")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    agent_p = Path(args.agent)
    base_p = Path(args.baseline)
    rows = impact_table(agent_p, base_p, top=args.top)

    headers = ["category", "dealer", "baseline", "agent", "count", "weighted_ev_loss", "share"]
    def fmt(x):
        if isinstance(x, float):
            return f"{x:.6f}"
        return str(x)
    print("\t".join(headers))
    for r in rows:
        print("\t".join(fmt(r[h]) for h in headers))

    if args.out_csv:
        Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            for r in rows:
                w.writerow([r[h] if h != "share" else f"{r[h]:.6f}" for h in headers])
        print(f"wrote CSV to {args.out_csv}")

    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        lines = ["| Category | Dealer | Baseline | Agent | Count | Weighted EV Loss | Share |", "|---|:---:|:---:|:---:|---:|---:|---:|"]
        for r in rows:
            lines.append(f"| {r['category']} | {r['dealer']} | {r['baseline']} | {r['agent']} | {r['count']} | {r['weighted_ev_loss']:.4f} | {r['share']*100:.2f}% |")
        Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote Markdown to {args.out_md}")


if __name__ == "__main__":
    main()

