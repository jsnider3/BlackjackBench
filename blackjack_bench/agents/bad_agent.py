from __future__ import annotations

from typing import Any

from ..types import Action, Observation


class BadAgent:
    """Intentionally poor: maximize expected loss within legal actions.

    Heuristics (not provably worst, but very bad):
    - If DOUBLE is legal, always DOUBLE (even on 20).
    - Else if SPLIT is legal, split 10s and low pairs; otherwise avoid good splits (never split Aces).
    - Else: Stand on <= 11; Hit on >= 17; for 12–16, Hit vs dealer 2–6 (reverse of basic), Stand vs 7–A.
    - Never surrender (we keep default rules with surrender off).
    """

    def act(self, observation: Observation, info: Any) -> Action:
        acts = observation.allowed_actions
        if Action.DOUBLE in acts:
            return Action.DOUBLE
        if Action.SPLIT in acts:
            # Avoid good splits; prefer bad ones
            r0 = observation.player.cards[0][:-1]
            r1 = observation.player.cards[1][:-1]
            def ten_group(x: str) -> str:
                return "10" if x in ("10", "J", "Q", "K") else x
            r0g, r1g = ten_group(r0), ten_group(r1)
            if r0g == r1g:
                if r0g == "10":
                    return Action.SPLIT
                if r0g in {"2", "3", "4", "6", "7", "9"}:  # often situational; still bad splits
                    return Action.SPLIT
                # Never split Aces or 8s (those are good)
        total = observation.player.total
        if total <= 11:
            return Action.STAND
        if total >= 17:
            return Action.HIT
        # 12–16: reverse of basic tendency
        return Action.HIT if self._dealer_up(observation) in (2, 3, 4, 5, 6) else Action.STAND

    def _dealer_up(self, observation: Observation) -> int:
        r = observation.dealer_upcard[:-1]
        if r in ("J", "Q", "K"):
            return 10
        if r == "A":
            return 11
        return int(r)
