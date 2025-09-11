from __future__ import annotations

from typing import Any, Optional

from ..types import Action, Observation


class ClaudeSonnetAgentExplicitError(Exception):
    """Raised when agent has no explicit rule for the given situation."""
    pass


class ClaudeSonnetAgent:
    """Agent implementing ONLY the explicitly stated rules from Claude Sonnet 4's thoughts.
    
    Explicit rules mentioned:
    1. "always split aces and eights"
    2. "never split tens or fives" 
    3. "double down on 11 against dealer's 2-10"
    4. "hit on hard totals under 12"
    5. "stand on hard 17 or higher"
    6. "consider surrender against dealer's strong upcards when holding terrible hands like hard 16 versus a 10"
    
    Vague statements NOT implemented:
    - "be more aggressive against dealer's weak upcards (2-6)" - no specifics given
    - "be more liberal with hitting and doubling" for soft hands - no specifics given
    """

    def act(self, observation: Observation, info: Any) -> Action:
        actions = observation.allowed_actions

        # Check explicit pair rules first
        if observation.player.can_split and Action.SPLIT in actions:
            pair_action = self._pair_decision(observation)
            if pair_action is not None:
                return pair_action

        # Check explicit surrender rule
        if Action.SURRENDER in actions:
            surrender_action = self._surrender_decision(observation)
            if surrender_action is not None:
                return surrender_action

        # Check explicit hard total rules
        if not observation.player.is_soft:
            hard_action = self._hard_total_decision(observation)
            if hard_action is not None:
                return hard_action

        # No explicit rule found for this situation
        raise ClaudeSonnetAgentExplicitError(
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
        """Explicit rule: consider surrender for hard 16 vs 10."""
        if not obs.player.is_soft and obs.player.total == 16:
            up = self._dealer_up(obs)
            if up == 10:  # Only mentioned "hard 16 versus a 10"
                return Action.SURRENDER
        return None

    def _hard_total_decision(self, obs: Observation) -> Optional[Action]:
        """Explicit hard total rules only."""
        total = obs.player.total
        up = self._dealer_up(obs)
        can_double = obs.player.can_double

        # Explicit rule: "hit on hard totals under 12"
        if total < 12:
            # Explicit rule: "double down on 11 against dealer's 2-10"
            if total == 11 and up in (2, 3, 4, 5, 6, 7, 8, 9, 10) and can_double:
                return Action.DOUBLE
            return Action.HIT

        # Explicit rule: "stand on hard 17 or higher"
        if total >= 17:
            return Action.STAND

        # No explicit rule for 12-16 (vague "more aggressive against weak upcards" doesn't specify)
        return None

    def _pair_decision(self, obs: Observation) -> Optional[Action]:
        """Explicit pair rules only."""
        r0 = obs.player.cards[0][:-1]
        r1 = obs.player.cards[1][:-1]

        def ten_group(x: str) -> str:
            return "10" if x in ("10", "J", "Q", "K") else x

        r0 = ten_group(r0)
        r1 = ten_group(r1)
        if r0 != r1:
            return None

        pair = r0
        
        # Explicit rule: "always split aces and eights"
        if pair == "A":
            return Action.SPLIT
        if pair == "8":
            return Action.SPLIT
            
        # Explicit rule: "never split tens or fives"
        if pair == "10":
            return None  # Don't split
        if pair == "5":
            return None  # Don't split

        # No other pair rules explicitly stated
        return None