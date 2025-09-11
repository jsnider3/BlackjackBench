from __future__ import annotations

from typing import Any

from ..types import Action, Observation


class SonomaSkyAgent:
    """Agent implementing Sonoma Sky Alpha's comprehensive blackjack strategy.
    
    Based on Sonoma Sky's very detailed basic strategy description:
    - Hard hands: 8 or less hit, 9 double vs 3-6 else hit, 10 double vs 2-9 else hit,
      11 double vs 2-10 hit vs ace, 12 hit vs 2-3 stand vs 4-6 hit vs 7-ace,
      13-16 stand vs 2-6 hit otherwise, 17+ always stand
    - Soft hands: Soft 13-14 double vs 5-6 else hit, soft 15-16 double vs 4-6 else hit,
      soft 17 double vs 3-6 else hit, soft 18 complex rules, soft 19+ stand
    - Pairs: Always split A/8, split 2s/3s vs 2-7, split 6s/7s appropriately,
      split 9s vs 2-6/8-9, never split 4s/5s/10s
    - Focus on basic strategy derived from computer simulations
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
        """Sonoma Sky's detailed soft hand strategy."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # Soft 13-14 (A,2-A,3): double vs 5-6, else hit
        if total in (13, 14):
            if up in (5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # Soft 15-16 (A,4-A,5): double vs 4-6, else hit
        if total in (15, 16):
            if up in (4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # Soft 17 (A,6): double vs 3-6, else hit
        if total == 17:
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # Soft 18 (A,7): stand vs 2-6/8, double vs 3-6, hit vs 7/9-ace
        if total == 18:
            if up in (2, 8):
                return Action.STAND
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            if up in (7, 9, 10, 11):
                return Action.HIT
            return Action.STAND
        
        # Soft 19+ (A,8+): stand
        if total >= 19:
            return Action.STAND
        
        return Action.HIT

    def _hard_total_decision(self, obs: Observation) -> Action:
        """Sonoma Sky's detailed hard total strategy."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # 8 or less: always hit
        if total <= 8:
            return Action.HIT
        
        # 9: double if dealer shows 3-6, else hit
        if total == 9:
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # 10: double on dealer 2-9, else hit
        if total == 10:
            if up in (2, 3, 4, 5, 6, 7, 8, 9) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # 11: double on 2-10, hit on ace
        if total == 11:
            if up in (2, 3, 4, 5, 6, 7, 8, 9, 10) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # 12: hit on dealer 2 or 3, stand on 4-6, hit on 7-ace
        if total == 12:
            if up in (2, 3):
                return Action.HIT
            if up in (4, 5, 6):
                return Action.STAND
            if up in (7, 8, 9, 10, 11):
                return Action.HIT
            return Action.HIT
        
        # 13-16: stand on dealer 2-6, hit otherwise
        if 13 <= total <= 16:
            if up in (2, 3, 4, 5, 6):
                return Action.STAND
            return Action.HIT
        
        # 17+: always stand
        if total >= 17:
            return Action.STAND

        return Action.HIT

    def _pair_decision(self, obs: Observation) -> Action | None:
        """Sonoma Sky's detailed pair strategy."""
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
        
        # Always split aces and 8s
        if pair == "A":
            return Action.SPLIT
        if pair == "8":
            return Action.SPLIT
        
        # Never split 4s, 5s, or 10s
        if pair == "4":
            return None
        if pair == "5":
            return None
        if pair == "10":
            return None
        
        # Split 2s and 3s against dealer 2-7
        if pair in ("2", "3"):
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        
        # Split 6s against 2-6 (mentioned as "6s/7s on 2-7, 7s also on 2")
        if pair == "6":
            if up in (2, 3, 4, 5, 6):
                return Action.SPLIT
            return None
        
        # Split 7s against 2-7
        if pair == "7":
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        
        # Split 9s against 2-6 and 8-9 (avoid 7, 10, A)
        if pair == "9":
            if up in (2, 3, 4, 5, 6, 8, 9):
                return Action.SPLIT
            return None

        return None