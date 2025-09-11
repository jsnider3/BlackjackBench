from __future__ import annotations

from typing import Any

from ..types import Action, Observation


class GeminiFlashAgent:
    """Agent implementing Gemini 2.5 Flash's conservative blackjack strategy.
    
    Based on Gemini Flash's thoughts emphasizing:
    - Basic strategy foundation focused on mathematical optimization
    - Hard hands: Hit 12-16 if dealer upcard is 7+, stand if dealer 2-6
    - Soft hands: More aggressive play since cannot bust, hit soft 17 or less, stand 19+
    - Pairs: Always split Aces and 8s, never split tens
    - Doubling: Maximize potential payout when high probability of good final hand
    - Conservative approach avoiding "gut feelings" in favor of mathematical decisions
    """

    def act(self, observation: Observation, info: Any) -> Action:
        actions = observation.allowed_actions

        # If split is available, resolve pair strategy first
        if observation.player.can_split and Action.SPLIT in actions:
            pair_action = self._pair_decision(observation)
            if pair_action is not None and pair_action in actions:
                return pair_action

        # Soft totals - more aggressive since cannot bust
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
        """Conservative soft hand strategy - more aggressive since cannot bust."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # Hit on soft 17 or less (mentioned specifically)
        if total <= 17:
            # Double when advantageous against weak dealer cards
            if up in (4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # Soft 18 - context dependent
        if total == 18:
            if up in (2, 7, 8):
                return Action.STAND
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            if up in (9, 10, 11):
                return Action.HIT
            return Action.STAND
        
        # Stand on 19 or higher (mentioned specifically)
        if total >= 19:
            return Action.STAND
        
        return Action.HIT

    def _hard_total_decision(self, obs: Observation) -> Action:
        """Conservative hard total strategy following Gemini's principles."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # Always hit on 11 or less
        if total <= 11:
            # Double on strong hands when advantageous
            if total == 11 and up in (2, 3, 4, 5, 6, 7, 8, 9, 10) and can_double:
                return Action.DOUBLE
            if total == 10 and up in (2, 3, 4, 5, 6, 7, 8, 9) and can_double:
                return Action.DOUBLE
            if total == 9 and up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT

        # Key rule: For 12-16, stand vs dealer 2-6, hit vs 7+
        if 12 <= total <= 16:
            if up in (2, 3, 4, 5, 6):
                # Dealer has higher chance of busting
                return Action.STAND
            else:
                # Dealer upcard 7+ - we need to improve our hand
                return Action.HIT

        # Stand on 17 or higher (conservative approach)
        if total >= 17:
            return Action.STAND

        return Action.HIT

    def _pair_decision(self, obs: Observation) -> Action | None:
        """Conservative pair strategy: always split advantageous pairs, avoid risky splits."""
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
        
        # Always split Aces (mentioned specifically)
        # "Splitting Aces gives me two strong starting hands"
        if pair == "A":
            return Action.SPLIT
        
        # Always split eights (mentioned specifically)  
        # "splitting eights avoids the difficult hand of 16"
        if pair == "8":
            return Action.SPLIT
        
        # Never split tens (mentioned specifically)
        # "a hand of 20 is already very strong"
        if pair == "10":
            return None
        
        # Conservative approach for other pairs - only split when clearly advantageous
        if pair == "9":
            # Don't split vs strong dealer cards (7, 10, A)
            if up in (7, 10, 11):
                return None  # 18 is good, don't risk it
            return Action.SPLIT
        
        if pair == "7":
            # Split against weak/medium dealer cards
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        
        if pair == "6":
            # Split only against weak dealer cards
            if up in (2, 3, 4, 5, 6):
                return Action.SPLIT
            return None
        
        if pair == "5":
            # Never split 5s - treat as 10 hard total
            return None
        
        if pair == "4":
            # Generally avoid splitting 4s (conservative approach)
            return None
        
        if pair in ("2", "3"):
            # Split small pairs against weak dealer cards
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None

        return None