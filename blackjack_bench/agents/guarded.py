from __future__ import annotations

from typing import Any, List

from ..types import Action, Observation
from .bad_agent import BadAgent


class GuardedAgent:
    """Wraps an agent to enforce legal actions.

    - If the inner agent returns an illegal action, increments `illegal_count`,
      logs the violation in `illegal_log`, and falls back to a BadAgent over
      the current legal actions.
    - Exposes `illegal_count` and `illegal_rate(decisions)` for reporting.
    - Provides `reset_illegals()` to clear counters.
    """

    def __init__(self, agent: Any):
        self.agent = agent
        self.fallback = BadAgent()
        self.illegal_count = 0
        self.illegal_log: List[dict] = []

    def reset_illegals(self) -> None:
        self.illegal_count = 0
        self.illegal_log.clear()

    def illegal_rate(self, decisions: int) -> float:
        return (self.illegal_count / decisions) if decisions else 0.0

    def act(self, observation: Observation, info: Any) -> Action:
        # Ensure info is a dict we can enrich
        if not isinstance(info, dict):
            info = {}
        a = self.agent.act(observation, info)
        if a not in observation.allowed_actions:
            self.illegal_count += 1
            self.illegal_log.append({
                "attempted": getattr(a, "name", str(a)),
                "allowed": [x.name for x in observation.allowed_actions],
            })
            info["illegal_attempt"] = getattr(a, "name", str(a))
            fb = self.fallback.act(observation, info)
            info["fallback_action"] = fb.name
            return fb
        return a
