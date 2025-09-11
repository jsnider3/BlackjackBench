from __future__ import annotations

from typing import Any

from ..types import Action, Observation


class GemmaAgent:
    """Agent implementing Gemma's corrected strict basic strategy.
    
    Based on Gemma's thoughts but correcting obvious errors:
    - Claims "strict basic strategy" approach with mechanical consistency
    - Hard hands: Hit on 11 or less, stand on 17+, hit 12-16 vs dealer 7+
    - Soft hands: Always hit soft 17 or lower (correcting the impossible "double soft 19-21")
    - Pairs: Always split A/8, never split 10s/5s, split 2s/3s/6s vs 2-6
    - Never take insurance
    - No surrender strategy mentioned
    - Focus on statistically optimal plays with highest expected value
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
        """Extract dealer upcard value."""
        r = observation.dealer_upcard[:-1]
        if r in ("J", "Q", "K"):
            return 10
        if r == "A":
            return 11
        return int(r)

    def _soft_total_decision(self, obs: Observation) -> Action:
        """Corrected soft hand strategy - always hit soft 17 or lower."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # Always hit on Soft 17 or lower (Gemma's rule, corrected)
        if total <= 17:
            # Add doubling for favorable situations
            if total in (15, 16) and up in (4, 5, 6) and can_double:
                return Action.DOUBLE
            if total in (13, 14) and up in (5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # Soft 18 - basic strategy
        if total == 18:
            if up in (2, 7, 8):
                return Action.STAND
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            if up in (9, 10, 11):
                return Action.HIT
            return Action.STAND
        
        # Soft 19+ - stand (impossible to double as Gemma incorrectly stated)
        if total >= 19:
            return Action.STAND
        
        return Action.HIT

    def _hard_total_decision(self, obs: Observation) -> Action:
        """Strict basic strategy for hard hands."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # Hit on 11 or less (Gemma's rule)
        if total <= 11:
            # Add doubling for optimal situations
            if total == 11 and up in (2, 3, 4, 5, 6, 7, 8, 9, 10) and can_double:
                return Action.DOUBLE
            if total == 10 and up in (2, 3, 4, 5, 6, 7, 8, 9) and can_double:
                return Action.DOUBLE
            if total == 9 and up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT

        # Hit on 12-16 against dealer's 7 or higher (Gemma's rule)
        # Stand on 17 or higher (Gemma's rule)
        if 12 <= total <= 16:
            if up in (7, 8, 9, 10, 11):
                return Action.HIT
            else:  # Dealer 2-6
                return Action.STAND

        # Stand on 17 or higher
        if total >= 17:
            return Action.STAND

        return Action.HIT

    def _pair_decision(self, obs: Observation) -> Action | None:
        """Strict pair strategy following Gemma's rules."""
        r0 = obs.player.cards[0][:-1]
        r1 = obs.player.cards[1][:-1]
        up = self._dealer_up(obs)

        def ten_group(x: str) -> str:
            return "10" if x in ("10", "J", "Q", "K") else x

        r0 = ten_group(r0)
        r1 = ten_group(r1)
        if r0 != r1:
            return None

        pair = r0
        
        # Always split Aces and 8s (Gemma's rule)
        if pair == "A":
            return Action.SPLIT
        if pair == "8":
            return Action.SPLIT
        
        # Never split 10s or 5s (Gemma's rule)
        if pair == "10":
            return None
        if pair == "5":
            return None
        
        # Split 2s, 3s, and 6s against dealer's 2-6 (Gemma's rule)
        if pair in ("2", "3", "6"):
            if up in (2, 3, 4, 5, 6):
                return Action.SPLIT
            return None
        
        # For other pairs, use conservative basic strategy approach
        if pair == "7":
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        
        if pair == "9":
            if up in (2, 3, 4, 5, 6, 8, 9):
                return Action.SPLIT
            return None
        
        if pair == "4":
            # Generally don't split 4s (conservative)
            return None

        return None