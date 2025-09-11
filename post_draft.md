# BlackJackBench: Benchmarking LLMs at Blackjack

## TL;DR
- I built BlackJackBench: a reproducible Blackjack benchmark with a simulator, baselines, and a policy‑grid that covers all 550 starting positions.
- **Key Finding**: Thinking capability transforms models from significant losers to winners. Claude Sonnet 4 achieves perfect basic strategy performance (+2.6% EV, 4.0% mistakes) while Gemini 2.5 Flash goes from -64% EV (no thinking) to +2.2% EV (with thinking).
- "Perfect" computer play is straightforward; the interesting question is how LLMs compare under fair prompting and strict legality.
- Many models perform poorly (40-80% mistake rates), but thinking-enabled models can match basic strategy accuracy. Everything is seeded, logged, and easy to rerun.

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

## Methodology: Key Concepts

**Policy-Grid**: Rather than random dealing, we systematically test all 550 possible starting positions (55 two-card player categories × 10 dealer upcards). Each cell gets fresh environment state with no card-counting carryover effects.

**Weighted Expected Value**: Uses natural frequency weighting based on infinite-deck probabilities. A 10,10 vs Ace scenario (high-frequency) gets more weight than A,2 vs 7 (low-frequency), reflecting real-world importance.

**Basic Strategy Baseline**: We compare against fixed 6-deck H17 DAS basic strategy tables. This isn't perfect play (card counting would be better) but represents the established "correct" decision for each situation.

**Mistake Rate**: Simple percentage of decisions that differ from basic strategy baseline, regardless of outcome or severity.

## LLM Integration (Fair and Simple)
- Prompt: “rules‑lite” (cards + short rules), no totals/allowed‑actions to avoid hand‑holding.
- Legality guard: If a model proposes an illegal action, we log it and substitute the worst legal move so runs continue and the agent is penalized.

## Results Summary

The results reveal dramatic performance differences between models, with **thinking capability being the decisive factor**:

| Model                           | Weighted EV | 95% CI             | Mistake Rate | Decisions |
| :---                            | :---------: | :----:             | :----------: | :---: |
| **Basic Strategy**              | **+2.6%**   | —                  | **0.0%**     | — |
| **Claude Sonnet 4 (thinking)**  | **+2.6%**   | **[-4.2%, +5.8%]** | **4.0%** | 4,281 |
| **Gemini 2.5 Flash (thinking)** | **+2.2%**   | **[-4.5%, +5.6%]** | **6.0%** | 4,345 |
| **Gemini 2.5 Pro**              | **+1.2%**   | **[-4.4%, +5.5%]** | **2.1%** | 4,358 |
| Claude Sonnet 4 (no thinking)   | -7.8%       | [-12.1%, -3.5%]    | 36.1% | 4,979 |
| Sonoma Sky Alpha                | -12.6%      | [-26.8%, -19.5%]   | 72.6% | 2,669 |
| Sonoma Dusk Alpha               | -20.5%      | [-25.2%, -15.8%]   | 42.7% | 4,804 |
| Gemini 2.5 Flash Lite           | -41.9%      | [-45.7%, -31.6%]   | 61.5% | 3,877 |
| Gemini 2.5 Flash (no thinking)  | -64.0%      | [-81.0%, -71.8%]   | 55.6% | 5,825 |
| Gemma3 12B-IT QAT               | -84.4%      | [-87.9%, -81.0%]   | 64.5% | 6,794 |

**Key Insight**: Three thinking-enabled models (Claude Sonnet 4, Gemini 2.5 Flash, and Gemini 2.5 Pro) achieve positive expected value and cannot be statistically distinguished from ideal basic strategy play at the 95% confidence level. Notably, Sonoma Sky Alpha demonstrates that mistake frequency doesn't always correlate with EV loss—its 72.6% mistake rate only costs -12.6% EV due to using a degenerate "always STAND" strategy where mistakes are relatively inexpensive.

## What Models "Know" About Blackjack

Before running expensive benchmarks, I asked models about their blackjack knowledge. You can read their detailed responses in the [model_thoughts/](model_thoughts/) directory, but here are the key patterns:

**Rule Assumptions**: Most models assumed S17 (dealer stands on soft 17), 6-8 decks, 3:2 payouts, DAS enabled, no surrender. This differs from our H17 setup, but the fundamental strategies remain similar.

**Strategic Knowledge**: There was broad agreement on core principles: don't take insurance, always split A/A and 8/8, never split 10/10, stand on hard 17+. Models showed varying sophistication on doubling decisions.

**Model-Specific Insights**:
- **Gemini 2.5 Pro/Flash**: Technically consistent basic strategy guidance with Google Search grounding
- **Claude Sonnet 4/Opus 4.1**: Accurate hard/soft/pairs advice with clean double heuristics  
- **GPT-5/5 Nano**: Solid basic strategy, with GPT-5 adding surrender and Hi-Lo deviations
- **Sonoma Sky/Dusk Alpha**: Industry rumors strongly suggest these are new xAI Grok variants (Sky = smarter, Dusk = faster), though this remains unconfirmed
- **Gemma**: Inconsistent rules and a critical error: "double down on soft 19-21"

**The knowledge gap doesn't explain performance differences** - even models with solid theoretical understanding failed dramatically in practice without thinking enabled. Interestingly, human experts who play perfect basic strategy aren't really "thinking" about blackjack either - they've memorized optimal decisions cold, making the thinking requirement for LLMs all the more notable.

## The Thinking Breakthrough: Claude Sonnet 4 and Gemini 2.5 Flash Analysis

The most striking finding is how thinking transforms the same underlying models, with Claude Sonnet 4 achieving the best overall performance:

### Claude Sonnet 4: Near-Perfect Performance
- **With Thinking**: +2.6% EV, 4.0% mistake rate (4,281 decisions) - matches basic strategy exactly
- **Without Thinking**: -7.8% EV, 36.1% mistake rate (4,979 decisions)  
- **Net Impact**: 10.4 percentage point EV improvement, 32.1 point mistake reduction

### Gemini 2.5 Flash: Dramatic Transformation  
- **With Thinking**: +2.2% EV, 6.0% mistake rate (4,345 decisions)
- **Without Thinking**: -64.0% EV, 55.6% mistake rate (5,825 decisions)
- **Net Impact**: 66.2 percentage point EV improvement

### What Thinking Fixes (Both Models)
- **Perfect Fundamental Decisions**: A/A and 8/8 splits, standing on 19-21
- **Strategic Consistency**: Fewer random or contradictory actions  
- **Complex Situation Handling**: Better doubling and splitting decisions

### Remaining Gaps (Even With Thinking)
**Claude Sonnet 4**: Minor over-doubling on soft hands vs weak dealer cards
**Gemini 2.5 Flash**: Over-doubling soft totals, under-doubling soft 19 vs 6

### Sample Reasoning Quality
The thinking traces show genuine strategic reasoning: calculating bust probabilities, considering dealer weak cards, referencing basic strategy principles. This isn't memorized responses but actual step-by-step analysis.

### The Imaginary Strategy Card Phenomenon
A particularly interesting pattern emerges from the thinking traces: models frequently consult imaginary "basic strategy charts" or "lookup tables" during their reasoning process. Despite these references being entirely fictional, this simulated consultation proves remarkably effective at producing correct decisions. Rather than purely calculating from first principles, thinking-enabled models often treat basic strategy as an external reference to be consulted—a form of reasoning that bridges pure calculation and pattern lookup.

### The Sky Alpha Anomaly: When "Always Stand" Works
Sonoma Sky Alpha reveals an important insight about mistake severity in blackjack. Despite making the wrong decision 72.6% of the time, its EV loss is only -12.6%—much better than models with lower mistake rates. The confusion matrix reveals why: Sky Alpha uses a completely degenerate "always STAND" strategy, never hitting, doubling, or splitting. While this is almost always wrong, standing tends to be less catastrophic than other poor choices, demonstrating that not all mistakes are created equal in strategic games.

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


## How to Run (Reproducible Examples)
- Baseline sanity:
  - `python -m blackjack_bench.cli run --agent basic --track policy --hands 100000 --seed 7`
- Policy‑grid weighted (basic):
  - `python -m blackjack_bench.cli run --agent basic --track policy-grid --weighted --reps 100 --seed 7`
- LLM example (Gemini API with thinking):
  - `python -m blackjack_bench.cli run --agent llm --guard --llm-provider gemini --llm-model gemini-2.5-flash --reasoning low --track policy-grid --weighted --reps 5 --seed 7`
- LLM example (Anthropic Claude with thinking):
  - `python -m blackjack_bench.cli run --agent llm --guard --llm-provider anthropic --llm-model claude-sonnet-4-20250514 --reasoning low --track policy-grid --weighted --reps 5 --seed 7`
- Inspect confusion (baseline vs agent):
  - `python tools/summarize_confusion.py --track policy-grid logs/<timestamp>_policy-grid_<agent>_<model>.jsonl --csv confusion.csv`

## Future Work
- **Expand Model Coverage**: Test remaining frontier models (GPT-4o, Claude 3.5 Sonnet, etc.)
- **Reasoning Analysis**: Deeper analysis of thinking traces to understand decision-making processes
- **Rule Variant Testing**: Check if mistakes would be optimal under different blackjack rulesets
- **Strategic Consistency**: Compare actual play patterns against models' stated strategies
- **Scale & Engineering**: Sharding, resumption, and caching for large-scale evaluations
- **Card Counting**: Basic blackjack is solved, but can they keep count?

## Conclusion: The Thinking Revolution

**BlackJackBench reveals a fundamental breakthrough**: thinking capability doesn't just improve LLM performance—it transforms models from systematic losers into near-optimal players. The 66-point EV swing between thinking and non-thinking versions of Gemini 2.5 Flash represents the difference between bankruptcy and profitability.

**Key Takeaways**:
- **Thinking is transformative**: The same model architecture produces radically different outcomes based solely on reasoning capability
- **Knowledge ≠ Performance**: Models with solid theoretical understanding still fail without step-by-step reasoning
- **Systematic evaluation matters**: BlackJackBench's policy-grid approach reveals performance patterns invisible in random testing
- **Benchmark ceiling effect**: Basic strategy blackjack may not be challenging enough to distinguish top thinking-enabled models, which all achieve near-optimal performance

**The Need for Harder Challenges**: Three models (Claude Sonnet 4, Gemini 2.5 Flash, and Gemini 2.5 Pro) all achieve statistically indistinguishable performance from perfect basic strategy. This suggests that basic blackjack decision-making has become a solved problem for frontier thinking-enabled models. To truly differentiate model capabilities, more complex challenges like card counting—which requires maintaining running counts, true count conversion, and betting strategy adjustments—would provide better discrimination between reasoning systems.

**Implications Beyond Blackjack**: If thinking capability creates such dramatic improvements in a well-defined domain like blackjack, the implications for complex real-world reasoning tasks are profound. However, the ceiling effect observed here also suggests we need more sophisticated benchmarks to push the boundaries of what these systems can achieve.

You can solve Blackjack "perfectly" with a lookup table, but the interesting question is whether general intelligence can discover and apply those solutions through reasoning alone. Ironically, human experts who achieve perfect basic strategy aren't really "thinking" about blackjack either—they've simply memorized the correct decisions cold. The answer, it turns out, depends critically on whether that reasoning process is made explicit. The next frontier lies in challenges that can't be solved by lookup tables alone.

<!-- Optional figures/placeholders -->
<!-- Figure: Confusion matrix (baseline vs agent) -->
<!-- Figure: Per-cell EV heatmap (policy-grid, weighted) -->
