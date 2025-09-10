from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import time
import json
from typing import Any

from .agents.basic import BasicStrategyAgent
from .agents.random_agent import RandomAgent
from .agents.bad_agent import BadAgent
from .agents.guarded import GuardedAgent
from .agents.llm_agent import LLMAgent
from .eval import run_policy_track, run_policy_grid


def build_agent(name: str, args: argparse.Namespace | None = None) -> Any:
    if name == "basic":
        return BasicStrategyAgent()
    if name == "random":
        return RandomAgent()
    if name in ("bad", "worst"):
        return BadAgent()
    if name == "llm":
        provider = getattr(args, "llm_provider", None) if args else None
        model = getattr(args, "llm_model", None) if args else None
        temperature = getattr(args, "llm_temperature", 0.0) if args else 0.0
        prompt_mode = getattr(args, "llm_prompt", "rules_lite") if args else "rules_lite"
        llm_debug = getattr(args, "llm_debug", False) if args else False
        gemini_reasoning = getattr(args, "gemini_reasoning", "low") if args else "low"
        return LLMAgent(
            provider=provider or "openai",
            model=model or "gpt-4o-mini",
            temperature=temperature,
            prompt_mode=prompt_mode,
            debug_log=llm_debug,
            gemini_reasoning=gemini_reasoning,
        )
    raise ValueError(f"Unknown agent: {name}")


def cmd_run(args: argparse.Namespace) -> None:
    agent = build_agent(args.agent, args)
    if args.guard:
        agent = GuardedAgent(agent)
    # Per-decision logging
    debug = getattr(args, "debug", False)
    log_file = getattr(args, "log_jsonl", None)
    # If resuming and no explicit log target is provided, append to the resume file
    if not log_file and getattr(args, "resume_from", None):
        log_file = args.resume_from
    if not log_file:
        # Default log path: logs/YYYYmmdd_HHMMSS_track_agent[_model].jsonl
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("logs").mkdir(parents=True, exist_ok=True)
        suffix = args.agent
        if args.agent == "llm":
            model = getattr(args, "llm_model", None) or "model"
            # Sanitize model name for filesystem
            safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "-" for ch in model)
            suffix = f"{suffix}_{safe}"
        log_file = str(Path("logs") / f"{ts}_{args.track}_{suffix}.jsonl")
    log_fh = open(log_file, "a", encoding="utf-8")

    # Heartbeat state
    heartbeat_secs = max(0, int(getattr(args, "heartbeat_secs", 60)))
    last_hb = time.monotonic()
    start_ts = last_hb
    processed_pairs = set()  # for policy-grid: (p1,p2,du,rep)

    # If resuming, pre-populate processed_pairs from the log
    if getattr(args, "resume_from", None) and args.track == "policy-grid":
        try:
            import json as _json
            with open(args.resume_from, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = _json.loads(line)
                    except Exception:
                        continue
                    if ev.get("track") != "policy-grid":
                        continue
                    cell = ev.get("cell") or {}
                    rep = ev.get("rep")
                    if not isinstance(rep, int):
                        continue
                    key = (cell.get("p1"), cell.get("p2"), cell.get("du"), rep)
                    if all(isinstance(k, str) for k in key[:3]):
                        processed_pairs.add(key)
        except FileNotFoundError:
            pass
    max_hand_seen = -1

    # Pre-run note for grid
    if args.track == "policy-grid" and heartbeat_secs > 0:
        total_cells = 55 * 10 * args.reps
        print(f"[start] policy-grid: reps={args.reps}, total_cells={total_cells}")
        if processed_pairs:
            done = len(processed_pairs)
            pct = (done / total_cells) * 100 if total_cells else 0
            print(f"[resume] already completed: {done}/{total_cells} ({pct:.1f}%) from {getattr(args, 'resume_from', '')}")

    def emit(event: dict):
        nonlocal last_hb, max_hand_seen
        if debug:
            # Compact stdout line
            obs = event.get("obs", {})
            p = obs.get("player", {})
            up_full = obs.get("dealer_upcard")
            up = up_full[:-1] if isinstance(up_full, str) and len(up_full) >= 2 else up_full
            cards_full = p.get("cards", []) or []
            cards = [c[:-1] if isinstance(c, str) and len(c) >= 2 else c for c in cards_full]
            print(f"[hand {event.get('hand')} d{event.get('decision_idx')}] up={up} cards={cards} act={event.get('agent_action')} base={event.get('baseline_action')} mistake={event.get('mistake')} illegal={event.get('meta',{}).get('illegal_attempt') is not None}")

        # Heartbeat printing
        if heartbeat_secs > 0:
            now = time.monotonic()
            track = event.get("track")
            if track == "policy-grid":
                cell = event.get("cell", {})
                rep = event.get("rep")
                key = (cell.get("p1"), cell.get("p2"), cell.get("du"), rep)
                processed_pairs.add(key)
                if now - last_hb >= heartbeat_secs:
                    elapsed = now - start_ts
                    total = 55 * 10 * args.reps
                    done = len(processed_pairs)
                    pct = (done / total) * 100 if total else 0
                    print(f"[heartbeat] {elapsed:.0f}s policy-grid: cell={cell.get('p1')},{cell.get('p2')} vs {cell.get('du')} rep={rep+1 if isinstance(rep,int) else rep}/{args.reps} progress={done}/{total} ({pct:.1f}%)")
                    last_hb = now
            elif track == "policy":
                hand = event.get("hand")
                if isinstance(hand, int):
                    max_hand = max_hand_seen if isinstance(max_hand_seen, int) else -1
                    max_hand = max(max_hand, hand)
                    max_hand_seen = max_hand
                if now - last_hb >= heartbeat_secs:
                    elapsed = now - start_ts
                    total = args.hands
                    done = (max_hand_seen + 1) if max_hand_seen >= 0 else 0
                    pct = (done / total) * 100 if total else 0
                    print(f"[heartbeat] {elapsed:.0f}s policy: hand={done}/{total} ({pct:.1f}%)")
                    last_hb = now
        if log_fh:
            import json as _json
            log_fh.write(_json.dumps(event) + "\n")
            log_fh.flush()

    if args.track == "policy":
        result = run_policy_track(agent, hands=args.hands, seed=args.seed, rules=None, log_fn=emit if (debug or log_fh) else None)
    elif args.track == "policy-grid":
        result = run_policy_grid(agent, seed=args.seed, weighted=args.weighted, reps=args.reps, log_fn=emit if (debug or log_fh) else None, resume_from=getattr(args, "resume_from", None))
    else:
        raise ValueError(f"Unknown track: {args.track}")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    print(json.dumps(result["metrics"], indent=2))
    if log_fh:
        log_fh.close()
        print(f"per-decision log written to {log_file}")


def main():
    parser = argparse.ArgumentParser(prog="blackjack_bench", description="BlackJackBench CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run a benchmark track")
    p_run.add_argument("--agent", choices=["basic", "random", "bad", "worst", "llm"], default="basic")
    p_run.add_argument("--track", choices=["policy", "policy-grid"], default="policy")
    p_run.add_argument("--hands", type=int, default=10000)
    p_run.add_argument("--seed", type=int, default=42)
    p_run.add_argument("--report", type=str, default=None)
    p_run.add_argument("--weighted", action="store_true", help="Weight policy-grid EV by natural frequency (infinite-deck)")
    p_run.add_argument("--reps", type=int, default=1, help="Repetitions per grid cell (policy-grid)")
    p_run.add_argument("--guard", action="store_true", help="Wrap agent to log illegal actions and fall back to worst legal choice")
    # LLM settings
    p_run.add_argument(
        "--llm-provider",
        type=str,
        default="openai",
        help="LLM provider (openai | gemini | ollama | openrouter)",
    )
    p_run.add_argument("--llm-model", type=str, default="gpt-4o-mini", help="LLM model name for --agent llm")
    p_run.add_argument("--llm-temperature", type=float, default=0.0, help="LLM temperature for --agent llm")
    p_run.add_argument("--llm-prompt", type=str, choices=["minimal", "rules_lite", "verbose"], default="rules_lite", help="Prompt style for --agent llm")
    # Gemini/OpenAI extras
    p_run.add_argument("--gemini-reasoning", type=str, default="low", choices=["none", "low", "medium", "high"], help="Gemini reasoning effort (none disables thinking)")
    # Gemini support uses the official SDK only
    p_run.add_argument("--llm-debug", action="store_true", help="Include LLM prompt in per-decision meta (response always logged)")
    # Debug/logging
    p_run.add_argument("--debug", action="store_true", help="Print per-decision debug lines to stdout")
    p_run.add_argument("--log-jsonl", type=str, default=None, help="Write per-decision JSONL events to this file")
    p_run.add_argument("--heartbeat-secs", type=int, default=60, help="Print a heartbeat line every N seconds (0 to disable)")
    p_run.add_argument("--resume-from", type=str, default=None, help="For policy-grid, resume by skipping (cell,rep) pairs already present in this JSONL log")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
