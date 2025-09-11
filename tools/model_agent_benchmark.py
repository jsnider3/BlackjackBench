#!/usr/bin/env python3
"""
Tool to benchmark model-thought-based agents against basic strategy using policy-grid evaluation.

This tool runs actual blackjack simulations to measure:
1. Expected value (EV) performance vs BasicStrategyAgent
2. Mistake rates in real gameplay
3. Performance across different game situations
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from blackjack_bench.agents.basic import BasicStrategyAgent
from blackjack_bench.agents.claude_sonnet_agent import ClaudeSonnetAgent
from blackjack_bench.agents.gpt5_agent import GPT5Agent
from blackjack_bench.agents.gemini_flash_agent import GeminiFlashAgent
from blackjack_bench.agents.sonoma_sky_agent import SonomaSkyAgent
from blackjack_bench.agents.gemma_agent import GemmaAgent
from blackjack_bench.eval import run_policy_grid


@dataclass
class BenchmarkResult:
    agent_name: str
    ev_per_hand: float
    ev_weighted: float
    mistake_rate: float
    hands_played: int
    total_decisions: int
    vs_basic_ev_diff: float


class ModelAgentBenchmark:
    def __init__(self, reps: int = 3, seed: int = 42):
        self.reps = reps
        self.seed = seed
        self.basic_agent = BasicStrategyAgent()
        self.model_agents = {
            "claude_sonnet": ClaudeSonnetAgent(),
            "gpt5": GPT5Agent(),
            "gemini_flash": GeminiFlashAgent(),
            "sonoma_sky": SonomaSkyAgent(),
            "gemma": GemmaAgent(),
        }
        
        # Get baseline performance
        print("Running baseline BasicStrategyAgent...")
        self.baseline_result = self._run_agent("basic", self.basic_agent)
        print(f"Baseline EV: {self.baseline_result['metrics']['ev_per_hand']:.6f}")
    
    def _run_agent(self, agent_name: str, agent) -> Dict[str, Any]:
        """Run policy-grid evaluation for a single agent."""
        try:
            result = run_policy_grid(
                agent=agent,
                seed=self.seed,
                weighted=True,
                reps=self.reps,
                log_fn=None  # No logging for benchmark
            )
            return result
        except Exception as e:
            print(f"Error running {agent_name}: {e}")
            return None
    
    def benchmark_agent(self, agent_name: str, agent) -> BenchmarkResult:
        """Benchmark a single agent."""
        print(f"Benchmarking {agent_name}...")
        
        result = self._run_agent(agent_name, agent)
        if result is None:
            return BenchmarkResult(
                agent_name=agent_name,
                ev_per_hand=0.0,
                ev_weighted=0.0,
                mistake_rate=1.0,
                hands_played=0,
                total_decisions=0,
                vs_basic_ev_diff=0.0
            )
        
        metrics = result['metrics']
        ev_per_hand = metrics.get('ev_per_hand', 0.0)
        ev_weighted = metrics.get('ev_weighted', ev_per_hand)
        mistake_rate = metrics.get('mistake_rate', 0.0)
        hands_played = metrics.get('hands', 0)
        total_decisions = metrics.get('decisions', 0)
        
        # Calculate difference vs baseline
        baseline_ev = self.baseline_result['metrics']['ev_per_hand']
        vs_basic_ev_diff = ev_per_hand - baseline_ev
        
        return BenchmarkResult(
            agent_name=agent_name,
            ev_per_hand=ev_per_hand,
            ev_weighted=ev_weighted,
            mistake_rate=mistake_rate,
            hands_played=hands_played,
            total_decisions=total_decisions,
            vs_basic_ev_diff=vs_basic_ev_diff
        )
    
    def benchmark_all_agents(self) -> List[BenchmarkResult]:
        """Benchmark all model agents."""
        results = []
        
        # Add baseline result
        baseline_metrics = self.baseline_result['metrics']
        baseline_result = BenchmarkResult(
            agent_name="basic_strategy",
            ev_per_hand=baseline_metrics['ev_per_hand'],
            ev_weighted=baseline_metrics.get('ev_weighted', baseline_metrics['ev_per_hand']),
            mistake_rate=0.0,  # Basic strategy makes no mistakes by definition
            hands_played=baseline_metrics['hands'],
            total_decisions=baseline_metrics['decisions'],
            vs_basic_ev_diff=0.0
        )
        results.append(baseline_result)
        
        # Test model agents
        for agent_name, agent in self.model_agents.items():
            result = self.benchmark_agent(agent_name, agent)
            results.append(result)
        
        return results
    
    def print_benchmark_report(self, results: List[BenchmarkResult]):
        """Print comprehensive benchmark report."""
        print("\n" + "="*80)
        print("MODEL AGENT BENCHMARK REPORT")
        print("="*80)
        print(f"Test Configuration: {self.reps} reps per cell, seed={self.seed}")
        
        print(f"\nPERFORMance COMPARISON:")
        print(f"{'Agent':<15} {'EV/Hand':<10} {'EV Weighted':<12} {'vs Basic':<10} {'Mistake %':<10} {'Hands':<8}")
        print("-" * 80)
        
        # Sort by EV performance (descending)
        sorted_results = sorted(results, key=lambda x: x.ev_per_hand, reverse=True)
        
        for result in sorted_results:
            ev_diff_str = f"{result.vs_basic_ev_diff:+.6f}" if result.agent_name != "basic_strategy" else "baseline"
            mistake_pct = result.mistake_rate * 100
            print(f"{result.agent_name:<15} {result.ev_per_hand:>8.6f} {result.ev_weighted:>10.6f} "
                  f"{ev_diff_str:>9} {mistake_pct:>8.1f}% {result.hands_played:>6}")
        
        print(f"\nANALYSIS:")
        print(f"- Baseline (BasicStrategy) EV: {results[0].ev_per_hand:.6f}")
        
        model_results = [r for r in results if r.agent_name != "basic_strategy"]
        if model_results:
            best_model = max(model_results, key=lambda x: x.ev_per_hand)
            worst_model = min(model_results, key=lambda x: x.ev_per_hand)
            
            print(f"- Best model agent: {best_model.agent_name} (EV: {best_model.ev_per_hand:.6f}, "
                  f"vs basic: {best_model.vs_basic_ev_diff:+.6f})")
            print(f"- Worst model agent: {worst_model.agent_name} (EV: {worst_model.ev_per_hand:.6f}, "
                  f"vs basic: {worst_model.vs_basic_ev_diff:+.6f})")
            
            avg_mistake_rate = sum(r.mistake_rate for r in model_results) / len(model_results)
            print(f"- Average mistake rate: {avg_mistake_rate * 100:.1f}%")
            
            accurate_agents = [r for r in model_results if r.mistake_rate < 0.05]  # < 5% mistakes
            print(f"- Agents with <5% mistake rate: {len(accurate_agents)}/{len(model_results)}")
            
            if accurate_agents:
                print(f"  - {', '.join(r.agent_name for r in accurate_agents)}")
    
    def save_results(self, results: List[BenchmarkResult], filename: str = "model_agent_benchmark.json"):
        """Save benchmark results to JSON file."""
        data = {
            "config": {
                "reps": self.reps,
                "seed": self.seed
            },
            "results": [
                {
                    "agent_name": r.agent_name,
                    "ev_per_hand": r.ev_per_hand,
                    "ev_weighted": r.ev_weighted,
                    "mistake_rate": r.mistake_rate,
                    "hands_played": r.hands_played,
                    "total_decisions": r.total_decisions,
                    "vs_basic_ev_diff": r.vs_basic_ev_diff
                }
                for r in results
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nResults saved to {filename}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark model-thought-based agents")
    parser.add_argument("--reps", type=int, default=3, help="Repetitions per grid cell")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", type=str, default="model_agent_benchmark.json", help="Output JSON file")
    args = parser.parse_args()
    
    benchmarker = ModelAgentBenchmark(reps=args.reps, seed=args.seed)
    results = benchmarker.benchmark_all_agents()
    benchmarker.print_benchmark_report(results)
    benchmarker.save_results(results, args.output)


if __name__ == "__main__":
    main()