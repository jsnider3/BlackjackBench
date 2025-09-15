from __future__ import annotations

from typing import Any, Dict

from ..types import Action, Observation


class BasicStrategyAgent:
    """Six-deck, H17, DAS basic strategy.

    Source: https://www.blackjackapprenticeship.com/wp-content/uploads/2024/09/H17-Basic-Strategy.pdf

    Notes:
    - Uses common chart approximations for 6D H17 with DAS.
    - Treats 10,J,Q,K as 10 for pair logic.
    - No surrender.
    """

    def act(self, observation: Observation, info: Any) -> Action:
        actions = observation.allowed_actions

        # If split is available, resolve pair strategy first
        if observation.player.can_split and Action.SPLIT in actions:
            pair_action = self._pair_decision(observation)
            if pair_action is not None and pair_action in actions:
                return pair_action

        # Soft totals
        if observation.player.is_soft:
            return self._soft_total_decision(observation)

        # Hard totals
        return self._hard_total_decision(observation)

    def _dealer_up(self, observation: Observation) -> int:
        # dealer_upcard like '9H' or '10S'; strip one-char suit
        r = observation.dealer_upcard[:-1]
        if r in ("J", "Q", "K"):
            return 10
        if r == "A":
            return 11
        return int(r)

    def _soft_total_decision(self, obs: Observation) -> Action:
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double
        # Chart for soft totals (A,2=13 ... A,9=20); 6D H17 DAS
        if total in (13, 14):  # A,2 / A,3
            if up in (5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        if total in (15, 16):  # A,4 / A,5
            if up in (4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        if total == 17:  # A,6
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        if total == 18:  # A,7
            if up in (2, 7, 8):
                return Action.STAND
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            if up in (9, 10, 11):
                return Action.HIT
            return Action.STAND
        if total == 19:  # A,8
            if up == 6 and can_double:
                return Action.DOUBLE
            return Action.STAND
        # A,9 or better (20+): stand
        return Action.STAND

    def _hard_total_decision(self, obs: Observation) -> Action:
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        if total <= 8:
            return Action.HIT
        if total == 9:
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        if total == 10:
            if up in (2, 3, 4, 5, 6, 7, 8, 9) and can_double:
                return Action.DOUBLE
            return Action.HIT
        if total == 11:
            if up in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11) and can_double:
                return Action.DOUBLE
            return Action.HIT
        if total == 12:
            if up in (4, 5, 6):
                return Action.STAND
            return Action.HIT
        if 13 <= total <= 16:
            if up in (2, 3, 4, 5, 6):
                return Action.STAND
            return Action.HIT
        return Action.STAND

    def _pair_decision(self, obs: Observation) -> Action | None:
        # Determine pair rank
        r0 = obs.player.cards[0][:-1]
        r1 = obs.player.cards[1][:-1]
        up = self._dealer_up(obs)

        def ten_group(x: str) -> str:
            return "10" if x in ("10", "J", "Q", "K") else x

        r0 = ten_group(r0)
        r1 = ten_group(r1)
        if r0 != r1:
            return None

        # Pair strategy (6D H17 DAS approx)
        pair = r0
        if pair == "A":
            return Action.SPLIT
        if pair == "8":
            return Action.SPLIT
        if pair == "10":
            return None  # never split tens
        if pair == "9":
            if up in (7, 10, 11):
                return Action.STAND
            return Action.SPLIT
        if pair == "7":
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        if pair == "6":
            if up in (2, 3, 4, 5, 6):
                return Action.SPLIT
            return None
        if pair == "5":
            # treat as 10 hard total (double vs 2-9)
            return None
        if pair == "4":
            if up in (5, 6):
                return Action.SPLIT
            return None
        if pair in ("2", "3"):
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        return None
