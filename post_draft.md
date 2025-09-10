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

## Results (Snapshot)

| Model | Weighted EV | Mistake Rate |
| :--- | :--- | :--- |
| Basic Strategy | +0.026% | 0.0% |
| Gemma3 12B-IT QAT | -84.4% | 64.5% |
| Sonoma Dusk Alpha | -20.5% | 42.7% |
| Sonoma Sky Alpha | -18.5% | 72.0% |
| Gemini 2.5 Flash (thinking) | +2.24% | 6.03% |
| Gemini 2.5 Flash (no thinking) | -63.96% | 55.57% |
| Gemini 2.5 Flash Lite | -41.88% | 61.54% |

## Why Gemma3 Bombed (Speculation)

The confusion matrix for Gemma3 reveals a clear pattern of mistakes. The model has a strong tendency to `HIT` in situations where it should `STAND` or `DOUBLE`. For example, it incorrectly `HIT` 3497 times when it should have `STOOD`, and 576 times when it should have `DOUBLED`. This over-aggressive strategy is the primary reason for its poor performance.

The model also struggles with `SPLIT` decisions. While it correctly `SPLIT` 252 times, it also incorrectly `SPLIT` 122 times when it should have `HIT`.

In contrast, the model almost never `DOUBLED` when it should have, doing so only 0 times out of 616 opportunities. This aversion to doubling down, combined with its tendency to over-hit, results in a significantly lower expected value.

Confusion matrix (policy‑grid)

| baseline\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT | 2011 | 20 | 0 | 122 | 2153 | 0.066 |
| STAND | 3497 | 91 | 0 | 20 | 3608 | 0.975 |
| DOUBLE | 576 | 0 | 0 | 40 | 616 | 1.000 |
| SPLIT | 5 | 0 | 0 | 252 | 257 | 0.019 |
| total | 6089 | 111 | 0 | 434 | 6634 | 0.645 |

Source: figures/gemma3_confusion.csv

Top leaks (weighted, initial decision only)
| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| pair 10/10 | 10 | STAND | SPLIT | 5 | 6.46% |
| hard 17 | 10 | STAND | HIT | 10 | 4.04% |
| hard 18 | 10 | STAND | HIT | 5 | 3.23% |
| hard 19 | 10 | STAND | HIT | 5 | 3.23% |
| hard 11 | 10 | DOUBLE | HIT | 20 | 3.23% |
| hard 12 | 4 | STAND | HIT | 20 | 1.41% |
| hard 12 | 5 | STAND | HIT | 20 | 1.41% |
| hard 12 | 6 | STAND | HIT | 20 | 1.41% |
| hard 13 | 2 | STAND | HIT | 20 | 1.41% |
| hard 13 | 3 | STAND | HIT | 20 | 1.41% |
| hard 13 | 4 | STAND | HIT | 20 | 1.41% |
| hard 13 | 5 | STAND | HIT | 20 | 1.41% |

What “Weighted Share” means: fraction of the total naturally‑weighted first‑decision mistakes attributable to that row. For each mistaken first decision at a starting cell (p1, p2, dealer upcard), we weight it by its natural frequency under an infinite‑deck model (Pr(10)=4/13, others 1/13; unordered player cards use 2·p1·p2 or p1² for pairs) and then divide the row’s weight by the sum over all mistakes. It reflects prevalence, not severity (no EV loss factor), and only counts the first decision from two‑card starts.

## Gemini 2.5 Flash (non‑thinking)
- Weighted EV (policy‑grid, natural): −0.640 units/hand; mistake rate: 55.6% (zero illegal attempts).
- Error profile: frequently refuses to stand in stand spots (especially vs 10), and declines correct doubles (e.g., 11 vs 10).

Top EV leaks (first decision; weighted by natural frequency; EV loss vs basic):
| Category | Dealer | Baseline | Agent | Count | Weighted EV Loss | Share |
|---|:---:|:---:|:---:|---:|---:|---:|
| pair 10/10 | 10 | STAND | SPLIT | 5 | 0.1457 | 7.68% |
| hard 11 | 10 | DOUBLE | HIT | 20 | 0.0728 | 3.84% |
| hard 17 | 10 | STAND | HIT | 10 | 0.0619 | 3.26% |
| hard 18 | 10 | STAND | HIT | 5 | 0.0583 | 3.07% |
| hard 19 | 2 | STAND | DOUBLE | 5 | 0.0546 | 2.88% |
| hard 19 | 6 | STAND | DOUBLE | 5 | 0.0473 | 2.50% |
| hard 19 | 3 | STAND | DOUBLE | 5 | 0.0437 | 2.30% |
| hard 13 | 2 | STAND | HIT | 20 | 0.0401 | 2.11% |
| hard 19 | 5 | STAND | DOUBLE | 5 | 0.0364 | 1.92% |
| hard 15 | 5 | STAND | DOUBLE | 15 | 0.0364 | 1.92% |
| hard 18 | 6 | STAND | DOUBLE | 5 | 0.0364 | 1.92% |
| hard 13 | 4 | STAND | HIT | 20 | 0.0310 | 1.63% |

Note: EV loss computed by aligning (cell, rep) to a basic‑strategy run and taking baseline_reward − agent_reward. Weighting uses infinite‑deck natural frequencies and counts only the first decision from two‑card starts.

## Thinking
I wanted to do comparisons between models, but an early hypothesis is that thinking would play a big difference,
so I also decided to do thinking vs non-thinking comparisons. For instance for 2.5 Flash.

## Ensuring Fairness
The goal is to avoid hand‑holding: give only the cards and a short rules blurb and let the model do the rest (compute totals, legality, and choose). That keeps the task “general LLM” rather than a parser exercise.

Rules‑lite prompt (exact text used):

```
Blackjack. Rules: 6 decks, dealer hits soft 17 (H17), blackjack pays 3:2, double on any two, double after split allowed, resplit to 3 hands, split aces one-card, no surrender.
Dealer upcard: {UP}.
Your hand: {RANKS}.
Reply with exactly one word: HIT, STAND, DOUBLE, or SPLIT. No explanations.
```

Where `{UP}` is the dealer’s upcard rank (e.g., 10, A) and `{RANKS}` are the player card ranks (e.g., A,7). No totals or allowed‑action list are provided.

Legality guard: when a model proposes an illegal action for the state, I record the violation and substitute an intentionally bad legal fallback (a “BadAgent” that tends to DOUBLE whenever possible, splits tens, etc.). This keeps runs going and penalizes models that ignore rules.

Coverage and logging:
- The policy‑grid plays every two‑card player category × dealer upcard once per rep in a fresh env, aligns RNG by (cell, rep), and reports a weighted EV using natural starting‑hand frequencies.
- JSONL logs include the observation, chosen action, baseline action, legality metadata, and the final outcome for replay/audit.

### Gemini 2.5 Flash: Reasoning Matters

- Policy-grid (5 reps, weighted):
  - Thinking enabled: +2.24% weighted EV, 6.03% mistake rate (4,345 decisions; all responses OK).
  - No thinking: −63.96% weighted EV, 55.57% mistake rate (5,825 decisions; all responses OK).
- What thinking fixes:
  - Pairs: A/A, 10/10, 8/8, 9/9 are perfect with thinking (0% mistakes); no‑thinking frequently misplays pairs (e.g., 5/5 ≈ 95.7%, 4/4 ≈ 79.2% mistakes).
  - High hard totals: thinking stands reliably on 19–21 (0% mistakes); no‑thinking tends to hit 17–21 vs high upcards.
- Remaining gaps with thinking:
  - Over‑doubling soft totals (soft 14–18 vs 3–4), under‑doubling soft 19 vs 6.
  - Hard 10 vs 10/A: tends to DOUBLE where baseline prefers HIT vs 10/A.
- Diagnostic “top leaks” (first decisions, weighted): hard 10 vs 10 (HIT→DOUBLE), hard 15 vs 2 (STAND→HIT), hard 13 vs 2 (STAND→HIT), soft 14/16/17 vs 3–4 (HIT→DOUBLE), soft 19 vs 6 (DOUBLE→STAND).

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
