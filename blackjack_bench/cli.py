from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import time
import sys
import subprocess
import json
from typing import Any, Optional, Callable, Dict

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
from .constants import (
    DEFAULT_OPENAI_MODEL, DEFAULT_TEMPERATURE, DEFAULT_PROMPT_MODE, 
    DEFAULT_REASONING_LEVEL, AVAILABLE_AGENTS, DEFAULT_HEARTBEAT_SECONDS
)
from .agent_utils import validate_agent_parameters
from .cli_helpers import (
    ErrorTracker, HeartbeatTracker, setup_logging, load_processed_pairs,
    prepare_heartbeat_info, create_event_emitter
)


def _extract_llm_params(args: Optional[argparse.Namespace]) -> dict[str, Any]:
    """Extract and validate LLM parameters from arguments."""
    if args is None:
        return {
            "provider": "openai",
            "model": DEFAULT_OPENAI_MODEL,
            "temperature": DEFAULT_TEMPERATURE,
            "prompt_mode": DEFAULT_PROMPT_MODE,
            "debug_log": False,
            "reasoning": DEFAULT_REASONING_LEVEL,
        }
    
    provider = getattr(args, "llm_provider", None) or "openai"
    model = getattr(args, "llm_model", None) or DEFAULT_OPENAI_MODEL
    temperature = getattr(args, "llm_temperature", DEFAULT_TEMPERATURE)
    prompt_mode = getattr(args, "llm_prompt", DEFAULT_PROMPT_MODE)
    llm_debug = getattr(args, "llm_debug", False)
    reasoning = getattr(args, "reasoning", DEFAULT_REASONING_LEVEL)
    
    # Validate parameters
    validate_agent_parameters(
        provider=provider,
        model=model,
        temperature=temperature,
        prompt_mode=prompt_mode,
        reasoning=reasoning,
    )
    
    return {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "prompt_mode": prompt_mode,
        "debug_log": llm_debug,
        "reasoning": reasoning,
    }


def build_agent(name: str, args: argparse.Namespace | None = None) -> Any:
    """Build an agent instance by name.
    
    Args:
        name: Agent type name
        args: Command line arguments (optional)
        
    Returns:
        Agent instance
        
    Raises:
        ValueError: If agent name is unknown
    """
    if name not in AVAILABLE_AGENTS:
        raise ValueError(f"Unknown agent: {name}. Available: {', '.join(sorted(AVAILABLE_AGENTS))}")
    
    # Simple agents with no parameters
    if name == "basic":
        return BasicStrategyAgent()
    if name == "random":
        return RandomAgent()
    if name in ("bad", "worst"):
        return BadAgent()
    
    # Configurable LLM agent
    if name == "llm":
        params = _extract_llm_params(args)
        return LLMAgent(**params)
    
    # Fixed model agents
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
        debug_log = getattr(args, "llm_debug", False) if args else False
        return QwenCLIAgent(debug_log=debug_log)
    
    # Should never reach here due to AVAILABLE_AGENTS check above
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
    """Execute a single benchmark run with the given arguments.
    
    Args:
        args: Parsed command line arguments
    """
    # Set up agent
    agent = build_agent(args.agent, args)
    if args.guard:
        agent = GuardedAgent(agent)

    # Set up logging and tracking
    debug = getattr(args, "debug", False)
    log_file, log_fh = setup_logging(args)
    
    error_tracker = ErrorTracker()
    heartbeat_secs = max(0, int(getattr(args, "heartbeat_secs", DEFAULT_HEARTBEAT_SECONDS)))
    heartbeat_tracker = HeartbeatTracker(heartbeat_secs)

    # Handle resume functionality
    if getattr(args, "resume_from", None) and args.track == "policy-grid":
        heartbeat_tracker.processed_pairs = load_processed_pairs(args.resume_from)

    shard_tag, total_cells_for_heartbeat = prepare_heartbeat_info(args, heartbeat_tracker.processed_pairs)

    # Create event emitter
    emit = create_event_emitter(
        debug, log_fh, heartbeat_tracker, error_tracker, 
        shard_tag, total_cells_for_heartbeat, args
    )
    log_fn = emit if (debug or log_fh) else None

    # Execute the benchmark
    result = _run_benchmark(args, agent, log_fn)
    
    # Output results
    _output_results(args, result)
    
    # Cleanup and summary
    error_tracker.print_summary(log_file)
    if log_fh:
        log_fh.close()
        print(f"per-decision log written to {log_file}")


def _run_benchmark(args: argparse.Namespace, agent: Any, log_fn: Optional[Callable]) -> Dict[str, Any]:
    """Run the actual benchmark based on track type."""
    if args.track == "policy":
        return run_policy_track(agent, hands=args.hands, seed=args.seed, rules=None, log_fn=log_fn)
    elif args.track == "policy-grid":
        return run_policy_grid(
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


def _output_results(args: argparse.Namespace, result: Dict[str, Any]) -> None:
    """Output benchmark results to report file and stdout.""" 
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    print(json.dumps(result["metrics"], indent=2))


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
