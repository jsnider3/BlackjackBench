#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional, Set, Any
import csv


def norm_rank(r: str) -> str:
    """Normalize face cards to '10'."""
    return "10" if r in {"10", "J", "Q", "K"} else r


def load_events(path: Path) -> Iterable[dict]:
    """Load JSONL events from a file."""
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def discover_files(inputs: List[str]) -> List[Path]:
    """Discover files from inputs (files, dirs, globs)."""
    files: List[Path] = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            files.extend(sorted(p.glob("*.jsonl")))
        elif any(ch in inp for ch in "*?["):
            files.extend(sorted(Path().glob(inp)))
        else:
            files.append(p)
    # Deduplicate
    out: List[Path] = []
    seen = set()
    for f in files:
        if f.exists() and f.suffix == ".jsonl" and f not in seen:
            out.append(f)
            seen.add(f)
    return out


def discover_strategy_files(strategy_dir: Path) -> List[Path]:
    """Discover strategy files from model_thoughts directory."""
    files = []
    if strategy_dir.is_dir():
        for ext in ["*.md", "*.txt"]:
            files.extend(sorted(strategy_dir.glob(ext)))
    return files


def extract_model_name_from_baseline(path: Path) -> str:
    """Extract model name from baseline filename."""
    name = path.name
    # Try to extract from pattern: timestamp_track_llm_modelname.jsonl
    if "_llm_" in name:
        return name.split("_llm_")[-1].rsplit(".", 1)[0]
    # Fallback to last segment
    return name.split("_")[-1].rsplit(".", 1)[0] if "_" in name else name.rsplit(".", 1)[0]


def extract_model_name_from_strategy(path: Path) -> str:
    """Extract model name from strategy filename."""
    name = path.stem  # Remove extension
    # Common patterns in model_thoughts directory
    name = name.replace("_thoughts", "").replace("_grounded", "")
    return name.replace("_", "-").lower()


def is_model_match(strategy_model: str, baseline_model: str) -> bool:
    """Check if a strategy model matches a baseline model with flexible rules."""
    strategy_model = strategy_model.lower()
    baseline_model = baseline_model.lower()
    
    # Exact match
    if strategy_model == baseline_model:
        return True
    
    # Handle underscore/hyphen differences
    if strategy_model.replace("-", "_") == baseline_model.replace("-", "_"):
        return True
    
    # Special cases for Gemini models
    if "gemini-2-5-flash" in strategy_model and "gemini-2-5-flash" in baseline_model:
        # "gemini-2-5-flash" strategy should match "gemini-2-5-flash-thinking" baseline (main model)
        if strategy_model == "gemini-2-5-flash" and baseline_model == "gemini-2-5-flash-thinking":
            return True
        
        # "gemini-2-5-flash-no-thinking-no" should match "gemini-2-5-flash-no-thinking"
        if strategy_model == "gemini-2-5-flash-no-thinking-no" and baseline_model == "gemini-2-5-flash-no-thinking":
            return True
    
    return False


def parse_strategy_rules(content: str) -> Dict[str, List[str]]:
    """Parse strategy rules from model thoughts content."""
    rules = {
        "always_split": [],
        "never_split": [],
        "always_double": [],
        "never_double": [],
        "always_hit": [],
        "always_stand": [],
        "general_rules": []
    }
    
    content_lower = content.lower()
    lines = content.split('\n')
    
    # Patterns for extracting specific rules
    patterns = {
        "always_split": [
            r"always split ([a-a,\s\d/]+)",
            r"split ([a-a,\s\d/]+) always",
            r"(\w+/\w+|\w+) should always be split",
        ],
        "never_split": [
            r"never split ([10s,\sface\scards\d/]+)",
            r"don't split ([10s,\sface\scards\d/]+)",
            r"(\w+/\w+|\w+) should never be split",
        ],
        "always_double": [
            r"always double (?:down )?(?:on )?(\d+)",
            r"double (?:down )?(?:on )?(\d+) always",
        ],
        "never_double": [
            r"never double (?:down )?(?:on )?([^.]+)",
            r"don't double (?:down )?(?:on )?([^.]+)",
        ]
    }
    
    # Extract specific patterns
    for rule_type, rule_patterns in patterns.items():
        for pattern in rule_patterns:
            matches = re.findall(pattern, content_lower)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                rules[rule_type].append(match.strip())
    
    # Extract general strategic statements
    strategy_indicators = [
        "basic strategy", "optimal play", "recommended", "should", "must",
        "correct play", "proper strategy", "standard approach"
    ]
    
    for line in lines:
        line_lower = line.lower().strip()
        if any(indicator in line_lower for indicator in strategy_indicators):
            if len(line.strip()) > 10 and len(line.strip()) < 200:  # Reasonable length
                rules["general_rules"].append(line.strip())
    
    return rules


def normalize_hand_description(desc: str) -> Set[Tuple[str, str]]:
    """Normalize hand descriptions to standard format."""
    desc = desc.lower().strip()
    hands = set()
    
    # Handle common patterns
    if "a/a" in desc or "aces" in desc or "ace" in desc:
        hands.add(("A", "A"))
    if "8/8" in desc or "eights" in desc:
        hands.add(("8", "8"))
    if "10/10" in desc or "tens" in desc or "face" in desc:
        hands.add(("10", "10"))
    if "2/2" in desc or "twos" in desc:
        hands.add(("2", "2"))
    if "3/3" in desc or "threes" in desc:
        hands.add(("3", "3"))
    if "4/4" in desc or "fours" in desc:
        hands.add(("4", "4"))
    if "5/5" in desc or "fives" in desc:
        hands.add(("5", "5"))
    if "6/6" in desc or "sixes" in desc:
        hands.add(("6", "6"))
    if "7/7" in desc or "sevens" in desc:
        hands.add(("7", "7"))
    if "9/9" in desc or "nines" in desc:
        hands.add(("9", "9"))
    
    # Handle numeric ranges
    numbers = re.findall(r'\b(\d+)\b', desc)
    for num in numbers:
        if num in ["11", "21"]:  # These are totals, not pairs
            continue
        hands.add((num, num))
    
    return hands


def analyze_baseline_decisions(path: Path, track: str = "policy-grid") -> Dict[str, Any]:
    """Analyze actual decisions made by a model."""
    decisions = {
        "split_decisions": defaultdict(lambda: defaultdict(int)),  # (p1,p2) -> {action: count}
        "double_decisions": defaultdict(lambda: defaultdict(int)),  # total -> {action: count}
        "total_decisions": 0,
        "pairs_encountered": set(),
        "totals_encountered": set()
    }
    
    for ev in load_events(path):
        if ev.get("track") != track:
            continue
        if ev.get("decision_idx") != 0:  # Focus on first decisions
            continue
            
        obs = ev.get("obs") or {}
        player = obs.get("player") or {}
        cell = ev.get("cell") or {}
        
        p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
        p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
        total = player.get("total")
        agent_action = ev.get("agent_action")
        
        if not (p1 and p2 and agent_action):
            continue
            
        decisions["total_decisions"] += 1
        
        # Track pair decisions
        if p1 == p2:
            pair_key = (p1, p2)
            decisions["split_decisions"][pair_key][agent_action] += 1
            decisions["pairs_encountered"].add(pair_key)
        
        # Track double decisions by total
        if isinstance(total, int):
            decisions["double_decisions"][total][agent_action] += 1
            decisions["totals_encountered"].add(total)
    
    return decisions


def check_split_consistency(rules: Dict[str, List[str]], decisions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check consistency of splitting rules."""
    violations = []
    
    # Check "always split" rules
    for rule in rules["always_split"]:
        expected_hands = normalize_hand_description(rule)
        for p1, p2 in expected_hands:
            pair_key = (p1, p2)
            if pair_key in decisions["split_decisions"]:
                split_count = decisions["split_decisions"][pair_key].get("SPLIT", 0)
                total_count = sum(decisions["split_decisions"][pair_key].values())
                split_rate = split_count / total_count if total_count > 0 else 0.0
                
                if split_rate < 0.9:  # Allow some tolerance
                    violations.append({
                        "rule_type": "always_split",
                        "rule_text": rule,
                        "hand": f"{p1}/{p2}",
                        "expected": "SPLIT",
                        "actual_rate": split_rate,
                        "decisions": dict(decisions["split_decisions"][pair_key]),
                        "severity": "high" if split_rate < 0.5 else "medium"
                    })
    
    # Check "never split" rules
    for rule in rules["never_split"]:
        expected_hands = normalize_hand_description(rule)
        for p1, p2 in expected_hands:
            pair_key = (p1, p2)
            if pair_key in decisions["split_decisions"]:
                split_count = decisions["split_decisions"][pair_key].get("SPLIT", 0)
                total_count = sum(decisions["split_decisions"][pair_key].values())
                split_rate = split_count / total_count if total_count > 0 else 0.0
                
                if split_rate > 0.1:  # Allow some tolerance
                    violations.append({
                        "rule_type": "never_split",
                        "rule_text": rule,
                        "hand": f"{p1}/{p2}",
                        "expected": "NOT SPLIT",
                        "actual_rate": split_rate,
                        "decisions": dict(decisions["split_decisions"][pair_key]),
                        "severity": "high" if split_rate > 0.5 else "medium"
                    })
    
    return violations


def check_double_consistency(rules: Dict[str, List[str]], decisions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Check consistency of doubling rules."""
    violations = []
    
    # Extract totals from "always double" rules
    for rule in rules["always_double"]:
        # Look for numeric totals in the rule
        numbers = re.findall(r'\b(\d+)\b', rule)
        for num_str in numbers:
            try:
                total = int(num_str)
                if 5 <= total <= 21 and total in decisions["double_decisions"]:
                    double_count = decisions["double_decisions"][total].get("DOUBLE", 0)
                    total_count = sum(decisions["double_decisions"][total].values())
                    double_rate = double_count / total_count if total_count > 0 else 0.0
                    
                    if double_rate < 0.3:  # More lenient for doubling (context-dependent)
                        violations.append({
                            "rule_type": "always_double",
                            "rule_text": rule,
                            "hand": f"total {total}",
                            "expected": "DOUBLE",
                            "actual_rate": double_rate,
                            "decisions": dict(decisions["double_decisions"][total]),
                            "severity": "medium" if double_rate < 0.1 else "low"
                        })
            except ValueError:
                continue
    
    return violations


def format_violations_report(violations: List[Dict[str, Any]], model_name: str) -> None:
    """Format and print violations report."""
    if not violations:
        print(f"\n{model_name}: No strategy violations detected!")
        return
    
    print(f"\n# Strategy Violations for {model_name}")
    print(f"Found {len(violations)} potential violations:")
    
    # Group by severity
    by_severity = defaultdict(list)
    for v in violations:
        by_severity[v["severity"]].append(v)
    
    for severity in ["high", "medium", "low"]:
        if severity not in by_severity:
            continue
            
        print(f"\n## {severity.upper()} Severity ({len(by_severity[severity])} violations)")
        
        for v in by_severity[severity]:
            print(f"\n**{v['rule_type'].replace('_', ' ').title()}**: {v['rule_text']}")
            print(f"  Hand: {v['hand']}")
            print(f"  Expected: {v['expected']}")
            print(f"  Actual compliance rate: {v['actual_rate']:.1%}")
            
            # Show decision breakdown
            decisions_str = ", ".join(f"{action}:{count}" for action, count in v['decisions'].items())
            print(f"  Decision breakdown: {decisions_str}")


def save_violations_csv(violations: List[Dict[str, Any]], model_name: str, output_path: str) -> None:
    """Save violations to CSV file."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        headers = ["model", "rule_type", "rule_text", "hand", "expected", "actual_rate", "severity", "decisions"]
        writer.writerow(headers)
        
        for v in violations:
            decisions_str = "; ".join(f"{action}:{count}" for action, count in v['decisions'].items())
            writer.writerow([
                model_name,
                v["rule_type"],
                v["rule_text"],
                v["hand"],
                v["expected"],
                f"{v['actual_rate']:.3f}",
                v["severity"],
                decisions_str
            ])


def main():
    ap = argparse.ArgumentParser(description="Check consistency between stated strategies and actual play")
    ap.add_argument("strategy_dir", help="Directory containing model strategy files (e.g., model_thoughts/)")
    ap.add_argument("baseline_dir", help="Directory containing baseline JSONL files")
    ap.add_argument("--model", help="Focus on specific model (partial name match)")
    ap.add_argument("--violations-only", action="store_true", help="Only show models with violations")
    ap.add_argument("--severity", choices=["low", "medium", "high"], help="Minimum severity to report")
    ap.add_argument("--csv", help="Save violations to CSV file")
    ap.add_argument("--track", choices=["policy", "policy-grid"], default="policy-grid")
    args = ap.parse_args()
    
    strategy_dir = Path(args.strategy_dir)
    baseline_dir = Path(args.baseline_dir)
    
    if not strategy_dir.exists():
        print(f"Strategy directory not found: {strategy_dir}")
        return
    
    if not baseline_dir.exists():
        print(f"Baseline directory not found: {baseline_dir}")
        return
    
    # Discover strategy and baseline files
    strategy_files = discover_strategy_files(strategy_dir)
    baseline_files = discover_files([str(baseline_dir)])
    
    print(f"Found {len(strategy_files)} strategy files and {len(baseline_files)} baseline files")
    
    all_violations = []
    models_checked = 0
    
    # Pre-filter strategy files to only those with matching baselines
    valid_strategy_files = []
    baseline_model_names = {extract_model_name_from_baseline(bf).lower() for bf in baseline_files}
    
    for strategy_file in strategy_files:
        strategy_model = extract_model_name_from_strategy(strategy_file)
        
        # Filter by model if specified
        if args.model and args.model.lower() not in strategy_model.lower():
            continue
            
        # Check if there's a matching baseline with flexible matching
        found_match = False
        for baseline_name in baseline_model_names:
            if is_model_match(strategy_model, baseline_name):
                found_match = True
                break
        
        if found_match:
            valid_strategy_files.append((strategy_file, strategy_model))
    
    if not valid_strategy_files:
        print("No strategy files found with matching baseline data.")
        return
    
    # Process each valid strategy file
    for strategy_file, strategy_model in valid_strategy_files:
        # Find matching baseline file
        matching_baseline = None
        for baseline_file in baseline_files:
            baseline_model = extract_model_name_from_baseline(baseline_file)
            if is_model_match(strategy_model, baseline_model):
                matching_baseline = baseline_file
                break
        
        models_checked += 1
        print(f"\nAnalyzing {strategy_model}...")
        
        # Parse strategy rules
        try:
            content = strategy_file.read_text(encoding="utf-8")
            rules = parse_strategy_rules(content)
        except Exception as e:
            print(f"Error reading strategy file {strategy_file}: {e}")
            continue
        
        # Analyze baseline decisions
        try:
            decisions = analyze_baseline_decisions(matching_baseline, args.track)
        except Exception as e:
            print(f"Error analyzing baseline {matching_baseline}: {e}")
            continue
        
        # Check consistency
        violations = []
        violations.extend(check_split_consistency(rules, decisions))
        violations.extend(check_double_consistency(rules, decisions))
        
        # Filter by severity if specified
        if args.severity:
            severity_order = {"low": 0, "medium": 1, "high": 2}
            min_level = severity_order[args.severity]
            violations = [v for v in violations if severity_order.get(v["severity"], 0) >= min_level]
        
        # Report violations
        if not args.violations_only or violations:
            format_violations_report(violations, strategy_model)
            
            # Add to all violations for CSV export
            for v in violations:
                v["model"] = strategy_model
                all_violations.append(v)
    
    # Summary
    total_violations = len(all_violations)
    print(f"\n# Summary")
    print(f"Strategy files analyzed: {len(valid_strategy_files)}")
    print(f"Models successfully checked: {models_checked}")
    if models_checked != len(valid_strategy_files):
        print(f"Models with errors: {len(valid_strategy_files) - models_checked}")
    print(f"Total violations found: {total_violations}")
    
    if total_violations > 0:
        by_severity = defaultdict(int)
        for v in all_violations:
            by_severity[v["severity"]] += 1
        
        for severity in ["high", "medium", "low"]:
            if by_severity[severity] > 0:
                print(f"  {severity.capitalize()} severity: {by_severity[severity]}")
    
    # Save CSV if requested
    if args.csv and all_violations:
        save_violations_csv(all_violations, "all_models", args.csv)
        print(f"\nSaved violations to {args.csv}")


if __name__ == "__main__":
    main()