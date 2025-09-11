#!/usr/bin/env python3
"""
Tool to analyze model-thought-based agents for strategy coverage and correctness.

This tool:
1. Tests each model agent against all possible game states
2. Compares their decisions with BasicStrategyAgent (ground truth)
3. Reports coverage (% of states with explicit rules) and accuracy
4. Categorizes types of mistakes
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from blackjack_bench.agents.basic import BasicStrategyAgent
from blackjack_bench.agents.claude_sonnet_agent import ClaudeSonnetAgent
from blackjack_bench.agents.gpt5_agent import GPT5Agent
from blackjack_bench.agents.gemini_flash_agent import GeminiFlashAgent
from blackjack_bench.agents.sonoma_sky_agent import SonomaSkyAgent
from blackjack_bench.agents.gemma_agent import GemmaAgent
from blackjack_bench.types import Action, Observation, HandView


@dataclass
class AgentAnalysis:
    agent_name: str
    total_states: int
    decisions_made: int
    coverage: float  # % of states where agent made a decision
    agreements_with_basic: int
    accuracy: float  # % agreement with basic strategy on decided states
    mistake_categories: Dict[str, int]
    specific_mistakes: List[Tuple[str, str, str, Action, Action]]  # state, agent_action, basic_action


class ModelAgentAnalyzer:
    def __init__(self):
        self.basic_agent = BasicStrategyAgent()
        self.model_agents = {
            "claude_sonnet": ClaudeSonnetAgent(),
            "gpt5": GPT5Agent(),
            "gemini_flash": GeminiFlashAgent(),
            "sonoma_sky": SonomaSkyAgent(),
            "gemma": GemmaAgent(),
        }
        
    def generate_all_states(self) -> List[Tuple[str, str, str]]:
        """Generate all possible (player_card1, player_card2, dealer_up) combinations."""
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        
        states = []
        # All possible two-card combinations (order doesn't matter for our purposes)
        for i, r1 in enumerate(ranks):
            for r2 in ranks[i:]:  # Only take combinations, not permutations
                for du in dealer_up:
                    states.append((r1, r2, du))
        
        return states
    
    def create_observation(self, p1: str, p2: str, dealer_up: str) -> Observation:
        """Create an observation from the card combination."""
        cards = [f"{p1}H", f"{p2}S"]  # Use different suits
        
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
        can_double = True  # Assume always can double on first two cards
        
        # Basic allowed actions
        allowed_actions = [Action.HIT, Action.STAND]
        if can_double:
            allowed_actions.append(Action.DOUBLE)
        if can_split:
            allowed_actions.append(Action.SPLIT)
        allowed_actions.append(Action.SURRENDER)
        
        hand_view = HandView(
            cards=cards,
            total=total,
            is_soft=is_soft,
            can_split=can_split,
            can_double=can_double
        )
        
        return Observation(
            player=hand_view,
            dealer_upcard=f"{dealer_up}H",
            hand_index=0,
            num_hands=1,
            allowed_actions=allowed_actions
        )
    
    def state_to_string(self, p1: str, p2: str, dealer_up: str) -> str:
        """Convert state to readable string."""
        if p1 == p2:
            return f"{p1},{p1} vs {dealer_up}"
        else:
            return f"{p1},{p2} vs {dealer_up}"
    
    def categorize_mistake(self, obs: Observation, agent_action: Action, basic_action: Action) -> str:
        """Categorize the type of mistake."""
        if obs.player.can_split:
            return "pair_strategy"
        elif obs.player.is_soft:
            return "soft_hands"
        elif obs.player.total <= 11:
            return "doubling_opportunities"
        elif 12 <= obs.player.total <= 16:
            return "stiff_hands"
        elif obs.player.total >= 17:
            return "pat_hands"
        else:
            return "other"
    
    def analyze_agent(self, agent_name: str, agent) -> AgentAnalysis:
        """Analyze a single agent's performance."""
        states = self.generate_all_states()
        decisions_made = 0
        agreements = 0
        mistake_categories = defaultdict(int)
        specific_mistakes = []
        
        for p1, p2, dealer_up in states:
            obs = self.create_observation(p1, p2, dealer_up)
            state_str = self.state_to_string(p1, p2, dealer_up)
            
            try:
                # Get agent decision
                agent_action = agent.act(obs, {})
                decisions_made += 1
                
                # Get basic strategy decision
                basic_action = self.basic_agent.act(obs, {})
                
                if agent_action == basic_action:
                    agreements += 1
                else:
                    # Categorize the mistake
                    category = self.categorize_mistake(obs, agent_action, basic_action)
                    mistake_categories[category] += 1
                    specific_mistakes.append((state_str, agent_action, basic_action))
                    
            except Exception as e:
                # Agent couldn't make a decision for this state (no explicit rule)
                # This is expected for faithful implementations
                continue
        
        total_states = len(states)
        coverage = (decisions_made / total_states) * 100 if total_states > 0 else 0
        accuracy = (agreements / decisions_made) * 100 if decisions_made > 0 else 0
        
        return AgentAnalysis(
            agent_name=agent_name,
            total_states=total_states,
            decisions_made=decisions_made,
            coverage=coverage,
            agreements_with_basic=agreements,
            accuracy=accuracy,
            mistake_categories=dict(mistake_categories),
            specific_mistakes=specific_mistakes[:20]  # Limit to first 20 for readability
        )
    
    def analyze_all_agents(self) -> List[AgentAnalysis]:
        """Analyze all model agents."""
        results = []
        for agent_name, agent in self.model_agents.items():
            print(f"Analyzing {agent_name}...")
            analysis = self.analyze_agent(agent_name, agent)
            results.append(analysis)
        return results
    
    def print_analysis_report(self, analyses: List[AgentAnalysis]):
        """Print a comprehensive analysis report."""
        print("\n" + "="*80)
        print("MODEL AGENT ANALYSIS REPORT")
        print("="*80)
        
        # Summary table
        print("\nSUMMARY TABLE:")
        print(f"{'Agent':<15} {'Coverage':<10} {'Accuracy':<10} {'States':<8} {'Agreements':<12}")
        print("-" * 65)
        for analysis in analyses:
            print(f"{analysis.agent_name:<15} {analysis.coverage:>7.1f}% {analysis.accuracy:>8.1f}% "
                  f"{analysis.decisions_made:>6}/{analysis.total_states:<3} {analysis.agreements_with_basic:>10}")
        
        # Detailed analysis for each agent
        for analysis in analyses:
            print(f"\n{analysis.agent_name.upper()} DETAILED ANALYSIS:")
            print("-" * 50)
            print(f"Coverage: {analysis.coverage:.1f}% ({analysis.decisions_made}/{analysis.total_states} states)")
            print(f"Accuracy: {analysis.accuracy:.1f}% ({analysis.agreements_with_basic}/{analysis.decisions_made} agreements)")
            
            if analysis.mistake_categories:
                print("\nMistake Categories:")
                for category, count in sorted(analysis.mistake_categories.items(), key=lambda x: x[1], reverse=True):
                    pct = (count / analysis.decisions_made) * 100
                    print(f"  {category}: {count} ({pct:.1f}%)")
            
            if analysis.specific_mistakes:
                print(f"\nFirst {len(analysis.specific_mistakes)} Specific Mistakes:")
                for state, agent_action, basic_action in analysis.specific_mistakes:
                    print(f"  {state}: {agent_action.name} vs {basic_action.name} (correct)")


def main():
    analyzer = ModelAgentAnalyzer()
    analyses = analyzer.analyze_all_agents()
    analyzer.print_analysis_report(analyses)


if __name__ == "__main__":
    main()