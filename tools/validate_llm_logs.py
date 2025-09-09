#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional


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


def summarize_file(path: Path, track: Optional[str]) -> Dict:
    total_events = 0
    decisions = 0
    no_decision = 0
    missing_llm_raw = 0
    empty_llm_raw = 0
    with_llm_status = 0
    status_counts = {"ok": 0, "empty": 0, "error": 0, "other": 0}

    for ev in load_events(path):
        if track and ev.get("track") != track:
            continue
        total_events += 1
        didx = ev.get("decision_idx")
        if didx is None:
            no_decision += 1
            continue
        decisions += 1
        meta = ev.get("meta") or {}
        if "llm_raw" not in meta:
            missing_llm_raw += 1
        else:
            raw = meta.get("llm_raw")
            if isinstance(raw, str) and raw.strip() == "":
                empty_llm_raw += 1
        if "llm_status" in meta:
            with_llm_status += 1
            st = str(meta.get("llm_status")).lower()
            if st in status_counts:
                status_counts[st] += 1
            else:
                status_counts["other"] += 1

    looks_llm = ("_llm_" in path.name) or (with_llm_status > 0)

    return {
        "file": str(path),
        "track": track,
        "events": total_events,
        "decisions": decisions,
        "no_decision": no_decision,
        "missing_llm_raw": missing_llm_raw,
        "empty_llm_raw": empty_llm_raw,
        "with_llm_status": with_llm_status,
        "status_ok": status_counts["ok"],
        "status_empty": status_counts["empty"],
        "status_error": status_counts["error"],
        "status_other": status_counts["other"],
        "looks_llm": looks_llm,
    }


def print_table(rows: List[Dict]) -> None:
    headers = [
        "file",
        "decisions",
        "missing_llm_raw",
        "empty_llm_raw",
        "with_llm_status",
        "status_ok",
        "status_empty",
        "status_error",
    ]
    # column widths
    def s(x):
        return str(x)
    widths = {h: max(len(h), max(len(s(r.get(h, ""))) for r in rows)) for h in headers}
    print("  ".join(h.ljust(widths[h]) for h in headers))
    for r in rows:
        print("  ".join(s(r.get(h, "")).ljust(widths[h]) for h in headers))


def main():
    ap = argparse.ArgumentParser(description="Validate LLM metadata in JSONL logs.")
    ap.add_argument("inputs", nargs="*", default=["baselines"], help="Files, dirs, or globs (default: baselines)")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default="policy-grid")
    ap.add_argument("--json", dest="json_out", help="Write a JSON report to this path")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if any LLM-looking file is missing llm_raw entries")
    args = ap.parse_args()

    files = discover_files(args.inputs)
    rows = [summarize_file(p, args.track) for p in files]
    if not rows:
        print("No input files found.")
        return

    print_table(rows)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"wrote JSON report to {args.json_out}")

    if args.strict:
        bad = [r for r in rows if r["looks_llm"] and (r["missing_llm_raw"] > 0 or r["empty_llm_raw"] > 0)]
        if bad:
            print(f"FAIL: {len(bad)} file(s) have missing/empty llm_raw", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()

