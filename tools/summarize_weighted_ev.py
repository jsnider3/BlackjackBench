#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from common import (
    Cell, Key, grid_weights_infinite_deck, discover_files, 
    load_events, norm_rank, extract_model_name, safe_float_format, 
    DEFAULT_PRECISION
)


def get_basic_strategy_difficulty(cell: Cell) -> float:
    """
    Estimate relative difficulty/EV for a cell using basic strategy knowledge.
    Higher values = easier scenarios, lower values = harder scenarios.
    """
    p1, p2, du = cell
    
    # Convert face cards for consistent handling
    p1, p2, du = norm_rank(p1), norm_rank(p2), norm_rank(du)
    
    # Calculate hand total
    def card_val(rank: str) -> int:
        if rank == 'A':
            return 11
        return min(int(rank), 10)
    
    total = card_val(p1) + card_val(p2)
    is_soft = (p1 == 'A' or p2 == 'A') and total <= 21
    is_pair = p1 == p2
    
    # Convert Ace from 11 to 1 if busting
    if total > 21 and (p1 == 'A' or p2 == 'A'):
        total -= 10
        is_soft = True
    
    dealer_val = card_val(du)
    
    # Rough difficulty scoring based on basic strategy EV
    difficulty = 0.0
    
    # Dealer strength factor (weak dealers make scenarios easier)
    if dealer_val in [4, 5, 6]:  # Weak dealers
        difficulty += 0.15
    elif dealer_val in [2, 3]:  # Moderately weak
        difficulty += 0.05
    elif dealer_val in [7, 8]:  # Moderate
        difficulty -= 0.05
    else:  # Strong dealers (9, 10, A)
        difficulty -= 0.15
    
    # Player hand strength
    if is_pair:
        if p1 == 'A':  # Pair of Aces
            difficulty += 0.2
        elif p1 == '10':  # Pair of 10s
            difficulty += 0.3
        elif p1 == '8':  # Pair of 8s
            difficulty += 0.1
        elif p1 in ['4', '5', '6']:  # Low pairs vs weak dealers can be good
            difficulty += 0.05
        else:
            difficulty -= 0.05
    elif is_soft:
        if total >= 19:  # Soft 19-20
            difficulty += 0.2
        elif total >= 17:  # Soft 17-18
            difficulty += 0.05
        else:  # Low soft hands
            difficulty -= 0.1
    else:  # Hard hands
        if total >= 17:
            if dealer_val >= 7:  # Hard 17+ vs strong dealer
                difficulty -= 0.3
            else:
                difficulty += 0.1
        elif total >= 12:
            if dealer_val <= 6:  # Stiff vs weak dealer
                difficulty += 0.05
            else:
                difficulty -= 0.2
        else:  # Low hard totals
            difficulty -= 0.15
    
    return difficulty


def calculate_difficulty_bias(covered_cells: List[Cell], all_weights: Dict[Cell, float]) -> Dict[str, float]:
    """Calculate difficulty bias metrics for the covered cells vs full grid."""
    if not covered_cells:
        return {"bias": 0.0, "coverage_pct": 0.0, "weight_coverage_pct": 0.0}
    
    # Get difficulty scores for covered cells
    covered_difficulties = [get_basic_strategy_difficulty(cell) for cell in covered_cells]
    covered_weights = [all_weights.get(cell, 0.0) for cell in covered_cells]
    
    # Get difficulty scores for all cells  
    all_cells = list(all_weights.keys())
    all_difficulties = [get_basic_strategy_difficulty(cell) for cell in all_cells]
    all_weights_list = list(all_weights.values())
    
    # Weighted averages
    covered_difficulty_avg = (
        sum(d * w for d, w in zip(covered_difficulties, covered_weights)) / sum(covered_weights)
        if sum(covered_weights) > 0 else 0.0
    )
    all_difficulty_avg = sum(d * w for d, w in zip(all_difficulties, all_weights_list)) / sum(all_weights_list)
    
    # Bias calculation
    bias = covered_difficulty_avg - all_difficulty_avg
    
    # Coverage stats
    coverage_pct = len(covered_cells) / len(all_cells) * 100
    weight_coverage_pct = sum(covered_weights) / sum(all_weights_list) * 100
    
    return {
        "bias": bias,
        "coverage_pct": coverage_pct, 
        "weight_coverage_pct": weight_coverage_pct,
        "covered_difficulty_avg": covered_difficulty_avg,
        "all_difficulty_avg": all_difficulty_avg
    }


def summarize_file(path: Path, smart_correction: bool = False) -> Dict[str, Any]:
    """
    Summarize weighted expected value from a policy-grid JSONL file.
    
    Args:
        path: Path to JSONL file
        smart_correction: Whether to apply difficulty bias correction
        
    Returns:
        Dictionary with EV metrics and statistics
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If no valid data is found in the file
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    weights = grid_weights_infinite_deck()
    # Track per (cell, rep) reward; ignore duplicate events within the same hand
    per_hand: Dict[Key, float] = {}
    # Also accumulate decision/mistake counts for context
    decisions = 0
    mistakes = 0
    for ev in load_events(path):
        if ev.get("track") != "policy-grid":
            continue
        cell = ev.get("cell") or {}
        rep = ev.get("rep")
        if not isinstance(rep, int):
            continue
        p1, p2, du = cell.get("p1"), cell.get("p2"), cell.get("du")
        if not (isinstance(p1, str) and isinstance(p2, str) and isinstance(du, str)):
            continue
        key: Key = (p1, p2, du, rep)
        # Grab final.reward once per hand
        if key not in per_hand:
            final = ev.get("final") or {}
            reward = final.get("reward")
            if isinstance(reward, (int, float)):
                per_hand[key] = float(reward)
        # Decision and mistake counters
        a = ev.get("agent_action")
        b = ev.get("baseline_action")
        if isinstance(a, str) and isinstance(b, str):
            decisions += 1
            if a != b:
                mistakes += 1

    # Aggregate to per-cell averages across reps
    by_cell: Dict[Cell, List[float]] = defaultdict(list)
    for (p1, p2, du, _rep), rew in per_hand.items():
        by_cell[(p1, p2, du)].append(rew)

    # Weighted EV over available cells
    weighted_return = 0.0
    sum_w = 0.0
    covered_cells = []
    for cell, rewards in by_cell.items():
        if not rewards:
            continue
        avg = sum(rewards) / len(rewards)
        w = weights.get(cell)
        if w is None:
            # Normalize face cards to '10' if necessary (defensive)
            r1, r2, du = cell
            w = weights.get((norm_rank(r1), norm_rank(r2), norm_rank(du)), 0.0)
        weighted_return += avg * w
        sum_w += w
        covered_cells.append(cell)

    # Validate we found some data
    if not per_hand:
        raise ValueError(f"No valid policy-grid data found in {path}")
    
    # Standard weighted EV
    ev_weighted = (weighted_return / sum_w) if sum_w > 0 else 0.0
    
    # Smart correction if requested
    result = {
        "file": str(path),
        "model": extract_model_name(path),
        "ev_weighted": ev_weighted,
        "sum_weights": sum_w,
        "cells_covered": len(covered_cells),
        "hands": len(per_hand),
        "ev_unweighted": (sum(per_hand.values()) / len(per_hand)) if per_hand else 0.0,
        "decisions": decisions,
        "mistake_rate": (mistakes / decisions) if decisions > 0 else 0.0,
    }
    
    if smart_correction and covered_cells:
        bias_analysis = calculate_difficulty_bias(covered_cells, weights)
        
        # Apply bias correction
        # Positive bias = easier scenarios covered, so agent's EV is inflated
        # Negative bias = harder scenarios covered, so agent's EV is deflated
        bias_factor = bias_analysis["bias"]
        ev_corrected = ev_weighted - (bias_factor * 0.5)  # Scale the correction
        
        result.update({
            "ev_weighted_corrected": ev_corrected,
            "difficulty_bias": bias_factor,
            "bias_direction": "easier" if bias_factor > 0.02 else ("harder" if bias_factor < -0.02 else "neutral"),
            "coverage_pct": bias_analysis["coverage_pct"],
            "weight_coverage_pct": bias_analysis["weight_coverage_pct"],
        })
    
    return result


def main():
    ap = argparse.ArgumentParser(description="Summarize weighted EV from policy-grid JSONL logs.")
    ap.add_argument("inputs", nargs="*", default=["baselines"], help="Files, directories, or globs (default: baselines)")
    ap.add_argument("--track", choices=["policy-grid"], default="policy-grid", help="Track to summarize (policy-grid only)")
    ap.add_argument("--smart", action="store_true", help="Apply difficulty bias correction for incomplete datasets")
    args = ap.parse_args()

    files = discover_files(args.inputs)
    if not files:
        print("No .jsonl files found.", file=sys.stderr)
        return 1

    # Process files with error handling
    rows = []
    for p in files:
        try:
            result = summarize_file(p, smart_correction=args.smart)
            rows.append(result)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error processing {p}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Unexpected error processing {p}: {e}", file=sys.stderr)
            continue

    if not rows:
        print("No files could be processed successfully.", file=sys.stderr)
        return 1
    
    # Format output table
    if args.smart:
        headers = ["model", "ev_weighted", "ev_weighted_corrected", "difficulty_bias", "bias_direction", 
                  "coverage_pct", "cells_covered", "hands", "mistake_rate", "file"]
    else:
        headers = ["model", "ev_weighted", "sum_weights", "cells_covered", "hands", "mistake_rate", "file"]
    
    def fmt(x):
        if isinstance(x, float):
            return safe_float_format(x)
        return str(x)
    
    table_rows = []
    for r in rows:
        table_rows.append([fmt(r.get(h, '')) for h in headers])
    
    # Print formatted table
    from common import format_table
    print(format_table(headers, table_rows))


if __name__ == "__main__":
    sys.exit(main() or 0)
