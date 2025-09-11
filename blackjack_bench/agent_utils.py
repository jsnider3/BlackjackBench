"""Shared utilities for agent implementations."""

from __future__ import annotations

from typing import Any, Dict, Optional
from .types import Action, Observation


def parse_dealer_upcard(observation: Observation) -> int:
    """Extract dealer upcard value from observation.
    
    Args:
        observation: Blackjack observation containing dealer upcard
        
    Returns:
        Numeric value of dealer upcard (11 for Ace, 10 for face cards)
    """
    # dealer_upcard like '9H' or '10S'; strip one-char suit
    rank = observation.dealer_upcard[:-1]
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def normalize_rank(rank: str) -> str:
    """Normalize card rank to standard form.
    
    Args:
        rank: Card rank string (may include 'T', 't', etc.)
        
    Returns:
        Normalized rank ('10' for ten-value cards, original for others)
    """
    if rank in ("T", "t"):
        return "10"
    if rank in ("J", "Q", "K"):
        return "10"
    return rank


def is_ten_value_pair(card1: str, card2: str) -> bool:
    """Check if two cards form a ten-value pair for splitting logic.
    
    Args:
        card1: First card rank (without suit)
        card2: Second card rank (without suit) 
        
    Returns:
        True if both cards are ten-value (10, J, Q, K)
    """
    def is_ten_value(rank: str) -> bool:
        return normalize_rank(rank) == "10"
    
    return is_ten_value(card1) and is_ten_value(card2)


def validate_agent_parameters(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    prompt_mode: Optional[str] = None,
    reasoning: Optional[str] = None,
) -> Dict[str, str]:
    """Validate and normalize agent parameters.
    
    Args:
        provider: LLM provider name
        model: Model name
        temperature: Temperature value
        prompt_mode: Prompt mode string
        reasoning: Reasoning level string
        
    Returns:
        Dictionary of validation errors (empty if all valid)
        
    Raises:
        ValueError: If any parameter is invalid
    """
    from .constants import VALID_PROMPT_MODES, VALID_REASONING_LEVELS
    
    errors = {}
    
    if prompt_mode is not None and prompt_mode not in VALID_PROMPT_MODES:
        errors["prompt_mode"] = f"Must be one of: {', '.join(VALID_PROMPT_MODES)}"
    
    if reasoning is not None and reasoning not in VALID_REASONING_LEVELS:
        errors["reasoning"] = f"Must be one of: {', '.join(VALID_REASONING_LEVELS)}"
        
    if temperature is not None and (temperature < 0.0 or temperature > 2.0):
        errors["temperature"] = "Must be between 0.0 and 2.0"
    
    if errors:
        error_msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
        raise ValueError(f"Invalid agent parameters: {error_msg}")
    
    return {}


def format_allowed_actions(actions: list[Action]) -> str:
    """Format allowed actions for display in prompts.
    
    Args:
        actions: List of allowed Action enums
        
    Returns:
        Comma-separated string of action names
    """
    return ", ".join(a.name for a in actions)


def extract_ranks_from_cards(cards: list[str]) -> str:
    """Extract ranks from card labels for prompt display.
    
    Args:
        cards: List of card labels (e.g., ['AH', '10S'])
        
    Returns:
        Comma-separated ranks (e.g., 'A,10')
    """
    return ",".join(card[:-1] for card in cards)


class AgentMetrics:
    """Helper class for tracking agent performance metrics."""
    
    def __init__(self):
        self.illegal_count = 0
        self.illegal_attempts: list[Dict[str, Any]] = []
        self.decisions = 0
        self.mistakes = 0
    
    def record_illegal_attempt(self, attempted_action: str, allowed_actions: list[str]) -> None:
        """Record an illegal action attempt."""
        self.illegal_count += 1
        self.illegal_attempts.append({
            "attempted": attempted_action,
            "allowed": allowed_actions,
        })
    
    def record_decision(self, is_mistake: bool) -> None:
        """Record a decision and whether it was a mistake."""
        self.decisions += 1
        if is_mistake:
            self.mistakes += 1
    
    def illegal_rate(self) -> float:
        """Calculate illegal action rate."""
        return (self.illegal_count / self.decisions) if self.decisions > 0 else 0.0
    
    def mistake_rate(self) -> float:
        """Calculate mistake rate."""
        return (self.mistakes / self.decisions) if self.decisions > 0 else 0.0
    
    def reset(self) -> None:
        """Reset all counters."""
        self.illegal_count = 0
        self.illegal_attempts.clear()
        self.decisions = 0
        self.mistakes = 0