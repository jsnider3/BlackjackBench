from __future__ import annotations

import random
from typing import Any

from ..types import Action, Observation


class RandomAgent:
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def act(self, observation: Observation, info: Any) -> Action:
        return self.rng.choice(observation.allowed_actions)

