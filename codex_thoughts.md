# Codex Thoughts — BlackjackBench (internal notes)

This is a scratchpad for roadmap, technical debts, and ideas to polish the benchmark and make big-model runs turnkey. You don’t need to read this unless you’re curious.

## Vision
- Deliver a simple, reproducible benchmark that measures decision quality (and EV) of agents in Blackjack across a clean rules set.
- Make it trivial to compare baselines, local LLMs, and hosted APIs — at small scale for iteration and at large scale for statistically strong conclusions.

## Current Status (snapshot)
- Core simulator: 6D H17 3:2, DAS, no surrender; split-aces one-card. Deterministic shoe with seed.
- Tracks:
  - Policy (natural dealing; persistent shoe).
  - Policy-grid (550 cells × reps; fresh env per cell; optional weighted EV).
- Baselines: BasicStrategyAgent, RandomAgent, BadAgent (formerly WorstAgent).
- LLM harness: providers openai (modern + legacy), ollama (HTTP), gemini (Google SDK), prompt modes (minimal, rules_lite default, verbose), legality guard.
- CLI niceties: default JSONL logging, per-decision debug printing, heartbeat progress.
- Tools: summarize_confusion.py for baseline→agent action matrix.

## Technical Debts / Fixups
- Rules realism and toggles
  - Optional dealer peek rule (S17/H17 variants with peek when upcard is A/10). Today we handle naturals before decisions, which is effectively a peek; confirm semantics for surrender-on variants when enabled later.
  - Surrender: currently off; when enabled, ensure late-surrender timing and metrics (half-bet loss) are handled and surfaced in outcomes.
  - Split tens: allowed by rules, but basic strategy never splits; keep as-is (configurable?), and ensure basic charts reflect S17/H17 and DAS toggles if we expand rules.
- Observation design
  - We hide running/true counts in policy-grid; verify no leakage in prompts (we’ve removed totals/allowed-actions in default prompt).
- Soft-hand logic
  - Implemented via ace reductions; currently correct (is_soft iff at least one Ace valued at 11). Consider unit tests.
- Forced starts (grid)
  - `_take_from_shoe` pulls ranks; we increment running_count for visible cards; the dealer hole card is drawn via `_draw()` (affects count later). Good. If we add a counting-allowed track, revisit visibility.
- Illegal actions
  - Default env policy raises; CLI uses GuardedAgent to log + worst-legal fallback. Optional evaluator-side penalize policy could be offered for benchmarks that want standardized penalties.

## Methodology Notes
- Weighted EV
  - Current weights use infinite-deck approximation: p(r)=1/13 except p(10)=4/13; pair probability uses combination with repetition; independent dealer upcard. It’s close enough; add option for finite-deck exact weights (computable analytically) if needed.
- Mistake rate
  - Measured vs basic strategy table (6D H17 DAS); not a true optimal policy. Future: Monte-Carlo EV oracle to verify or to quantify mistake severity (EV delta, not just mismatch count).
- RNG alignment
  - Grid uses seed + cell_index*1009 + rep; keeps (cell,rep) comparable across agents while ensuring different reps differ. Documented behavior.

## LLM Harness Improvements
- Providers
  - Gemini: use official API client with model/temperature/max_output options.
  - OpenAI path is fine (uses new `OpenAI()` client). Consider Azure OpenAI switch.
  - Ollama: add chat endpoint support and grammar constraints to force tokens (HIT/STAND/DOUBLE/SPLIT/SURRENDER).
- Performance & Robustness
  - Add `--llm-timeout`, `--retries`, `--retry-backoff` to survive long runs.
  - Decision cache (optional): memoize on serialized Observation + prompt mode. Especially effective on grid across reps.
  - Strict decoding: grammars or regex validation; currently GuardedAgent already shields illegal choices.

## Scaling (so we can “flip the switch”)
- Sharding
  - `--shard-index i --shard-count k` for policy-grid to partition the (cell,rep) space deterministically. Include shard metadata in the manifest and filename.
- Resume
  - `--resume-from <jsonl>`: scan completed (cell,rep) keys and skip them, appending to the same (or a new) log.
- Compression & manifests
  - `--compress` to write `.jsonl.gz`.
  - First line manifest: a compact JSON run header with provider, model, prompt_mode, rules, seed, reps, shard info, etc.
- ETA & latency
  - Extend heartbeat with rolling average per-decision latency and ETA to completion.

## Analysis & Reporting
- Summarizer CLI
  - `summarize` command that aggregates one or more logs into:
    - Metrics table (ev_weighted, ev_per_hand, decisions, mistake_rate, illegal_rate).
    - Confusion matrix CSV.
    - Per-cell CSV (avg reward, count, mistake rate), suitable for heatmaps.
    - (Optional) seed-aggregated stats (mean ± 95% CI).
- Leak profiling
  - Breakdown by (hard/soft/pairs total) × dealer upcard.
  - Top-N high-cost mismatches by EV delta if oracle is implemented.

## Testing Plan
- Unit tests
  - cards.hand_totals (hard/soft cases)
  - env: dealer play H17/S17, split-aces one-card, double-after-split flags, blackjack payouts.
  - basic strategy: golden tests for canonical chart rows (A,7 vs upcards; hard 12–16; pairs).
- Property tests
  - Determinism with seed
  - Grid coverage: exactly 550 cells per rep; hands count matches; weighted weights sum to 1.

## Packaging & DX
- Turn this into a proper Python package with an entry point `blackjack-bench`.
- Add pyproject.toml, pinned deps (optional), and a lightweight CI (lint/test only).
- Improve README with a quickstart matrix, sample outputs, and links to tools.

## Post / Docs Ideas
- Figures: confusion matrix (Gemma vs Gemini), per-cell EV heatmap.
- Method appendix: exact rules, seeds, prompt text, legality guard policy.
- Discussion: why “perfect” computers aren’t interesting, but LLM comparisons are.

## Potential Features (later)
- Counting & betting tracks: add Hi-Lo baseline, bet spread testing, true-count correlation.
- Rationale capture: optional “Reason:” text that’s logged but not scored.
- Multi-agent tournaments: pit agents head-to-head on the same prelogged deals.

## Nice-to-Haves
- CLI grammars for Ollama (herd outputs to exact action tokens).
- Offline ask_fn stubs for LLM Agent to let users test flow without network.
- Notebook examples for analysis (confusion, heatmaps, EV convergence plots).

— end —
