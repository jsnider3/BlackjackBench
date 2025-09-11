#!/usr/bin/env python3
"""
Common utilities for BlackJack analysis tools.

This module provides shared functionality for:
- File discovery and JSONL parsing
- Grid weight calculations
- Rank normalization
- Decision classification
- Output formatting
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional


# Type aliases for clarity
Cell = Tuple[str, str, str]  # (p1, p2, du)
Key = Tuple[str, str, str, int]  # (p1, p2, du, rep)

# Constants
RANK_ORDER = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
FACE_CARDS = {"10", "J", "Q", "K"}
DEALER_UPCARDS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
ACTIONS = ["HIT", "STAND", "DOUBLE", "SPLIT", "SURRENDER"]

# Default configuration values commonly used across tools
DEFAULT_TOP_N = 15
DEFAULT_PRECISION = 6


def norm_rank(rank: str) -> str:
    """Normalize face cards to '10' for consistent handling."""
    return "10" if rank in FACE_CARDS else rank


def grid_weights_infinite_deck() -> Dict[Cell, float]:
    """
    Calculate natural frequency weights for policy-grid cells.
    
    Returns probability weights for each (p1, p2, dealer_upcard) combination
    assuming infinite deck (4/13 for 10s, 1/13 for others).
    """
    ranks = RANK_ORDER
    pr = {r: (4/13 if r == "10" else 1/13) for r in ranks}
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
    pd = {d: pr[d] for d in dealer_up}
    
    weights: Dict[Cell, float] = {}
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:  # combinations with repetition
            p_player = (pr[r1] ** 2) if r1 == r2 else (2 * pr[r1] * pr[r2])
            for du in dealer_up:
                weights[(r1, r2, du)] = p_player * pd[du]
    
    return weights


def discover_files(inputs: List[str]) -> List[Path]:
    """
    Discover JSONL files from various input types.
    
    Args:
        inputs: List of file paths, directory paths, or glob patterns
        
    Returns:
        Deduplicated list of existing JSONL files
    """
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
    """
    Load JSONL events from a file with error handling.
    
    Args:
        path: Path to JSONL file
        
    Yields:
        Parsed JSON events, skipping malformed lines
    """
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def categorize_hand(event: Dict[str, Any]) -> str:
    """
    Categorize a decision event into strategy category.
    
    Args:
        event: JSONL event dictionary
        
    Returns:
        Category string: "pair X/X", "soft N", "hard N", or "unknown"
        
    Note:
        This is a standardized version used across multiple tools.
        For first decisions, it checks for pairs; otherwise categorizes by total and softness.
    """
    obs = event.get("obs") or {}
    player = obs.get("player") or {}
    total = player.get("total")
    is_soft = bool(player.get("is_soft"))
    cell = event.get("cell") or {}
    
    # Normalize card ranks
    p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
    p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
    
    # Check for pairs on first decision
    if event.get("decision_idx") == 0 and p1 and p2 and p1 == p2:
        return f"pair {p1}/{p2}"
    
    # Categorize by hand total
    if isinstance(total, int):
        return f"soft {total}" if is_soft else f"hard {total}"
    
    return "unknown"


def classify_decision(event: dict) -> Tuple[str, Optional[Cell]]:
    """
    Classify a decision event into category and extract starting cell.
    
    Args:
        event: JSONL event dictionary
        
    Returns:
        Tuple of (category_string, start_cell_or_None)
        where category is "pair X/X", "soft N", or "hard N"
        and start_cell is (p1, p2, du) for first decisions only
    """
    obs = event.get("obs") or {}
    player = obs.get("player") or {}
    total = player.get("total")
    is_soft = bool(player.get("is_soft"))
    decision_idx = event.get("decision_idx")
    cell = event.get("cell") or {}
    
    start_cell: Optional[Cell] = None
    
    # Extract start cell for first decisions
    if decision_idx == 0 and cell:
        p1 = norm_rank(str(cell.get("p1"))) if cell.get("p1") else None
        p2 = norm_rank(str(cell.get("p2"))) if cell.get("p2") else None
        du = norm_rank(str(cell.get("du"))) if cell.get("du") else None
        
        if p1 and p2 and du:
            # Sort player cards for consistent lookup
            p1s, p2s = sorted([p1, p2], key=lambda x: RANK_ORDER.index(x))
            start_cell = (p1s, p2s, du)
            
            # Check for pairs
            if p1s == p2s:
                return (f"pair {p1s}/{p2s}", start_cell)
    
    # Classify by total and softness
    if is_soft:
        return (f"soft {total}", start_cell)
    else:
        return (f"hard {total}", start_cell)


def extract_model_name(file_path: Path) -> str:
    """
    Extract a clean model name from a file path.
    
    Args:
        file_path: Path to model file
        
    Returns:
        Clean model name string
    """
    name = file_path.name
    # Try to extract from structured filename
    parts = name.split("_")
    try:
        # Last segment without extension often contains the model
        return parts[-1].rsplit(".", 1)[0]
    except Exception:
        return name.rsplit(".", 1)[0]


def format_table(
    headers: List[str], 
    rows: List[List[str]], 
    right_align: Optional[List[str]] = None
) -> str:
    """
    Format a table with proper column alignment.
    
    Args:
        headers: Column headers
        rows: Data rows (same length as headers)
        right_align: List of header names to right-align
        
    Returns:
        Formatted table string
    """
    if not rows:
        return "(no data)"
    
    right_align = right_align or []
    all_rows = [headers] + rows
    widths = [max(len(str(row[i])) for row in all_rows) for i in range(len(headers))]
    
    # Format header
    header_parts = []
    for i, header in enumerate(headers):
        if header in right_align:
            header_parts.append(header.rjust(widths[i]))
        else:
            header_parts.append(header.ljust(widths[i]))
    
    lines = ["  ".join(header_parts)]
    
    # Format data rows
    for row in rows:
        row_parts = []
        for i, (cell, header) in enumerate(zip(row, headers)):
            if header in right_align:
                row_parts.append(str(cell).rjust(widths[i]))
            else:
                row_parts.append(str(cell).ljust(widths[i]))
        lines.append("  ".join(row_parts))
    
    return "\n".join(lines)


def safe_float_format(value: float, precision: int = DEFAULT_PRECISION) -> str:
    """
    Format float with specified precision, handling edge cases.
    
    Args:
        value: Float value to format
        precision: Number of decimal places (default from DEFAULT_PRECISION)
        
    Returns:
        Formatted string representation of the float
    """
    if value == 0.0:
        return "0." + "0" * precision
    return f"{value:.{precision}f}"


def safe_percentage_format(value: float, precision: int = 2) -> str:
    """
    Format float as percentage with specified precision.
    
    Args:
        value: Float value (0.0-1.0 range expected)
        precision: Number of decimal places for percentage
        
    Returns:
        Formatted percentage string (e.g., "45.67%")
    """
    return f"{value * 100:.{precision}f}%"