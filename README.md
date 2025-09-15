BlackjackBench — A Blackjack-Based Benchmark for AI Agents

Overview
- Purpose: Evaluate decision-making, reasoning, and planning of AI agents in a constrained, partially observable environment with crisp ground truth and outcome metrics.
- Approach: Provide a reproducible Blackjack simulator, agent protocol, standardized tasks (tracks), and automatic scoring. Include strong baselines and a simple CLI to run evaluations and produce reports.

Benchmark Tracks
- Policy Track: Agent plays fixed-stake Blackjack hands. Score by expected value (EV) per hand and mistake rate vs. an optimal/basic strategy reference under specified rules.
- Counting Track: Multi-hand shoe with limited memory. Score how EV and bet sizing improve with true-count; include correlation of wagers with true-count and EV lift over flat betting.
- Betting Track: Agent controls bet size subject to table limits; actions scored by bankroll growth, risk of ruin, and EV vs. a counting-aware baseline.
- Reasoning Track (optional): Agent outputs an action plus a brief rationale. Primary score remains action quality; rationale is logged for qualitative analysis, not graded automatically.

Rules and Variants
- Defaults (v0): 6-deck shoe, dealer hits soft 17 (H17), Blackjack pays 3:2, double on any two cards, double after split allowed, resplit to 3 hands, aces split once with one-card draw, late surrender off.
- Configurable: Deck count, penetration, S17/H17, 3:2 vs 6:5, DAS, surrender, split limits, table min/max.

Observation Space
- Hand: Player cards and derived totals (hard/soft), active split hand index, available actions.
- Dealer: Upcard; hole card hidden until terminal.
- Shoe: Cards remaining (not visible), running/true count exposure toggled by track (for counting-allowed variants, agent must compute from visible cards only).
- History: Prior hands in current shoe (for tracks that allow memory). History length is configurable; log always contains all revealed cards for deterministic replay.

Action Space
- Core actions: HIT, STAND, DOUBLE (if allowed), SPLIT (if allowed), SURRENDER (if allowed).
- Betting: Optional per-hand bet within table limits (Betting/Counting tracks).
- Output format: Structured JSON or a simple token string (e.g., "HIT", "BET 2x"). CLI adapters convert to enums.

Episodes and Scoring
- Episode: One hand (Policy track) or a multi-hand shoe (Counting/Betting tracks).
- Primary metrics: EV/hand, total return, house-edge delta vs. basic/optimal, mistake rate by decision type.
- Secondary metrics: Bet-count correlation (Spearman), EV lift over flat betting, risk-of-ruin estimate, variance, time/steps per decision.
- Reproducibility: All runs seeded; full card reveal logs enable exact replay.

Agent Protocol
- Function interface: `act(observation, info) -> action` where observation encodes only allowed information per track.
- Stateless vs. stateful: Agents may keep internal state (e.g., running count). The harness can also provide a scratchpad that persists within a shoe.
- Time limits: Optional per-decision timeout for fairness; default generous for offline evaluation.

Baselines
- Random agent: Uniform random valid action selection.
- Basic strategy agent: Deterministic lookups for the configured rules.
- Simple counter: Hi-Lo running/true count with conservative bet spread and a few high-leverage deviations (e.g., Illustrious 18).

Outputs and Reports
- JSONL per-episode trace: observations, actions, rewards, revealed cards.
- Summary report: metrics per track, confidence intervals, and comparisons against baselines.
- Replays: Deterministic re-simulation from logs for auditability.

CLI
- Run benchmark: `python -m blackjack_bench.cli run --agent basic --track policy --hands 10000 --seed 42 --report report.json`
- Compare agents: `python -m blackjack_bench.cli compare --agents basic,random --track policy --hands 20000`
 - Policy grid (all 550 starts once): `python -m blackjack_bench.cli run --agent basic --track policy-grid --seed 7`
 - Weighted grid EV (natural frequencies, infinite-deck): `python -m blackjack_bench.cli run --agent basic --track policy-grid --weighted --seed 7`
   - Optional reps to reduce variance while still covering all cells: `--reps 50`
 - Guard illegal actions and fall back to the worst legal move: add `--guard` to any run.
 - Resume + logging behavior: if you pass `--resume-from <log.jsonl>` and omit `--log-jsonl`, new events append to `<log.jsonl>` automatically. Specify `--log-jsonl` to override.
 - Use an LLM as the agent: `--agent llm --llm-provider openai --llm-model gpt-4o-mini` (requires `openai` package and `OPENAI_API_KEY`). Combine with `--guard` for robust benchmarking.
 - Use Google Gemini (official SDK): `--agent llm --llm-provider gemini --llm-model gemini-1.5-flash` (requires `google-generativeai` and either `GOOGLE_API_KEY` or `GEMINI_API_KEY`).

Roadmap
- v0: Simulator, policy track, basic strategy + random baselines, EV and mistake metrics, CLI + reports.
- v0.1: Counting + betting tracks, simple counter baseline, count-aware deviations.
- v1: Configurable rules matrix, rationale logging, richer reports, harness adapters.

Contributing
- Keep changes minimal, deterministic, and well-tested. Prefer small PRs that add focused capabilities.
