#!/usr/bin/env python3
"""
Quick test to demonstrate the coverage difference between the rewritten agents.
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from blackjack_bench.agents.claude_sonnet_agent import ClaudeSonnetAgent, ClaudeSonnetAgentExplicitError
from blackjack_bench.agents.gpt5_agent import GPT5Agent, GPT5AgentExplicitError
from blackjack_bench.types import Action, Observation, HandView

def create_test_observation(p1: str, p2: str, dealer_up: str) -> Observation:
    """Create a test observation."""
    cards = [f"{p1}H", f"{p2}S"]
    
    # Calculate total and is_soft
    total = 0
    aces = 0
    for card in [p1, p2]:
        if card == "A":
            aces += 1
            total += 11
        elif card in ["J", "Q", "K"]:
            total += 10
        else:
            total += int(card)
    
    # Adjust for aces
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    
    is_soft = (aces > 0)
    can_split = (p1 == p2)
    
    hand_view = HandView(
        cards=cards,
        total=total,
        is_soft=is_soft,
        can_split=can_split,
        can_double=True
    )
    
    return Observation(
        player=hand_view,
        dealer_upcard=f"{dealer_up}H",
        hand_index=0,
        num_hands=1,
        allowed_actions=[Action.HIT, Action.STAND, Action.DOUBLE, Action.SPLIT, Action.SURRENDER]
    )

def test_agent_coverage(agent_name: str, agent, error_class):
    """Test an agent's coverage of different game states."""
    test_cases = [
        # Soft hands
        ("A", "2", "5"),  # Soft 13 vs 5
        ("A", "6", "4"),  # Soft 17 vs 4  
        ("A", "7", "9"),  # Soft 18 vs 9
        
        # Hard hands
        ("5", "7", "2"),  # Hard 12 vs 2
        ("8", "6", "10"), # Hard 14 vs 10
        ("9", "2", "4"),  # Hard 11 vs 4
        
        # Pairs
        ("2", "2", "3"),  # Pair 2s vs 3
        ("8", "8", "6"),  # Pair 8s vs 6
        ("4", "4", "7"),  # Pair 4s vs 7
    ]
    
    covered = 0
    total = len(test_cases)
    
    print(f"\n{agent_name} Coverage Test:")
    print("-" * 30)
    
    for p1, p2, dealer_up in test_cases:
        obs = create_test_observation(p1, p2, dealer_up)
        state_desc = f"{p1},{p2} vs {dealer_up}"
        
        try:
            action = agent.act(obs, {})
            print(f"✓ {state_desc}: {action.name}")
            covered += 1
        except error_class as e:
            print(f"✗ {state_desc}: NO RULE")
        except Exception as e:
            print(f"? {state_desc}: ERROR - {e}")
    
    print(f"\nCoverage: {covered}/{total} ({covered/total*100:.1f}%)")
    return covered, total

def main():
    print("TESTING EXPLICIT RULE COVERAGE")
    print("=" * 50)
    
    claude_agent = ClaudeSonnetAgent()
    gpt5_agent = GPT5Agent()
    
    claude_covered, claude_total = test_agent_coverage("Claude Sonnet", claude_agent, ClaudeSonnetAgentExplicitError)
    gpt5_covered, gpt5_total = test_agent_coverage("GPT-5", gpt5_agent, GPT5AgentExplicitError)
    
    print(f"\n" + "=" * 50)
    print("SUMMARY:")
    print(f"Claude Sonnet: {claude_covered}/{claude_total} ({claude_covered/claude_total*100:.1f}%) - Very vague descriptions")
    print(f"GPT-5: {gpt5_covered}/{gpt5_total} ({gpt5_covered/gpt5_total*100:.1f}%) - Detailed explicit rules")
    print(f"\nGPT-5 provided {gpt5_covered/claude_covered:.1f}x more explicit coverage!")

if __name__ == "__main__":
    main()