from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple


class Action(Enum):
    HIT = auto()
    STAND = auto()
    DOUBLE = auto()
    SPLIT = auto()
    SURRENDER = auto()


@dataclass
class HandView:
    cards: List[str]
    total: int
    is_soft: bool
    can_split: bool
    can_double: bool


@dataclass
class Observation:
    player: HandView
    dealer_upcard: str
    hand_index: int
    num_hands: int
    allowed_actions: List[Action]
    running_count: Optional[int] = None
    true_count: Optional[float] = None


Result = Tuple[bool, int]

