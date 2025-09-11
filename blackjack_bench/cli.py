from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import time
import sys
import subprocess
import json
from typing import Any

from .agents.basic import BasicStrategyAgent
from .agents.random_agent import RandomAgent
from .agents.bad_agent import BadAgent
from .agents.guarded import GuardedAgent
from .agents.llm_agent import LLMAgent
from .agents.claude_sonnet_agent import ClaudeSonnetAgent
from .agents.gpt5_agent import GPT5Agent
from .agents.gemini_flash_agent import GeminiFlashAgent
from .agents.sonoma_sky_agent import SonomaSkyAgent
from .agents.gemma_agent import GemmaAgent
from .agents.qwen_cli_agent import QwenCLIAgent
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
        reasoning = getattr(args, "reasoning", "low") if args else "low"
        return LLMAgent(
            provider=provider or "openai",
            model=model or "gpt-4o-mini",
            temperature=temperature,
            prompt_mode=prompt_mode,
            debug_log=llm_debug,
            reasoning=reasoning,
        )
    # Model-thought-based agents
    if name == "claude-sonnet":
        return ClaudeSonnetAgent()
    if name == "gpt5":
        return GPT5Agent()
    if name == "gemini-flash":
        return GeminiFlashAgent()
    if name == "sonoma-sky":
        return SonomaSkyAgent()
    if name == "gemma":
        return GemmaAgent()
    if name == "qwen-cli":
        llm_debug = getattr(args, "llm_debug", False) if args else False
        return QwenCLIAgent(debug_log=llm_debug)
    raise ValueError(f"Unknown agent: {name}")


def _run_parallel(args: argparse.Namespace) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    Path("logs").mkdir(parents=True, exist_ok=True)
    suffix = args.agent
    if args.agent == "llm":
        model = getattr(args, "llm_model", None) or "model"
        safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "-" for ch in model)
        suffix = f"{suffix}_{safe}"
    base_log = str(Path("logs") / f"{ts}_{args.track}_{suffix}")
    procs = []
    shard_logs: list[str] = []
    par = max(1, int(getattr(args, "parallel", 1)))
    for i in range(par):
        shard_log = f"{base_log}_shard{i}.jsonl"
        shard_logs.append(shard_log)
        cmd = [
            sys.executable,
            "-m",
            "blackjack_bench.cli",
            "run",
            "--agent", args.agent,
            "--track", args.track,
            "--reps", str(args.reps),
            "--seed", str(args.seed),
            "--heartbeat-secs", str(getattr(args, "heartbeat_secs", 60)),
            "--log-jsonl", shard_log,
            "--num-shards", str(par),
            "--shard-index", str(i),
        ]
        if args.weighted:
            cmd.append("--weighted")
        if args.guard:
            cmd.append("--guard")
        if getattr(args, "report", None):
            cmd.extend(["--report", f"{base_log}_shard{i}.report.json"])
        if args.agent == "llm":
            cmd.extend(["--llm-provider", getattr(args, "llm_provider", "openai")])
            cmd.extend(["--llm-model", getattr(args, "llm_model", "gpt-4o-mini")])
            cmd.extend(["--llm-temperature", str(getattr(args, "llm_temperature", 0.0))])
            cmd.extend(["--llm-prompt", getattr(args, "llm_prompt", "rules_lite")])
            cmd.extend(["--reasoning", getattr(args, "reasoning", "low")])
            if getattr(args, "llm_debug", False):
                cmd.append("--llm-debug")
        if getattr(args, "debug", False):
            cmd.append("--debug")
        if getattr(args, "resume_from", None):
            cmd.extend(["--resume-from", getattr(args, "resume_from")])
        procs.append(subprocess.Popen(cmd))

    print(f"[parent] launched {par} shard(s); writing shard logs to {base_log}_shard*.jsonl")
    try:
        last_done = 0
        while True:
            remaining = [p for p in procs if p.poll() is None]
            done = len(procs) - len(remaining)
            if done > last_done and done >= 1:
                print(f"[parent] shards {done}/{par} completed")
                last_done = done
            if not remaining:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("[parent] received interrupt; terminating shards...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                pass

    try:
        combined = f"{base_log}_combined.jsonl"
        with open(combined, "w", encoding="utf-8") as out_f:
            for sl in shard_logs:
                try:
                    with open(sl, "r", encoding="utf-8") as in_f:
                        for line in in_f:
                            if line.strip():
                                out_f.write(line)
                except FileNotFoundError:
                    pass
        print(f"parallel run complete; combined log: {combined}")
        print(f"shard logs kept: {base_log}_shard*.jsonl")
    except Exception as e:
        print(f"parallel run complete; failed to combine logs: {e}")
        print(f"shard logs at {base_log}_shard*.jsonl")

def _run_single(args: argparse.Namespace) -> None:
    agent = build_agent(args.agent, args)
    if args.guard:
        agent = GuardedAgent(agent)

    debug = getattr(args, "debug", False)
    log_file, log_fh = _setup_logging(args)

    heartbeat_secs = max(0, int(getattr(args, "heartbeat_secs", 60)))
    last_hb = time.monotonic()
    start_ts = last_hb
    processed_pairs = set()
    max_hand_seen = -1
    
    # Error tracking
    error_count = 0
    consecutive_errors = 0
    last_error = None

    if getattr(args, "resume_from", None) and args.track == "policy-grid":
        processed_pairs = _load_processed_pairs(args.resume_from)

    shard_tag, total_cells_for_heartbeat = _prepare_heartbeat(args, processed_pairs)

    def emit(event: dict):
        nonlocal last_hb, max_hand_seen, error_count, consecutive_errors, last_error
        
        # Check for LLM errors and empty responses
        meta = event.get("meta", {})
        llm_status = meta.get("llm_status")
        llm_error = meta.get("llm_error")
        llm_model = meta.get("llm_model", "unknown")
        
        if llm_status == "error" and llm_error:
            error_count += 1
            consecutive_errors += 1
            last_error = llm_error
            
            # Print error immediately for visibility
            print(f"❌ LLM ERROR (#{error_count}): {llm_error}")
            
            # If we get too many consecutive errors, abort
            if consecutive_errors >= 10:
                print(f"🛑 ABORTING: {consecutive_errors} consecutive LLM errors. Last error: {last_error}")
                print(f"Check your API key, model name, or network connection.")
                if log_fh:
                    log_fh.close()
                sys.exit(1)
        elif llm_status == "empty":
            error_count += 1
            consecutive_errors += 1
            last_error = f"Model {llm_model} returned empty response after {meta.get('llm_attempts', '?')} attempts"
            
            # Print empty response error for visibility
            print(f"❌ LLM EMPTY RESPONSE (#{error_count}): {last_error}")
            
            # If we get too many consecutive empty responses, abort
            if consecutive_errors >= 10:
                print(f"🛑 ABORTING: {consecutive_errors} consecutive empty responses from {llm_model}")
                print(f"The model may not support the current prompt format or parameters.")
                print(f"Try using --llm-debug to see the exact prompt being sent.")
                if log_fh:
                    log_fh.close()
                sys.exit(1)
        else:
            # Reset consecutive counter on success
            consecutive_errors = 0
        
        if debug:
            obs = event.get("obs", {})
            p = obs.get("player", {})
            up_full = obs.get("dealer_upcard")
            up = up_full[:-1] if isinstance(up_full, str) and len(up_full) >= 2 else up_full
            cards_full = p.get("cards", []) or []
            cards = [c[:-1] if isinstance(c, str) and len(c) >= 2 else c for c in cards_full]
            print(f"[hand {event.get('hand')} d{event.get('decision_idx')}] up={up} cards={cards} act={event.get('agent_action')} base={event.get('baseline_action')} mistake={event.get('mistake')} illegal={event.get('meta',{}).get('illegal_attempt') is not None}")

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
                    total = total_cells_for_heartbeat
                    done = len(processed_pairs)
                    pct = (done / total) * 100 if total else 0
                    print(f"[heartbeat]{shard_tag} {elapsed:.0f}s policy-grid: cell={cell.get('p1')},{cell.get('p2')} vs {cell.get('du')} rep={rep+1 if isinstance(rep,int) else rep}/{args.reps} progress={done}/{total} ({pct:.1f}%)")
                    last_hb = now
            elif track == "policy":
                hand = event.get("hand")
                if isinstance(hand, int):
                    max_hand_seen = max(max_hand_seen, hand)
                if now - last_hb >= heartbeat_secs:
                    elapsed = now - start_ts
                    total = args.hands
                    done = max_hand_seen + 1
                    pct = (done / total) * 100 if total else 0
                    print(f"[heartbeat] {elapsed:.0f}s policy: hand={done}/{total} ({pct:.1f}%)")
                    last_hb = now
        if log_fh:
            event["timestamp"] = datetime.now().isoformat()
            log_fh.write(json.dumps(event) + "\n")
            log_fh.flush()

    log_fn = emit if (debug or log_fh) else None

    if args.track == "policy":
        result = run_policy_track(agent, hands=args.hands, seed=args.seed, rules=None, log_fn=log_fn)
    elif args.track == "policy-grid":
        result = run_policy_grid(
            agent,
            seed=args.seed,
            weighted=args.weighted,
            reps=args.reps,
            log_fn=log_fn,
            resume_from=getattr(args, "resume_from", None),
            shard_index=int(getattr(args, "shard_index", 0) or 0),
            num_shards=int(getattr(args, "num_shards", 1) or 1),
        )
    else:
        raise ValueError(f"Unknown track: {args.track}")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    print(json.dumps(result["metrics"], indent=2))
    
    # Print error summary
    if error_count > 0:
        print(f"\n⚠️  WARNING: {error_count} LLM errors occurred during this run.")
        print(f"   Last error: {last_error}")
        print(f"   Check the log file for details: {log_file}")
    
    if log_fh:
        log_fh.close()
        print(f"per-decision log written to {log_file}")

def _setup_logging(args: argparse.Namespace):
    log_file = getattr(args, "log_jsonl", None)
    if not log_file and getattr(args, "resume_from", None):
        log_file = args.resume_from
    if not log_file:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        Path("logs").mkdir(parents=True, exist_ok=True)
        suffix = args.agent
        if args.agent == "llm":
            model = getattr(args, "llm_model", None) or "model"
            safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "-" for ch in model)
            suffix = f"{suffix}_{safe}"
        log_file = str(Path("logs") / f"{ts}_{args.track}_{suffix}.jsonl")
    log_fh = open(log_file, "a", encoding="utf-8")
    return log_file, log_fh

def _load_processed_pairs(resume_from: str) -> set:
    processed_pairs = set()
    try:
        with open(resume_from, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
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
    return processed_pairs

def _prepare_heartbeat(args: argparse.Namespace, processed_pairs: set):
    shard_tag = ""
    total_cells_for_heartbeat = 55 * 10 * args.reps
    if args.track == "policy-grid" and getattr(args, "heartbeat_secs", 60) > 0:
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
        dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
        try:
            shard_idx = int(getattr(args, "shard_index", 0) or 0)
            num_shards = max(1, int(getattr(args, "num_shards", 1) or 1))
        except Exception:
            shard_idx, num_shards = 0, 1
        shard_cells = 0
        ci = 0
        for i, r1 in enumerate(ranks):
            for r2 in ranks[i:]:
                for _du in dealer_up:
                    if ci % num_shards == shard_idx:
                        shard_cells += 1
                    ci += 1
        total_cells_for_heartbeat = shard_cells * args.reps
        shard_tag = f" shard={shard_idx+1}/{num_shards}" if num_shards > 1 else ""
        print(f"[start]{shard_tag} policy-grid: reps={args.reps}, total_cells={total_cells_for_heartbeat}")
        if processed_pairs:
            done = len(processed_pairs)
            pct = (done / total_cells_for_heartbeat) * 100 if total_cells_for_heartbeat else 0
            print(f"[resume]{shard_tag} already completed: {done}/{total_cells_for_heartbeat} ({pct:.1f}%)")
    return shard_tag, total_cells_for_heartbeat

def cmd_run(args: argparse.Namespace) -> None:
    if max(1, int(getattr(args, "parallel", 1))) > 1:
        _run_parallel(args)
    else:
        _run_single(args)


def main():
    parser = argparse.ArgumentParser(prog="blackjack_bench", description="BlackJackBench CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run a benchmark track")
    p_run.add_argument("--agent", choices=["basic", "random", "bad", "worst", "llm", "claude-sonnet", "gpt5", "gemini-flash", "sonoma-sky", "gemma", "qwen-cli"], default="basic")
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
        help="LLM provider (openai | gemini | ollama | openrouter | anthropic)",
    )
    p_run.add_argument("--llm-model", type=str, default="gpt-4o-mini", help="LLM model name for --agent llm")
    p_run.add_argument("--llm-temperature", type=float, default=0.0, help="LLM temperature for --agent llm")
    p_run.add_argument("--llm-prompt", type=str, choices=["minimal", "rules_lite", "verbose"], default="rules_lite", help="Prompt style for --agent llm")
    # LLM reasoning
    p_run.add_argument("--reasoning", type=str, default="low", choices=["none", "low", "medium", "high"], help="LLM reasoning effort (none disables thinking)")
    # Gemini support uses the official SDK only
    p_run.add_argument("--llm-debug", action="store_true", help="Include LLM prompt in per-decision meta (response always logged)")
    # Debug/logging
    p_run.add_argument("--debug", action="store_true", help="Print per-decision debug lines to stdout")
    p_run.add_argument("--log-jsonl", type=str, default=None, help="Write per-decision JSONL events to this file")
    p_run.add_argument("--heartbeat-secs", type=int, default=60, help="Print a heartbeat line every N seconds (0 to disable)")
    p_run.add_argument("--resume-from", type=str, default=None, help="For policy-grid, resume by skipping (cell,rep) pairs already present in this JSONL log")
    # Parallel/sharding
    p_run.add_argument("--parallel", type=int, default=1, help="Run policy-grid in N parallel shards (spawns subprocesses)")
    p_run.add_argument("--num-shards", type=int, default=1, help="Advanced: total shards for this run (use with --shard-index)")
    p_run.add_argument("--shard-index", type=int, default=None, help="Advanced: process only shard INDEX (0-based), used internally when --parallel > 1")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
