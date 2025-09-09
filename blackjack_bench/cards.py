from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional


RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]  # suits are not functionally relevant but keep for logs


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def label(self) -> str:
        return f"{self.rank}{self.suit}"


def card_value(rank: str) -> int:
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K", "10"):
        return 10
    return int(rank)


def hand_totals(cards: List[Card]) -> (int, bool):
    total = 0
    aces = 0
    for c in cards:
        if c.rank == "A":
            aces += 1
        total += card_value(c.rank)
    # downgrade aces from 11 to 1 as needed
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    # soft if at least one ace remains valued as 11
    is_soft = aces > 0
    return total, is_soft


class Shoe:
    def __init__(self, num_decks: int = 6, seed: Optional[int] = None):
        self.num_decks = num_decks
        self.rng = random.Random(seed)
        self._cards: List[Card] = []
        self._build()

    def _build(self):
        self._cards = [Card(rank, suit) for _ in range(self.num_decks) for suit in SUITS for rank in RANKS]
        self.rng.shuffle(self._cards)

    def draw(self) -> Card:
        if not self._cards:
            self._build()
        return self._cards.pop()

    def remaining(self) -> int:
        return len(self._cards)
