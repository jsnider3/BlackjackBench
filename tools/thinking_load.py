#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Any


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


def categorize(ev: dict) -> str:
    obs = ev.get("obs") or {}
    player = obs.get("player") or {}
    total = player.get("total")
    is_soft = bool(player.get("is_soft"))
    cell = ev.get("cell") or {}
    p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
    p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
    if ev.get("decision_idx") == 0 and p1 and p2 and p1 == p2:
        return f"pair {p1}/{p2}"
    return (f"soft {total}" if is_soft else f"hard {total}") if isinstance(total, int) else "unknown"


def compute_metric(meta: Dict[str, Any], *, prefer: str) -> Tuple[float, Dict[str, Any]]:
    """Return (metric_value, extras) given meta and preference.

    prefer: 'tokens' | 'chars' | 'words'
    - tokens: use usage.total_tokens - usage.prompt_tokens if present, else chars
    - chars: len(llm_thinking) if present, else 0
    - words: space-split length of llm_thinking
    """
    thinking = meta.get("llm_thinking")
    usage = meta.get("llm_usage") or {}
    prompt = usage.get("prompt_tokens")
    total = usage.get("total_tokens")
    out_tokens = None
    try:
        if isinstance(total, (int, float)) and isinstance(prompt, (int, float)):
            out_tokens = float(total) - float(prompt)
    except Exception:
        out_tokens = None

    if prefer == "tokens" and out_tokens is not None:
        return out_tokens, {"out_tokens": out_tokens, "prompt_tokens": prompt, "total_tokens": total}
    if prefer == "words" and isinstance(thinking, str):
        w = float(len([w for w in thinking.split() if w]))
        return w, {"words": w}
    # default to chars
    n = float(len(thinking)) if isinstance(thinking, str) else 0.0
    return n, {"chars": n, "out_tokens": out_tokens, "prompt_tokens": prompt, "total_tokens": total}


def main():
    ap = argparse.ArgumentParser(description="Rank decisions by 'thinking' load (tokens/length) from LLM JSONL logs.")
    ap.add_argument("inputs", nargs="+", help="Files, dirs, or globs (e.g., logs/*combined.jsonl)")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default="policy-grid")
    ap.add_argument("--metric", choices=["tokens", "chars", "words"], default="tokens", help="Metric to rank by (default: tokens)")
    ap.add_argument("--top", type=int, default=15, help="Show top N heaviest-thinking events")
    ap.add_argument("--bottom", type=int, default=15, help="Show bottom N lightest-thinking events")
    ap.add_argument("--first-only", action="store_true", help="Only consider first decisions (decision_idx==0)")
    ap.add_argument("--aggregate", action="store_true", help="Print aggregated grids for splits, hard totals, and soft totals")
    args = ap.parse_args()

    files = discover_files(args.inputs)
    if not files:
        raise SystemExit("No input files found")

    rows: List[Dict[str, Any]] = []
    seen = 0
    with_thinking = 0
    empty = 0
    attempts_ge2 = 0
    # For aggregation: grids mapping (row_label, dealer) -> list of metric values
    split_grid: Dict[Tuple[str, str], List[float]] = {}
    hard_grid: Dict[Tuple[int, str], List[float]] = {}
    soft_grid: Dict[Tuple[int, str], List[float]] = {}
    for f in files:
        for ev in load_events(f):
            if ev.get("track") != args.track:
                continue
            if ev.get("decision_idx") is None:
                continue
            if args.first_only and ev.get("decision_idx") != 0:
                continue
            seen += 1
            meta = ev.get("meta") or {}
            st = str(meta.get("llm_status", "")).lower()
            if st == "empty":
                empty += 1
                continue
            if isinstance(meta.get("llm_thinking"), str):
                with_thinking += 1
            if isinstance(meta.get("llm_attempts"), int) and meta.get("llm_attempts") >= 2:
                attempts_ge2 += 1
            val, extras = compute_metric(meta, prefer=args.metric)
            obs = ev.get("obs") or {}
            player = obs.get("player") or {}
            cell = ev.get("cell") or {}
            rows.append({
                "metric": val,
                "metric_extras": extras,
                "cell": {"p1": cell.get("p1"), "p2": cell.get("p2"), "du": cell.get("du")},
                "rep": ev.get("rep"),
                "decision_idx": ev.get("decision_idx"),
                "category": categorize(ev),
                "player_total": player.get("total"),
                "is_soft": bool(player.get("is_soft")),
                "allowed": obs.get("allowed_actions"),
                "agent_action": ev.get("agent_action"),
                "baseline_action": ev.get("baseline_action"),
                "mistake": bool(ev.get("mistake")),
            })
            # Build aggregation buckets for first decisions only
            if ev.get("decision_idx") == 0:
                du_full = obs.get("dealer_upcard")
                du = None
                if isinstance(du_full, str) and len(du_full) >= 1:
                    du = norm_rank(du_full[:-1])
                du = du or "?"
                p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
                p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
                total = player.get("total")
                is_soft = bool(player.get("is_soft"))
                if p1 and p2 and p1 == p2:
                    key = (f"{p1}/{p2}", du)
                    split_grid.setdefault(key, []).append(float(val))
                elif isinstance(total, int):
                    if is_soft:
                        key = (int(total), du)
                        soft_grid.setdefault(key, []).append(float(val))
                    else:
                        key = (int(total), du)
                        hard_grid.setdefault(key, []).append(float(val))

    if not rows:
        print("No decision events found (or all were empty).")
        return

    if args.aggregate:
        # Helper to print a grid table
        dealer_cols = ["2","3","4","5","6","7","8","9","10","A"]
        def print_grid(title: str, rows_labels: List[Any], grid: Dict[Tuple[Any,str], List[float]]):
            print(f"\n# {title}")
            
            # Prepare table data
            table_data = []
            for rl in rows_labels:
                row = [str(rl)]
                for du in dealer_cols:
                    vals = grid.get((rl, du)) or []
                    if vals:
                        avg = sum(vals)/len(vals)
                        row.append(f"{avg:.1f}")
                    else:
                        row.append("")
                table_data.append(row)

            if not table_data:
                print("(no data)")
                return

            # Calculate widths
            header = ["player\dealer"] + dealer_cols
            widths = [max(len(header[i]), max((len(row[i]) for row in table_data), default=0)) for i in range(len(header))]

            # Print header
            header_line = [header[0].ljust(widths[0])]
            for i in range(1, len(header)):
                header_line.append(header[i].rjust(widths[i]))
            print("  ".join(header_line))

            # Print rows
            for row in table_data:
                row_line = [row[0].ljust(widths[0])]
                for i in range(1, len(row)):
                    row_line.append(row[i].rjust(widths[i]))
                print("  ".join(row_line))
        # Prepare row labels
        split_rows = [f"{r}/{r}" for r in RANK_ORDER]
        hard_rows = sorted({k[0] for k in hard_grid.keys()})
        soft_rows = sorted({k[0] for k in soft_grid.keys()})
        print(f"events={seen} with_thinking={with_thinking} empty={empty} attempts_ge2={attempts_ge2}")
        print_grid("Splits avg thinking ("+args.metric+")", split_rows, split_grid)
        print_grid("Hard totals avg thinking ("+args.metric+")", hard_rows, hard_grid)
        print_grid("Soft totals avg thinking ("+args.metric+")", soft_rows, soft_grid)
        return

    rows.sort(key=lambda r: (r["metric"]))

    def fmt_row(r: Dict[str, Any]) -> str:
        c = r.get("cell") or {}
        extras = r.get("metric_extras") or {}
        m = r.get("metric")
        extras_str = " ".join(f"{k}:{v}" for k, v in extras.items() if v is not None)
        return (
            f"p1={c.get('p1')} p2={c.get('p2')} du={c.get('du')} rep={r.get('rep')} d={r.get('decision_idx')} "
            f"cat={r.get('category')} total={r.get('player_total')} soft={r.get('is_soft')} "
            f"base={r.get('baseline_action')} agent={r.get('agent_action')} mistake={r.get('mistake')} "
            f"metric={m:.1f} extras={extras_str}"
        )

    # Summary
    values = [r["metric"] for r in rows]
    values_sorted = sorted(values)
    import statistics as _st
    median = values_sorted[len(values_sorted)//2]
    p90 = values_sorted[int(0.90 * (len(values_sorted)-1))]
    p99 = values_sorted[int(0.99 * (len(values_sorted)-1))]
    print(f"events={seen} with_thinking={with_thinking} empty={empty} attempts_ge2={attempts_ge2}")
    print(f"metric={args.metric} median={median:.1f} p90={p90:.1f} p99={p99:.1f}")

    # Bottom
    print("\n# Lightest-thinking events (bottom)")
    for r in rows[: args.bottom]:
        print(fmt_row(r))

    # Top
    print("\n# Heaviest-thinking events (top)")
    for r in rows[-args.top :][::-1]:
        print(fmt_row(r))


if __name__ == "__main__":
    main()
