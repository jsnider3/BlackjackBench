from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rules:
    num_decks: int = 6
    hit_soft_17: bool = True  # H17; False => S17
    blackjack_payout: float = 1.5  # 3:2
    double_allowed: bool = True
    double_after_split: bool = True
    max_splits: int = 3  # total hands after splits
    split_aces_one_card: bool = True
    resplit_aces: bool = False
    surrender_allowed: bool = False  # off by default

