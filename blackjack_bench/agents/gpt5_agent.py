from __future__ import annotations

from typing import Any, Optional

from ..types import Action, Observation


class GPT5AgentExplicitError(Exception):
    """Raised when agent has no explicit rule for the given situation."""
    pass


class GPT5Agent:
    """Agent implementing ONLY the explicitly stated rules from GPT-5's thoughts.
    
    GPT-5 provided very detailed explicit rules:
    
    Hard totals:
    - 8 or less: hit
    - 9: double vs 3–6, else hit
    - 10: double vs 2–9, else hit
    - 11: double vs 2–A
    - 12: stand vs 4–6, else hit
    - 13–16: stand vs 2–6, else hit
    - 17+: stand
    
    Soft totals (A counted as 11):
    - A,2–A,3: double vs 5–6, else hit
    - A,4–A,5: double vs 4–6, else hit
    - A,6: double vs 3–6, else hit
    - A,7: double vs 3–6; stand vs 2,7,8; hit vs 9–A
    - A,8/A,9: stand
    
    Pairs:
    - Always split A,A and 8,8
    - Never split 5,5 or 10,10
    - 2,2 and 3,3: split vs 2–7
    - 4,4: split vs 5–6 (only if DAS), else hit
    - 6,6: split vs 2–6
    - 7,7: split vs 2–7
    - 9,9: split vs 2–6 and 8–9; stand vs 7,10,A
    
    Surrender:
    - 16 (not 8,8) vs 9,10,A
    - 15 vs 10
    """

    def act(self, observation: Observation, info: Any) -> Action:
        actions = observation.allowed_actions

        # Check explicit surrender rules first
        if Action.SURRENDER in actions:
            surrender_action = self._surrender_decision(observation)
            if surrender_action is not None:
                return surrender_action

        # Check explicit pair rules
        if observation.player.can_split and Action.SPLIT in actions:
            pair_action = self._pair_decision(observation)
            if pair_action is not None:
                return pair_action

        # Check explicit soft total rules
        if observation.player.is_soft:
            soft_action = self._soft_total_decision(observation)
            if soft_action is not None:
                return soft_action

        # Check explicit hard total rules
        if not observation.player.is_soft:
            hard_action = self._hard_total_decision(observation)
            if hard_action is not None:
                return hard_action

        # No explicit rule found
        raise GPT5AgentExplicitError(
            f"No explicit rule for: {self._describe_situation(observation)}"
        )

    def _dealer_up(self, observation: Observation) -> int:
        """Extract dealer upcard value."""
        r = observation.dealer_upcard[:-1]
        if r in ("J", "Q", "K"):
            return 10
        if r == "A":
            return 11
        return int(r)

    def _describe_situation(self, obs: Observation) -> str:
        """Describe the current situation for error messages."""
        if obs.player.can_split:
            return f"pair {obs.player.cards[0][:-1]},{obs.player.cards[1][:-1]} vs {obs.dealer_upcard[:-1]}"
        elif obs.player.is_soft:
            return f"soft {obs.player.total} vs {obs.dealer_upcard[:-1]}"
        else:
            return f"hard {obs.player.total} vs {obs.dealer_upcard[:-1]}"

    def _surrender_decision(self, obs: Observation) -> Optional[Action]:
        """Explicit surrender rules: 16 (not 8,8) vs 9,10,A; 15 vs 10."""
        if obs.player.is_soft:
            return None
        
        up = self._dealer_up(obs)
        total = obs.player.total
        
        # 16 vs 9,10,A (but not 8,8)
        if total == 16:
            # Check if it's 8,8 pair
            if (len(obs.player.cards) == 2 and 
                obs.player.cards[0][:-1] == "8" and obs.player.cards[1][:-1] == "8"):
                return None  # Don't surrender 8,8
            if up in (9, 10, 11):
                return Action.SURRENDER
        
        # 15 vs 10
        if total == 15 and up == 10:
            return Action.SURRENDER
            
        return None

    def _soft_total_decision(self, obs: Observation) -> Optional[Action]:
        """Explicit soft total rules."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # A,2–A,3 (soft 13-14): double vs 5–6, else hit
        if total in (13, 14):
            if up in (5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # A,4–A,5 (soft 15-16): double vs 4–6, else hit
        if total in (15, 16):
            if up in (4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # A,6 (soft 17): double vs 3–6, else hit
        if total == 17:
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # A,7 (soft 18): double vs 3–6; stand vs 2,7,8; hit vs 9–A
        if total == 18:
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            if up in (2, 7, 8):
                return Action.STAND
            if up in (9, 10, 11):
                return Action.HIT
            return Action.STAND
        
        # A,8/A,9 (soft 19-20): stand
        if total >= 19:
            return Action.STAND
        
        # No other soft hand rules specified
        return None

    def _hard_total_decision(self, obs: Observation) -> Optional[Action]:
        """Explicit hard total rules."""
        up = self._dealer_up(obs)
        total = obs.player.total
        can_double = obs.player.can_double

        # 8 or less: hit
        if total <= 8:
            return Action.HIT
        
        # 9: double vs 3–6, else hit
        if total == 9:
            if up in (3, 4, 5, 6) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # 10: double vs 2–9, else hit
        if total == 10:
            if up in (2, 3, 4, 5, 6, 7, 8, 9) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # 11: double vs 2–A
        if total == 11:
            if up in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11) and can_double:
                return Action.DOUBLE
            return Action.HIT
        
        # 12: stand vs 4–6, else hit
        if total == 12:
            if up in (4, 5, 6):
                return Action.STAND
            return Action.HIT
        
        # 13–16: stand vs 2–6, else hit
        if 13 <= total <= 16:
            if up in (2, 3, 4, 5, 6):
                return Action.STAND
            return Action.HIT
        
        # 17+: stand
        if total >= 17:
            return Action.STAND
        
        # Should not reach here given the rules above
        return None

    def _pair_decision(self, obs: Observation) -> Optional[Action]:
        """Explicit pair rules."""
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
        
        # Always split A,A and 8,8
        if pair == "A":
            return Action.SPLIT
        if pair == "8":
            return Action.SPLIT
        
        # Never split 5,5 or 10,10
        if pair == "5":
            return None  # Don't split
        if pair == "10":
            return None  # Don't split
        
        # 2,2 and 3,3: split vs 2–7
        if pair in ("2", "3"):
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        
        # 4,4: split vs 5–6 (only if DAS), else hit
        if pair == "4":
            if up in (5, 6):
                return Action.SPLIT
            return None  # "else hit" - let it fall through to hard total decision
        
        # 6,6: split vs 2–6
        if pair == "6":
            if up in (2, 3, 4, 5, 6):
                return Action.SPLIT
            return None
        
        # 7,7: split vs 2–7
        if pair == "7":
            if up in (2, 3, 4, 5, 6, 7):
                return Action.SPLIT
            return None
        
        # 9,9: split vs 2–6 and 8–9; stand vs 7,10,A
        if pair == "9":
            if up in (2, 3, 4, 5, 6, 8, 9):
                return Action.SPLIT
            if up in (7, 10, 11):
                return None  # "stand" - let it fall through to hard total (which will stand on 18)
            return None

        # No rule for other pairs
        return None