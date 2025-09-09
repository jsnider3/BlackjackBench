# BlackJackBench: Benchmarking LLMs at Blackjack

## TL;DR
- I built BlackJackBench: a reproducible Blackjack benchmark with a simulator, baselines, and a policy‑grid that covers all 550 starting positions.
- “Perfect” computer play is straightforward; the interesting question is how LLMs compare under fair prompting and strict legality.
- In early runs, Gemma3 performed very poorly; Gemini 2.5 did much better. Everything is seeded, logged, and easy to rerun.

## Why Blackjack
- Simple, well‑understood rules; partially observable; crisp outcomes and ground truth.
- A near‑optimal basic strategy exists, so we can measure decision mistakes and expected value precisely.
- Local decisions (HIT/STAND/DOUBLE/SPLIT) make it easy to isolate and score errors.

## Benchmark Design
- Rules (defaults): 6‑deck shoe, dealer hits soft 17 (H17), Blackjack 3:2, double on any two, double after split (DAS), no surrender, split aces one‑card, resplit to 3 hands.
- Tracks:
  - Policy: Natural dealing. Metrics: EV/hand and mistake rate vs basic strategy.
  - Policy‑grid: 55 two‑card player categories × 10 dealer upcards = 550 cells. Each cell is played once per rep in a fresh env (no carryover). Weighted EV uses natural frequencies.
- Metrics:
  - EV/hand: net units per hand.
  - ev_weighted: natural‑frequency average over the grid.
  - mistake_rate: fraction of decisions that differ from a fixed 6D H17 DAS basic strategy.
- Reproducibility: All runs are seeded; every decision and final outcome is logged as JSONL for replay/audit.

## Model Thoughts
I figured I would ask the models what they know about blackjack before spending the money to run full tests. You can read their answers yourself
at [TODO Insert links], but I'll explain the key points.

They mostly assumed S17 (dealer stands on soft 17), 6–8 decks, 3:2 payouts
on blackjack, DAS on, no surrender by default. Aside from S17, that's what we're using. S17 surprised me since dealer hitting on 17 is more common in the real world and I had already written the code with H17 in mind. There was broad agreement on "using basic strategy": don't take insurance, always split A/A and 8/8, never split 10/10, stand on hard 17+, there was some disagreement between models about when and whether to double 10/11. Gemma was the only one with real errors where it doubles soft 19–21.

The Gemini ones were using Google Search to ground their thoughts, maybe I should see how they respond without that?
- Gemini 2.5 Pro and Flash
  - Assume S17 and give technically consistent basic‑strategy guidance; Pro is verbose, Flash is concise.
  - Correct hard/soft/pairs advice; explicitly avoid insurance; reasonable double rules.

- Claude Sonnet 4 and Opus 4.1
  - Assume or imply S17; cover hard/soft/pairs accurately; Opus lists clean double heuristics (11 vs 2–A; 10 vs 2–9; 9 vs 3–6).
  - Sensible notes on bankroll and avoiding side bets.

- GPT‑5 and GPT‑5 Nano
  - Assume S17; solid basic strategy. GPT‑5 adds surrender guidance (e.g., 16 vs 9/10/A; 15 vs 10) and a few Hi‑Lo deviations; Nano is concise and consistent.

- Gemma
  - Inconsistent rules (mentions both H17 and “dealer stands on 17”), and a clear error: “double down on soft 19–21.”
  - Overall confident tone, but soft‑hand guidance and rule assumptions are off.

## LLM Integration (Fair and Simple)
- Prompt: “rules‑lite” (cards + short rules), no totals/allowed‑actions to avoid hand‑holding.
- Legality guard: If a model proposes an illegal action, we log it and substitute the worst legal move so runs continue and the agent is penalized.

## Results (Early Snapshot)
- Basic strategy (sanity check):
  - Policy (1M hands): EV ≈ −0.48% (expected for 6D H17 3:2 DAS).
  - Policy‑grid weighted: near the canonical −0.5% to −0.7%, depending on reps.
- BadAgent (deliberately poor heuristic):
  - Weighted grid: ≈ −0.61 to −0.64 EV/hand.
- Gemma3 (rules‑lite, guarded):
  - Weighted grid (5 reps): ev_weighted ≈ −0.84, mistake_rate ≈ 64%.
  - Interpretation: heavy over‑hitting, ill‑timed splits, almost never doubles correctly; worse than the bad heuristic.
- Gemini 2.5 (rules‑lite, guarded):
  - Policy (50 hands, small sample): EV ≈ −0.09, mistake_rate ≈ 8.75%.
  - Much better behavior even with minimal hints; follow‑up grid runs suggested.

## Why Gemma3 Bombed (Speculation)
- Minimal prompts require the model to infer basic strategy rather than rely on explicit totals/hints.
- Gemma3 over‑indexed on HIT and avoided DOUBLE almost entirely. Misplays of high‑frequency stand states (e.g., hard 12–16 vs 7–A) are expensive.
- In contrast, Gemini handled stand/hit boundaries more sanely, even with minimal hints.

## Ensuring Fairness
I wanted to minimize the hand-holding I was giving the models, so I
decided to just give them the cards and the rules and leave it up to
the model to calculate the total and what actions were allowed.
If they tried illegal actions, I just make a terrible decision on their
behalf.

I created a grid of every possible combination of cards the player and dealer
could have and ran the model on every possibility then weighted the results
by how common those combinations actually are. This ensured every edge case was handled while making the EV estimate accurate.

- Policy‑grid isolates hands (fresh env per cell), aligns RNG by (cell, rep), and reports a weighted EV for natural‑frequency estimates.
- JSONL logs every decision with observation, action, baseline comparison, and the final hand outcome.

## How to Run (Reproducible Examples)
- Baseline sanity:
  - `python -m blackjack_bench.cli run --agent basic --track policy --hands 100000 --seed 7`
- Policy‑grid weighted (basic):
  - `python -m blackjack_bench.cli run --agent basic --track policy-grid --weighted --reps 100 --seed 7`
- LLM example (Gemini API):
  - `python -m blackjack_bench.cli run --agent llm --guard --llm-provider gemini --llm-model gemini-2.5-flash --track policy-grid --weighted --reps 5 --seed 7`
- Inspect confusion (baseline vs agent):
  - `python tools/summarize_confusion.py --track policy-grid logs/<timestamp>_policy-grid_<agent>_<model>.jsonl --csv confusion.csv`

## TODO
- Use the official Gemini API for throughput and reliability.
- Do the rest of the models.
- Check some reasoning traces. Do they know what the correct action, are they looking it up, are they calculating it?
- Sharding/resume/retries: split 550×reps across processes/machines and resume cleanly on failure.
- Weighted mistake profiling: “top leaks” by (player total/soft/pair, dealer upcard).
- Check if the mistakes would be correct under a different ruleset.
- Optional grammar constraints for action‑only decoding; decision caching to reduce repeated LLM calls across reps.
- Remark about how some models degenerate into one action.
- Check how much each model followed the strategy it said it would follow.

## Closing Thought
You can solve Blackjack “perfectly” with a table. The interesting test is whether general LLMs—without crutches—can approach reasonable play. Early signals show sizable gaps between models. A benchmark like BlackJackBench makes those differences obvious, repeatable, and actionable.

<!-- Optional figures/placeholders -->
<!-- Figure: Confusion matrix (baseline vs agent) -->
<!-- Figure: Per-cell EV heatmap (policy-grid, weighted) -->
