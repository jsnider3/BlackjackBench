#!/usr/bin/env python3
"""
Tool to validate blackjack_bench JSONL log files.

Checks:
1. Valid JSON structure
2. Required fields presence
3. Data type validation
4. Logical consistency
5. Completeness of runs
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict, Counter
from dataclasses import dataclass


@dataclass
class ValidationResult:
    total_lines: int
    valid_lines: int
    errors: List[str]
    warnings: List[str]
    summary: Dict[str, Any]


class JSONLValidator:
    def __init__(self):
        self.required_fields = {
            "track", "cell", "rep", "decision_idx", "obs", 
            "agent_action", "baseline_action", "mistake", "meta", "final"
        }
        
        self.cell_required_fields = {"p1", "p2", "du"}
        self.obs_required_fields = {"player", "dealer_upcard", "hand_index", "num_hands", "allowed_actions"}
        self.player_required_fields = {"cards", "total", "is_soft", "can_split", "can_double"}
        self.final_required_fields = {"reward", "dealer", "hands", "bets", "outcomes", "result"}
        
    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate a JSONL file."""
        errors = []
        warnings = []
        valid_lines = 0
        total_lines = 0
        
        cells_seen = set()
        decisions_per_cell = defaultdict(list)
        action_counts = Counter()
        mistake_counts = Counter()
        tracks = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    total_lines += 1
                    line = line.strip()
                    
                    if not line:
                        warnings.append(f"Line {line_num}: Empty line")
                        continue
                    
                    try:
                        entry = json.loads(line)
                        line_errors = self.validate_entry(entry, line_num)
                        errors.extend(line_errors)
                        
                        if not line_errors:  # Only count as valid if no errors
                            valid_lines += 1
                            
                            # Collect statistics
                            if "track" in entry:
                                tracks.add(entry["track"])
                            if "cell" in entry and isinstance(entry["cell"], dict):
                                cell_key = (entry["cell"].get("p1"), entry["cell"].get("p2"), entry["cell"].get("du"))
                                cells_seen.add(cell_key)
                                rep = entry.get("rep", 0)
                                decisions_per_cell[cell_key].append((rep, entry.get("decision_idx", 0)))
                            if "agent_action" in entry:
                                action_counts[entry["agent_action"]] += 1
                            if "mistake" in entry:
                                mistake_counts[entry["mistake"]] += 1
                    
                    except json.JSONDecodeError as e:
                        errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    except Exception as e:
                        errors.append(f"Line {line_num}: Unexpected error - {e}")
        
        except FileNotFoundError:
            errors.append(f"File not found: {file_path}")
        except Exception as e:
            errors.append(f"Error reading file: {e}")
        
        # Generate summary statistics
        summary = {
            "tracks": list(tracks),
            "unique_cells": len(cells_seen),
            "total_decisions": valid_lines,
            "action_distribution": dict(action_counts),
            "mistake_rate": mistake_counts.get(True, 0) / valid_lines if valid_lines > 0 else 0,
            "avg_decisions_per_cell": valid_lines / len(cells_seen) if cells_seen else 0,
        }
        
        # Check for completeness
        if "policy-grid" in tracks:
            expected_cells = self.calculate_expected_cells()
            missing_cells = expected_cells - cells_seen
            if missing_cells:
                warnings.append(f"Missing {len(missing_cells)} expected cells for policy-grid")
                if len(missing_cells) <= 10:  # Show a few examples
                    examples = list(missing_cells)[:5]
                    warnings.append(f"Example missing cells: {examples}")
        
        return ValidationResult(
            total_lines=total_lines,
            valid_lines=valid_lines,
            errors=errors,
            warnings=warnings,
            summary=summary
        )
    
    def calculate_expected_cells(self) -> Set[tuple]:
        """Calculate expected (p1, p2, du) combinations for policy-grid."""
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
        dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
        
        expected = set()
        for i, r1 in enumerate(ranks):
            for r2 in ranks[i:]:  # Only combinations, not permutations
                for du in dealer_up:
                    expected.add((r1, r2, du))
        return expected
    
    def validate_entry(self, entry: Dict[str, Any], line_num: int) -> List[str]:
        """Validate a single JSONL entry."""
        errors = []
        
        # Check if this is a "no_decision" entry (different validation rules)
        is_no_decision = entry.get("no_decision", False)
        
        if is_no_decision:
            # For no_decision entries, only require basic fields
            required_no_decision_fields = {"track", "cell", "rep", "decision_idx", "no_decision", "final"}
            missing_fields = required_no_decision_fields - set(entry.keys())
            if missing_fields:
                errors.append(f"Line {line_num}: Missing required no_decision fields: {missing_fields}")
            
            # decision_idx should be null for no_decision entries
            if "decision_idx" in entry and entry["decision_idx"] is not None:
                errors.append(f"Line {line_num}: decision_idx should be null for no_decision entries")
        else:
            # Check required top-level fields for normal entries
            missing_fields = self.required_fields - set(entry.keys())
            if missing_fields:
                errors.append(f"Line {line_num}: Missing required fields: {missing_fields}")
        
        # Validate track
        if "track" in entry:
            if entry["track"] not in ["policy", "policy-grid"]:
                errors.append(f"Line {line_num}: Invalid track '{entry['track']}'")
        
        # Validate cell structure for policy-grid
        if entry.get("track") == "policy-grid" and "cell" in entry:
            cell = entry["cell"]
            if not isinstance(cell, dict):
                errors.append(f"Line {line_num}: cell must be an object")
            else:
                missing_cell_fields = self.cell_required_fields - set(cell.keys())
                if missing_cell_fields:
                    errors.append(f"Line {line_num}: Missing cell fields: {missing_cell_fields}")
        
        # Validate observation structure
        if "obs" in entry:
            obs = entry["obs"]
            if not isinstance(obs, dict):
                errors.append(f"Line {line_num}: obs must be an object")
            else:
                missing_obs_fields = self.obs_required_fields - set(obs.keys())
                if missing_obs_fields:
                    errors.append(f"Line {line_num}: Missing obs fields: {missing_obs_fields}")
                
                # Validate player structure
                if "player" in obs:
                    player = obs["player"]
                    if not isinstance(player, dict):
                        errors.append(f"Line {line_num}: obs.player must be an object")
                    else:
                        missing_player_fields = self.player_required_fields - set(player.keys())
                        if missing_player_fields:
                            errors.append(f"Line {line_num}: Missing player fields: {missing_player_fields}")
                        
                        # Validate data types
                        if "total" in player and not isinstance(player["total"], int):
                            errors.append(f"Line {line_num}: player.total must be integer")
                        if "is_soft" in player and not isinstance(player["is_soft"], bool):
                            errors.append(f"Line {line_num}: player.is_soft must be boolean")
                        if "cards" in player and not isinstance(player["cards"], list):
                            errors.append(f"Line {line_num}: player.cards must be array")
        
        # Validate final structure
        if "final" in entry:
            final = entry["final"]
            if not isinstance(final, dict):
                errors.append(f"Line {line_num}: final must be an object")
            else:
                missing_final_fields = self.final_required_fields - set(final.keys())
                if missing_final_fields:
                    errors.append(f"Line {line_num}: Missing final fields: {missing_final_fields}")
        
        # Validate data types
        if "mistake" in entry and not isinstance(entry["mistake"], bool):
            errors.append(f"Line {line_num}: mistake must be boolean")
        
        if "rep" in entry and not isinstance(entry["rep"], int):
            errors.append(f"Line {line_num}: rep must be integer")
        
        # decision_idx can be int or null (for no_decision entries)
        if "decision_idx" in entry:
            decision_idx = entry["decision_idx"]
            if decision_idx is not None and not isinstance(decision_idx, int):
                errors.append(f"Line {line_num}: decision_idx must be integer or null")
        
        return errors
    
    def print_report(self, result: ValidationResult, file_path: str):
        """Print a validation report."""
        print(f"JSONL VALIDATION REPORT")
        print(f"File: {file_path}")
        print("=" * 80)
        
        print(f"\nFILE STRUCTURE:")
        print(f"Total lines: {result.total_lines}")
        print(f"Valid lines: {result.valid_lines}")
        print(f"Success rate: {result.valid_lines/result.total_lines*100:.1f}%")
        
        if result.errors:
            print(f"\nERRORS ({len(result.errors)}):")
            for error in result.errors[:20]:  # Limit to first 20
                print(f"  ❌ {error}")
            if len(result.errors) > 20:
                print(f"  ... and {len(result.errors) - 20} more errors")
        
        if result.warnings:
            print(f"\nWARNINGS ({len(result.warnings)}):")
            for warning in result.warnings[:10]:  # Limit to first 10
                print(f"  ⚠️  {warning}")
            if len(result.warnings) > 10:
                print(f"  ... and {len(result.warnings) - 10} more warnings")
        
        print(f"\nCONTENT SUMMARY:")
        summary = result.summary
        print(f"Tracks: {summary['tracks']}")
        print(f"Unique cells: {summary['unique_cells']}")
        print(f"Total decisions: {summary['total_decisions']}")
        print(f"Mistake rate: {summary['mistake_rate']*100:.1f}%")
        print(f"Avg decisions per cell: {summary['avg_decisions_per_cell']:.1f}")
        
        if summary['action_distribution']:
            print(f"\nACTION DISTRIBUTION:")
            for action, count in sorted(summary['action_distribution'].items()):
                pct = count / summary['total_decisions'] * 100
                print(f"  {action}: {count} ({pct:.1f}%)")
        
        # Overall assessment
        print(f"\nOVERALL ASSESSMENT:")
        if not result.errors:
            print("✅ File is valid!")
        else:
            print(f"❌ File has {len(result.errors)} errors that need to be fixed")
        
        if result.warnings:
            print(f"⚠️  File has {len(result.warnings)} warnings to review")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate blackjack_bench JSONL log files")
    parser.add_argument("file_path", help="Path to JSONL file to validate")
    args = parser.parse_args()
    
    validator = JSONLValidator()
    result = validator.validate_file(args.file_path)
    validator.print_report(result, args.file_path)
    
    # Exit with error code if validation failed
    if result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()