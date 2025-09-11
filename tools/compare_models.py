#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import statistics
import math

from common import (
    Cell, Key, grid_weights_infinite_deck, discover_files, load_events,
    classify_decision, extract_model_name, format_table, norm_rank, RANK_ORDER
)


def analyze_file(path: Path, track: str = "policy-grid") -> Dict[str, Any]:
    """Analyze a single baseline file and return comprehensive metrics."""
    weights = grid_weights_infinite_deck()
    
    # Per-hand rewards for EV calculation
    per_hand: Dict[Key, float] = {}
    
    # Decision and mistake tracking
    decisions = 0
    mistakes = 0
    
    # Category-wise tracking
    category_decisions: Dict[str, int] = defaultdict(int)
    category_mistakes: Dict[str, int] = defaultdict(int)
    
    # Thinking analysis (for LLM models)
    thinking_tokens: List[float] = []
    has_thinking = False
    
    for ev in load_events(path):
        if ev.get("track") != track:
            continue
            
        # Extract final reward once per hand
        cell = ev.get("cell") or {}
        rep = ev.get("rep")
        if isinstance(rep, int):
            p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
            p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
            du = norm_rank(str(cell.get("du"))) if cell.get("du") else None
            if p1 and p2 and du:
                key: Key = (p1, p2, du, rep)
                if key not in per_hand:
                    final = ev.get("final") or {}
                    reward = final.get("reward")
                    if isinstance(reward, (int, float)):
                        per_hand[key] = float(reward)
        
        # Decision analysis
        if ev.get("decision_idx") is None:
            continue
            
        a = ev.get("agent_action")
        b = ev.get("baseline_action")
        if not isinstance(a, str) or not isinstance(b, str):
            continue
            
        decisions += 1
        category, _ = classify_decision(ev)
        category_decisions[category] += 1
        
        if a != b:
            mistakes += 1
            category_mistakes[category] += 1
            
        # Thinking analysis
        meta = ev.get("meta") or {}
        if "llm_thinking" in meta:
            has_thinking = True
            usage = meta.get("llm_usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            total_tokens = usage.get("total_tokens")
            if isinstance(total_tokens, (int, float)) and isinstance(prompt_tokens, (int, float)):
                thinking_tokens.append(float(total_tokens) - float(prompt_tokens))
    
    # Calculate weighted EV and collect per-hand rewards for confidence intervals
    by_cell: Dict[Cell, List[float]] = defaultdict(list)
    all_hand_rewards: List[float] = []  # For confidence interval calculation
    
    for (p1, p2, du, _rep), rew in per_hand.items():
        by_cell[(p1, p2, du)].append(rew)
        all_hand_rewards.append(rew)
    
    weighted_return = 0.0
    sum_w = 0.0
    cells_covered = 0
    
    for cell, rewards in by_cell.items():
        if not rewards:
            continue
        avg = sum(rewards) / len(rewards)
        w = weights.get(cell, 0.0)
        weighted_return += avg * w
        sum_w += w
        cells_covered += 1
    
    ev_weighted = (weighted_return / sum_w) if sum_w else 0.0
    
    # Compute confidence interval for EV
    ci_lower, ci_upper = compute_confidence_interval(all_hand_rewards) if all_hand_rewards else (0.0, 0.0)
    mistake_rate = (mistakes / decisions) if decisions else 0.0
    
    # Extract model name from filename
    model = extract_model_name(path)
    
    result = {
        "file": str(path),
        "model": model,
        "decisions": decisions,
        "mistakes": mistakes,
        "mistake_rate": mistake_rate,
        "ev_weighted": ev_weighted,
        "ev_ci_lower": ci_lower,
        "ev_ci_upper": ci_upper,
        "cells_covered": cells_covered,
        "hands": len(per_hand),
        "category_breakdown": {
            cat: {
                "decisions": category_decisions[cat],
                "mistakes": category_mistakes[cat],
                "mistake_rate": (category_mistakes[cat] / category_decisions[cat]) if category_decisions[cat] else 0.0
            }
            for cat in set(category_decisions.keys()) | set(category_mistakes.keys())
        }
    }
    
    if has_thinking and thinking_tokens:
        result["thinking"] = {
            "has_thinking": True,
            "avg_tokens": statistics.mean(thinking_tokens),
            "median_tokens": statistics.median(thinking_tokens),
            "max_tokens": max(thinking_tokens),
            "min_tokens": min(thinking_tokens)
        }
    else:
        result["thinking"] = {"has_thinking": False}
    
    return result


def compute_confidence_interval(values: List[float], confidence: float = 0.95) -> Tuple[float, float]:
    """Compute confidence interval for a list of values."""
    if len(values) < 2:
        return (0.0, 0.0)
    
    mean = statistics.mean(values)
    std = statistics.stdev(values)
    n = len(values)
    
    # Use t-distribution for small samples
    from math import sqrt
    try:
        # Approximate critical value for 95% confidence
        t_critical = 1.96 if n > 30 else 2.0
        margin = t_critical * (std / sqrt(n))
        return (mean - margin, mean + margin)
    except Exception:
        return (mean, mean)


def format_comparison_table(analyses: List[Dict[str, Any]], category_filter: Optional[str] = None) -> None:
    """Print a formatted comparison table."""
    if not analyses:
        print("No models to compare.")
        return
    
    # Headers
    headers = ["Model", "Decisions", "Mistakes", "Mistake Rate", "Weighted EV", "95% CI", "Hands", "Cells"]
    
    # Add thinking columns if any model has thinking
    has_thinking_models = any(a["thinking"]["has_thinking"] for a in analyses)
    if has_thinking_models:
        headers.extend(["Avg Thinking Tokens", "Max Thinking Tokens"])
    
    # Add category-specific columns if filtering
    if category_filter:
        headers.extend([f"{category_filter} Decisions", f"{category_filter} Mistake Rate"])
    
    # Build rows
    rows = []
    for analysis in analyses:
        # Format confidence interval
        ci_str = f"[{analysis['ev_ci_lower']:.4f}, {analysis['ev_ci_upper']:.4f}]"
        
        row = [
            analysis["model"],
            str(analysis["decisions"]),
            str(analysis["mistakes"]),
            f"{analysis['mistake_rate']:.3f}",
            f"{analysis['ev_weighted']:.6f}",
            ci_str,
            str(analysis["hands"]),
            str(analysis["cells_covered"])
        ]
        
        if has_thinking_models:
            thinking = analysis["thinking"]
            if thinking["has_thinking"]:
                row.extend([
                    f"{thinking['avg_tokens']:.0f}",
                    f"{thinking['max_tokens']:.0f}"
                ])
            else:
                row.extend(["N/A", "N/A"])
        
        if category_filter:
            cat_data = analysis["category_breakdown"].get(category_filter, {"decisions": 0, "mistake_rate": 0.0})
            row.extend([
                str(cat_data["decisions"]),
                f"{cat_data['mistake_rate']:.3f}"
            ])
        
        rows.append(row)
    
    # Print formatted table
    print(format_table(headers, [[str(cell) for cell in row] for row in rows]))
    print("-" * 80)  # Separator line


def print_statistical_comparison(analyses: List[Dict[str, Any]]) -> None:
    """Print statistical comparison between models."""
    if len(analyses) < 2:
        print("\nNeed at least 2 models for statistical comparison.")
        return
    
    print(f"\n# Statistical Comparison ({len(analyses)} models)")
    
    # Sort by weighted EV for ranking
    sorted_analyses = sorted(analyses, key=lambda x: x["ev_weighted"], reverse=True)
    
    print("\nRanking by Weighted EV:")
    for i, analysis in enumerate(sorted_analyses, 1):
        print(f"  {i}. {analysis['model']}: {analysis['ev_weighted']:.6f} "
              f"(±{analysis['mistake_rate']:.3f} mistake rate)")
    
    # Pairwise comparisons for top models
    if len(analyses) >= 2:
        best = sorted_analyses[0]
        second = sorted_analyses[1]
        ev_diff = best["ev_weighted"] - second["ev_weighted"]
        mistake_diff = second["mistake_rate"] - best["mistake_rate"]
        
        print(f"\nTop performer ({best['model']}) vs second ({second['model']}):")
        print(f"  EV advantage: {ev_diff:+.6f} units/hand")
        print(f"  Mistake rate advantage: {mistake_diff:+.3f}")


def save_csv_report(analyses: List[Dict[str, Any]], output_path: str) -> None:
    """Save comparison results to CSV."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Headers
        headers = ["model", "decisions", "mistakes", "mistake_rate", "ev_weighted", "ev_ci_lower", "ev_ci_upper", "hands", "cells_covered"]
        
        # Add thinking headers if applicable
        has_thinking = any(a["thinking"]["has_thinking"] for a in analyses)
        if has_thinking:
            headers.extend(["avg_thinking_tokens", "max_thinking_tokens"])
        
        writer.writerow(headers)
        
        # Data rows
        for analysis in analyses:
            row = [
                analysis["model"],
                analysis["decisions"],
                analysis["mistakes"],
                f"{analysis['mistake_rate']:.6f}",
                f"{analysis['ev_weighted']:.6f}",
                f"{analysis['ev_ci_lower']:.6f}",
                f"{analysis['ev_ci_upper']:.6f}",
                analysis["hands"],
                analysis["cells_covered"]
            ]
            
            if has_thinking:
                thinking = analysis["thinking"]
                if thinking["has_thinking"]:
                    row.extend([
                        f"{thinking['avg_tokens']:.2f}",
                        f"{thinking['max_tokens']:.0f}"
                    ])
                else:
                    row.extend(["", ""])
            
            writer.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Compare multiple blackjack models head-to-head")
    ap.add_argument("inputs", nargs="+", help="JSONL files, directories, or globs to analyze")
    ap.add_argument("--models", help="Comma-separated list of model names to filter (partial match)")
    ap.add_argument("--category", choices=["pairs", "soft", "hard"], help="Focus on specific decision category")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default="policy-grid", help="Track to analyze")
    ap.add_argument("--csv", help="Save results to CSV file")
    ap.add_argument("--sort-by", choices=["ev", "mistakes", "decisions"], default="ev", help="Sort results by metric")
    ap.add_argument("--statistical", action="store_true", help="Include statistical analysis")
    args = ap.parse_args()
    
    # Discover files
    files = discover_files(args.inputs)
    if not files:
        print("No JSONL files found.")
        return
    
    # Filter by model names if specified
    if args.models:
        model_filters = [m.strip().lower() for m in args.models.split(",")]
        filtered_files = []
        for f in files:
            if any(filter_name in f.name.lower() for filter_name in model_filters):
                filtered_files.append(f)
        files = filtered_files
        
        if not files:
            print(f"No files found matching model filters: {args.models}")
            return
    
    print(f"Analyzing {len(files)} model files...")
    
    # Analyze each file
    analyses = []
    for f in files:
        try:
            analysis = analyze_file(f, args.track)
            analyses.append(analysis)
        except Exception as e:
            print(f"Error analyzing {f}: {e}")
    
    if not analyses:
        print("No successful analyses.")
        return
    
    # Sort results
    if args.sort_by == "ev":
        analyses.sort(key=lambda x: x["ev_weighted"], reverse=True)
    elif args.sort_by == "mistakes":
        analyses.sort(key=lambda x: x["mistake_rate"])
    elif args.sort_by == "decisions":
        analyses.sort(key=lambda x: x["decisions"], reverse=True)
    
    # Filter category if specified
    category_filter = None
    if args.category:
        if args.category == "pairs":
            category_filter = None  # Will show all pairs in detailed view
        else:
            category_filter = args.category
    
    # Print comparison table
    format_comparison_table(analyses, category_filter)
    
    # Statistical analysis
    if args.statistical:
        print_statistical_comparison(analyses)
    
    # Category breakdown
    if not category_filter:
        print(f"\n# Category Breakdown")
        categories = set()
        for analysis in analyses:
            categories.update(analysis["category_breakdown"].keys())
        
        for category in sorted(categories):
            if args.category == "pairs" and not category.startswith("pair"):
                continue
            if args.category == "soft" and not category.startswith("soft"):
                continue
            if args.category == "hard" and not category.startswith("hard"):
                continue
                
            print(f"\n## {category}")
            for analysis in analyses:
                cat_data = analysis["category_breakdown"].get(category, {"decisions": 0, "mistakes": 0, "mistake_rate": 0.0})
                if cat_data["decisions"] > 0:
                    print(f"  {analysis['model']}: {cat_data['mistakes']}/{cat_data['decisions']} "
                          f"({cat_data['mistake_rate']:.3f} mistake rate)")
    
    # Save CSV if requested
    if args.csv:
        save_csv_report(analyses, args.csv)
        print(f"\nSaved CSV report to {args.csv}")


if __name__ == "__main__":
    main()