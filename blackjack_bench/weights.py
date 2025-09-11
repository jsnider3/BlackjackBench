"""Grid weight calculations for policy evaluation."""

from __future__ import annotations

from typing import Dict, Tuple

# Type alias for clarity
Cell = Tuple[str, str, str]  # (player_card_1, player_card_2, dealer_upcard)


def grid_weights_infinite_deck() -> Dict[Cell, float]:
    """Calculate natural frequency weights for policy grid under infinite-deck approximation.
    
    Returns:
        Dictionary mapping (player_card1, player_card2, dealer_upcard) to probability weight.
        Weights sum to 1.0 under independence assumption.
    """
    # Ranks with 10-grouping; probabilities under infinite-deck approximation
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    pr = {r: (4/13 if r == "10" else 1/13) for r in ranks}
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
    pd = {d: pr[d] for d in dealer_up}

    weights: Dict[Cell, float] = {}
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:
            # Probability of getting this specific pair of cards
            p_player = (pr[r1] ** 2) if r1 == r2 else (2 * pr[r1] * pr[r2])
            for du in dealer_up:
                weights[(r1, r2, du)] = p_player * pd[du]
    
    return weights