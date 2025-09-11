"""Helper functions for CLI operations."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Set, Dict, Any, Callable

from .constants import MAX_CONSECUTIVE_ERRORS, DEFAULT_HEARTBEAT_SECONDS


class ErrorTracker:
    """Track LLM errors and handle error thresholds."""
    
    def __init__(self, max_consecutive: int = MAX_CONSECUTIVE_ERRORS):
        self.error_count = 0
        self.consecutive_errors = 0
        self.last_error: Optional[str] = None
        self.max_consecutive = max_consecutive
    
    def record_error(self, error_msg: str, llm_model: str = "unknown") -> bool:
        """Record an error and return True if should abort."""
        self.error_count += 1
        self.consecutive_errors += 1
        self.last_error = error_msg
        
        print(f"❌ LLM ERROR (#{self.error_count}): {error_msg}")
        
        if self.consecutive_errors >= self.max_consecutive:
            print(f"🛑 ABORTING: {self.consecutive_errors} consecutive LLM errors. Last error: {error_msg}")
            print(f"Check your API key, model name, or network connection.")
            return True
        return False
    
    def record_empty_response(self, llm_model: str, attempts: int = 1) -> bool:
        """Record an empty response and return True if should abort."""
        error_msg = f"Model {llm_model} returned empty response after {attempts} attempts"
        self.error_count += 1
        self.consecutive_errors += 1
        self.last_error = error_msg
        
        print(f"❌ LLM EMPTY RESPONSE (#{self.error_count}): {error_msg}")
        
        if self.consecutive_errors >= self.max_consecutive:
            print(f"🛑 ABORTING: {self.consecutive_errors} consecutive empty responses from {llm_model}")
            print(f"The model may not support the current prompt format or parameters.")
            print(f"Try using --llm-debug to see the exact prompt being sent.")
            return True
        return False
    
    def record_success(self) -> None:
        """Record successful operation, resetting consecutive error count."""
        self.consecutive_errors = 0
    
    def print_summary(self, log_file: str) -> None:
        """Print error summary if any errors occurred."""
        if self.error_count > 0:
            print(f"\n⚠️  WARNING: {self.error_count} LLM errors occurred during this run.")
            print(f"   Last error: {self.last_error}")
            print(f"   Check the log file for details: {log_file}")


class HeartbeatTracker:
    """Track heartbeat progress for different track types."""
    
    def __init__(self, heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS):
        self.heartbeat_seconds = heartbeat_seconds
        self.last_heartbeat = time.monotonic()
        self.start_time = self.last_heartbeat
        self.processed_pairs: Set[Tuple[str, str, str, int]] = set()
        self.max_hand_seen = -1
    
    def should_print_heartbeat(self) -> bool:
        """Check if it's time to print a heartbeat."""
        if self.heartbeat_seconds <= 0:
            return False
        now = time.monotonic()
        return now - self.last_heartbeat >= self.heartbeat_seconds
    
    def print_policy_grid_heartbeat(
        self, 
        cell: Dict[str, Any], 
        rep: int, 
        reps: int, 
        total_cells: int,
        shard_tag: str = ""
    ) -> None:
        """Print heartbeat for policy-grid track."""
        now = time.monotonic()
        elapsed = now - self.start_time
        done = len(self.processed_pairs)
        pct = (done / total_cells) * 100 if total_cells else 0
        
        rep_display = rep + 1 if isinstance(rep, int) else rep
        print(f"[heartbeat]{shard_tag} {elapsed:.0f}s policy-grid: "
              f"cell={cell.get('p1')},{cell.get('p2')} vs {cell.get('du')} "
              f"rep={rep_display}/{reps} progress={done}/{total_cells} ({pct:.1f}%)")
        
        self.last_heartbeat = now
    
    def print_policy_heartbeat(self, total_hands: int) -> None:
        """Print heartbeat for policy track.""" 
        now = time.monotonic()
        elapsed = now - self.start_time
        done = self.max_hand_seen + 1
        pct = (done / total_hands) * 100 if total_hands else 0
        
        print(f"[heartbeat] {elapsed:.0f}s policy: hand={done}/{total_hands} ({pct:.1f}%)")
        self.last_heartbeat = now
    
    def record_policy_grid_cell(self, cell: Dict[str, Any], rep: int) -> None:
        """Record a processed policy-grid cell."""
        key = (cell.get("p1"), cell.get("p2"), cell.get("du"), rep)
        self.processed_pairs.add(key)
    
    def record_policy_hand(self, hand: int) -> None:
        """Record a processed policy hand."""
        if isinstance(hand, int):
            self.max_hand_seen = max(self.max_hand_seen, hand)


def setup_logging(args) -> Tuple[str, Optional[Any]]:
    """Set up logging file and handle."""
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


def load_processed_pairs(resume_from: str) -> Set[Tuple[str, str, str, int]]:
    """Load already processed pairs from resume file."""
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


def prepare_heartbeat_info(args, processed_pairs: Set[Tuple[str, str, str, int]]) -> Tuple[str, int]:
    """Prepare heartbeat information for policy-grid runs."""
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


def create_event_emitter(
    debug: bool,
    log_fh: Optional[Any],
    heartbeat_tracker: HeartbeatTracker,
    error_tracker: ErrorTracker,
    shard_tag: str,
    total_cells_for_heartbeat: int,
    args
) -> Callable[[Dict[str, Any]], None]:
    """Create an event emission function for logging and heartbeats."""
    
    def emit(event: dict) -> None:
        # Handle LLM errors and empty responses
        meta = event.get("meta", {})
        llm_status = meta.get("llm_status")
        llm_error = meta.get("llm_error")
        llm_model = meta.get("llm_model", "unknown")
        
        should_abort = False
        if llm_status == "error" and llm_error:
            should_abort = error_tracker.record_error(llm_error, llm_model)
        elif llm_status == "empty":
            attempts = meta.get('llm_attempts', 1)
            should_abort = error_tracker.record_empty_response(llm_model, attempts)
        else:
            error_tracker.record_success()
        
        if should_abort:
            if log_fh:
                log_fh.close()
            sys.exit(1)
        
        # Debug output
        if debug:
            obs = event.get("obs", {})
            p = obs.get("player", {})
            up_full = obs.get("dealer_upcard")
            up = up_full[:-1] if isinstance(up_full, str) and len(up_full) >= 2 else up_full
            cards_full = p.get("cards", []) or []
            cards = [c[:-1] if isinstance(c, str) and len(c) >= 2 else c for c in cards_full]
            illegal = event.get('meta', {}).get('illegal_attempt') is not None
            print(f"[hand {event.get('hand')} d{event.get('decision_idx')}] "
                  f"up={up} cards={cards} act={event.get('agent_action')} "
                  f"base={event.get('baseline_action')} mistake={event.get('mistake')} "
                  f"illegal={illegal}")
        
        # Heartbeat logic
        if heartbeat_tracker.heartbeat_seconds > 0 and heartbeat_tracker.should_print_heartbeat():
            track = event.get("track")
            if track == "policy-grid":
                cell = event.get("cell", {})
                rep = event.get("rep")
                heartbeat_tracker.record_policy_grid_cell(cell, rep)
                heartbeat_tracker.print_policy_grid_heartbeat(
                    cell, rep, args.reps, total_cells_for_heartbeat, shard_tag
                )
            elif track == "policy":
                hand = event.get("hand")
                heartbeat_tracker.record_policy_hand(hand)
                heartbeat_tracker.print_policy_heartbeat(args.hands)
        
        # Track progress even when not printing heartbeat
        track = event.get("track")
        if track == "policy-grid":
            cell = event.get("cell", {})
            rep = event.get("rep") 
            heartbeat_tracker.record_policy_grid_cell(cell, rep)
        elif track == "policy":
            hand = event.get("hand")
            heartbeat_tracker.record_policy_hand(hand)
        
        # Write to log file
        if log_fh:
            event["timestamp"] = datetime.now().isoformat()
            log_fh.write(json.dumps(event) + "\n")
            log_fh.flush()
    
    return emit