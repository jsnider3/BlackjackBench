---
layout: post
title: "BlackjackBench and The Thinking Revolution"
date: 2025-09-15 09:00:00 -0400
categories: update ai benchmark blackjack
---

## TL;DR
- I built BlackjackBench: a Blackjack benchmark covering all 550 initial hands. It can be easily rerun with everything logged and random seeds controllable.
- Key metric is difference in expected value (ΔEV) compared to the basic‑strategy baseline on the exact same seeded hands. With thinking enabled, models approach baseline: Claude Sonnet 4 (ΔEV ≈ −0.06%, 4.0% mistakes) and GPT‑5 Nano (medium) (ΔEV ≈ −0.12%, 5.0%). Notably, Gemini 2.5 Flash improves dramatically from ΔEV −66.6% (no thinking) to −0.43% with thinking[^2].
- "Perfect" computer play is straightforward; the interesting question is how LLMs compare under fair prompting and strict legality, and what model progress implies for general problems.
- Many non-thinking models perform poorly (making mistakes on 40–80% of hands), but thinking-enabled models can match basic strategy accuracy.

## Why Blackjack
- It has simple, well‑understood rules with clear outcomes and well-defined truth. The player knows a lot, but not everything.
- A near‑optimal basic strategy exists, so we can measure decision mistakes and expected value precisely.
- Local decisions (HIT/STAND/DOUBLE/SPLIT) make it easy to isolate and score errors.

## Benchmark Design
- Rules (defaults): 6‑deck shoe, dealer hits soft 17 (H17), blackjack pays 3:2, double on any two, double after split (DAS), no surrender, split aces one‑card, resplit to 3 hands.
- Evaluation mode: Policy‑grid only. We enumerate 55 two‑card player categories × 10 dealer upcards = 550 cells. Each cell is played in a fresh environment once per repetition (no carryover or counting effects). Most results use multiple reps to reduce variance.
- Weighting: In addition to the simple mean across played cells, we report a natural‑frequency weighted EV using infinite‑deck probabilities so common starts contribute proportionally.
- Metrics:
  - EV/hand: mean net units per hand over the executed grid reps (unweighted).
  - ev_weighted: natural‑frequency weighted EV over the grid.
  - mistake_rate: fraction of decisions that differ from a fixed six‑deck H17 DAS basic strategy[^6].
- Reproducibility: Deterministic RNG seeds; per‑decision JSONL logs enable exact replay/audit; supports parallelizing long runs and resuming them after interruption.

## Methodology: Key Concepts

**Policy-Grid**: Rather than random dealing, we systematically test all 550 possible starting positions (55 two-card player categories × 10 dealer upcards). Each cell runs in a fresh environment (no card exposure or counting carryover).

**Weighted Expected Value**: Rather than treating all 550 starting hands equally, we weight each situation by how often it naturally occurs in real blackjack. This gives a more realistic overall EV that reflects actual play patterns.

The weighting uses infinite-deck probabilities to calculate how frequently each starting hand appears. For example:
- Common situations like "two 10-value cards vs dealer Ace" occur frequently (weight ≈ 0.00728)
- Rare situations like "Ace,2 vs dealer 7" occur less often (weight ≈ 0.00091)

When computing the final EV, each hand's performance gets multiplied by its natural frequency weight. This means:
- A mistake on 10,10 vs A hurts the weighted EV significantly (high frequency × EV loss)
- The same mistake on A,2 vs 7 barely affects weighted EV (low frequency × EV loss)

Thus, weighted EV emphasizes performance on the hands players actually encounter most often.[^7]

**Basic Strategy Baseline**: We compare against fixed 6-deck H17 DAS basic strategy tables[^6]. This isn't perfect play (card counting would be better[^10]) but represents the established "correct" decision for each situation.

**Mistake Rate**: A simple percentage of decisions that differ from basic strategy.

**ΔEV Reporting**: We report ΔEV relative to the empirical Basic Strategy baseline for the exact, seeded 2,750 hands. In this run, Basic Strategy's absolute EV is +2.6%[^1] due to these hands being friendly to the player with this seed. ΔEV makes comparisons clearer and fair across models.

## LLM Integration

**What is "thinking"?** Throughout this study, "thinking" refers to Chain-of-Thought prompting where models generate intermediate reasoning steps before outputting their final decision. For OpenAI models, this uses the reasoning effort parameter; for Anthropic models, this enables the thinking budget; for Google models, this uses reasoning summaries. Non-thinking models respond directly without explicit step-by-step reasoning.

- Prompt style: "rules‑lite" — only the upcard, your two ranks, and a short rules blurb. No totals and no allowed‑actions list.
- Output contract: Return exactly one of HIT, STAND, DOUBLE, SPLIT. The harness maps minor variants; illegal choices trigger a guarded fallback and are logged.
- Reasoning levels: `none | medium`. When enabled, providers may return a thinking trace which we log but do not grade.
- Legality guard: We check the agent's proposed action. If it's illegal, we count that and instead take a deliberately bad legal action to penalize non‑compliance[^5].

Rules‑lite prompt (exact text used):

```
Blackjack. Rules: 6 decks, dealer hits soft 17 (H17), blackjack pays 3:2, double on any two, double after split allowed, resplit to 3 hands, split aces one-card, no surrender.
Dealer upcard: {UP}.
Your hand: {RANKS}.
Reply with exactly one word: HIT, STAND, DOUBLE, or SPLIT. No explanations.
```

Where `{UP}` is the dealer's upcard rank (e.g., 10, A) and `{RANKS}` are the player ranks (e.g., A,7). We intentionally omit totals and allowed‑actions to test whether the model can figure that out on its own.

Now, what did we find when we put these models to the test?

## The Main Event: Thinking is Transformative

The results reveal dramatic performance differences between models, with **thinking capability being the decisive factor**.

| Model[^3]                           | ΔEV vs Baseline | Mistake Rate | Decisions |
| :---                                | :-------------: | :----------: | :-------: |
| **Basic Strategy**                  | **+0.0%**       | **0.0%**     | —         |
| **GPT‑5 (thinking, medium)**        | **+0.01%**      | **1.2%**     | 4,341     |
| Claude Sonnet 4 (thinking)         | -0.06%          | 4.0%         | 4,281     |
| GPT‑5 Nano (thinking, medium)      | -0.12%          | 5.0%         | 4,380     |
| Gemini 2.5 Flash (thinking)[^2]    | -0.43%          | 6.0%         | 4,345     |
| Sonoma Sky Alpha (thinking)        | -0.99%          | 8.0%         | 4,323     |
| Gemini 2.5 Pro (thinking)         | -1.46%          | 2.1%         | 4,358     |
| **Claude Opus 4.1 (no thinking)**  | **-1.9%**       | **16%**      | 4,422     |
| Claude Sonnet 4 (no thinking)     | -10.49%         | 36%          | 4,979     |
| GPT-5 (no thinking)                | -20.64%         | 38%          | 4,275     |
| Sonoma Dusk Alpha                  | -23.17%         | 43%          | 4,804     |
| Gemini 2.5 Flash Lite             | -44.55%         | 62%          | 3,877     |
| GPT‑5 Nano (no thinking)           | -51.18%         | 55%          | 5,869     |
| Gemini 2.5 Flash (no thinking)    | -66.6%          | 56%          | 5,825     |
| Gemma3 12B‑IT QAT                  | -87.07%         | 65%          | 6,794     |

Note: ΔEV values are computed relative to the same seeded basic‑strategy baseline on the exact same 2,750 hands.

Key takeaways:
- Six thinking‑enabled models (Claude Sonnet 4, GPT‑5, GPT‑5 Nano, Gemini 2.5 Pro, Gemini 2.5 Flash, Sonoma Sky Alpha) are at basic‑strategy parity (within 95% CI)[^4]; non‑thinking variants trail by ~2–60+ points ΔEV.
- The gap between thinking and non‑thinking versions of the same model can be massive (e.g., Gemini 2.5 Flash improves by ~66 points with thinking).
- Best non‑thinking baseline here is Claude Opus 4.1 (−1.9% ΔEV, 16% mistakes).

### The Capability Threshold Moment

**These results capture a fascinating moment in AI development.** Blackjack basic strategy sits at a capability threshold where today's models need thinking to reach parity, but likely won't require it in the near future. Test‑time compute acts as a temporary bridge—what requires explicit reasoning today will become implicit knowledge tomorrow[^8].

The evidence is striking: six different models achieve near-perfect performance with thinking enabled, while their identical non-thinking counterparts fail dramatically. Gemini 2.5 Flash's 66-point EV swing exemplifies this threshold effect—the same model architecture performs either competently or catastrophically depending solely on whether explicit reasoning is enabled. This suggests we're witnessing a capability boundary where test-time compute multiplies performance precisely because the underlying task difficulty sits at the current frontier of implicit model knowledge.

### The Thinking Breakthrough in Detail

The most striking finding is how thinking transforms the same underlying models. In our results, GPT‑5 (medium reasoning) edges out others by EV with the lowest mistake rate among thinking models, while Claude Sonnet 4 and Gemini 2.5 Flash also deliver near‑basic strategy performance:

#### Claude Sonnet 4: Near‑Perfect Performance
- With Thinking: ΔEV −0.06%, 4.0% mistake rate (4,281 decisions) — matches baseline within noise
- Without Thinking: ΔEV −10.49%, 36% mistake rate (4,979 decisions)  
- Net Impact: ~+10 percentage point ΔEV improvement, 32.1 point mistake reduction

#### Gemini 2.5 Flash: Dramatic Transformation  
- With Thinking: ΔEV −0.43%, 6.0% mistake rate (4,345 decisions)
- Without Thinking: ΔEV −66.6%, 56% mistake rate (5,825 decisions)
- Net Impact: +66.2 percentage point EV gain

This underscores that explicit test‑time reasoning, not just stored knowledge, drives parity with basic strategy.

#### GPT‑5 Nano (Medium Thinking): Near‑Basic Strategy
- ΔEV vs baseline: −0.12%
- Mistake rate: 5.0% over 4,380 decisions; 2,750 hands; full 550‑cell coverage
- Confusion hotspots:
  - hard 13–16 vs dealer 2–3: chooses HIT instead of correct STAND
  - soft 15–17 vs dealer 3–4: over‑DOUBLING where HIT is correct
  - occasional hard 10 vs 10 over‑DOUBLE

Confusion summary: STAND→HIT dominates the errors (row mistake rate ~7.5%), while DOUBLE and SPLIT rows are very accurate (≤2%). The top‑weighted leaks concentrate in failing to stand with stiff hands against weak dealer upcards.

#### What Thinking Fixes
- **Perfect Fundamental Decisions**: A/A and 8/8 splits, standing on 19-21
- **Strategic Consistency**: Fewer random or contradictory actions  
- **Complex Situation Handling**: Better doubling and splitting decisions

#### Remaining Gaps (Even With Thinking)
**Claude Sonnet 4**: Minor over-doubling on soft hands vs weak dealer cards

**Gemini 2.5 Flash**: Over-doubling soft totals, under-doubling soft 19 vs 6

#### Remaining Leaks (Thinking Models)
- GPT‑5 (thinking): Remaining errors are mostly soft over‑doubling (soft 17 vs 3–4; soft 18 vs 2); a small hard outlier is hard 12 vs 4 STAND→HIT. Double/split rows are perfect.
- Claude Sonnet 4 (thinking): Remaining errors are mixed. Some notable hard misses (hard 11 vs A DOUBLE→HIT, hard 8 vs 5/6 HIT→DOUBLE) plus some soft over‑doubling (soft 17/14 vs 3–4).
- Gemini 2.5 Flash (thinking): Dominated by hard leaks (hard 10 vs 10 HIT→DOUBLE; hard 15 vs 2 STAND→HIT) with some soft over‑doubling and a pair 2/2 vs 10 HIT→SPLIT.
- GPT‑5 Nano (thinking): Dominated by hard 13–16 vs dealer 2–3 STAND→HIT; smaller soft issues (e.g., soft 19 vs 6 DOUBLE→STAND).
- Pair handling (A/A, 8/8, 10/10) is consistently correct across all thinking models (first decision).

#### The Imaginary Strategy Card Phenomenon
A particularly interesting pattern emerges from the thinking traces: models frequently consult imaginary "basic strategy charts" or "lookup tables" during their reasoning process. Despite none of them actually having a way to look up anything, this simulated consultation proves remarkably effective at producing correct decisions.

But what happens when thinking is disabled? The results reveal fascinating failure patterns.

## The Counterpoint: How Models Fail Without Thinking

While thinking-enabled models achieve near-perfect performance, their non-thinking counterparts reveal fascinating failure patterns. Each model family exhibits distinct error signatures that reveal their underlying reasoning processes.

One counterpoint worth highlighting is Claude Opus 4.1 (no thinking). Despite lacking deliberate reasoning, it posts the strongest non‑thinking result in our set (ΔEV −1.8%, 16% mistakes). Its errors are not chaotic: confusion concentrates in high‑impact spots like HIT→STAND on hard 15–16 versus 7–A, while splits are essentially perfect (0% row mistakes). This pattern suggests a fairly complete static policy with specific blind spots around marginal HIT vs STAND and some soft over‑doubling, rather than a wholesale strategy failure. It also suggests that non-thinking models more broadly will be able to catch up on this benchmark in a year or so.

### GPT‑5 Nano: A Case Study in Strategic Inconsistency

![GPT‑5 Nano Confusion Matrix](figures/gpt5_nano_nonthinking_confusion.svg)
*GPT‑5 Nano (no thinking) confusion matrix showing high error rates on STAND and DOUBLE rows*

GPT‑5 Nano's performance (ΔEV −51% vs baseline, 55% mistake rate) shows how partial knowledge without strategic coherence leads to disaster. The model demonstrates a paradox: near‑perfect execution of some rules alongside catastrophic violations of others.

**What GPT‑5 Nano got right:**
- **Splitting when correct**: 0% mistake rate when the baseline action is SPLIT (perfect recognition of correct split scenarios)
- **Basic hit/stand on obvious situations**: Reasonable performance on clear‑cut decisions

**Where it went disastrously wrong:**
- **Splitting 10,10 vs dealer 10**: Giving up the second-best hand for two okay hands. In this run, it is the top EV leak, making up ~7.0% of its loss.
- **Hitting hard 17+ vs strong dealers**: A fundamental mistake that it kept making. 
- **Doubling conservatism**: When doubling is profitable, 99% of the time it doesn't double.
- **Standing inconsistency**: 73% mistake rate, often standing when it should hit

This pattern suggests GPT‑5 Nano has memorized some blackjack “rules” (like split A/A and 8/8) but lacks the strategic framework to apply them consistently. The result is worse than random play—systematic errors compound losses. The model’s perfect recognition of correct splits makes its other failures even more puzzling, highlighting how LLMs can exhibit highly uneven competence across related tasks.

### The Gemma3 "Hit Everything" Syndrome

![Gemma3 Confusion Matrix](figures/gemma3_confusion_heatmap.svg)
*Gemma3 confusion matrix showing systematic "hit everything" bias*

Confusion Matrix Analysis:
- **Should STAND → Actually HIT**: 3,497 errors (97% of all STAND situations)
- **Should DOUBLE → Actually HIT**: 576 errors (93.5% of all DOUBLE situations) 
- **Never doubles down**: 0 correct doubles out of 616 opportunities

**Pattern**: Gemma3 has learned "when in doubt, hit" as a default strategy. For blackjack, this is a very poor strategy since standing is frequently the optimal move and generally carries lower risk. This represents a complete strategic failure where the model defaults to the most aggressive action regardless of situation.

### Non‑Thinking vs Thinking Error Patterns

**Gemini 2.5 Flash comparison**:

*Without Thinking*:  
- Chaotic error distribution across all categories  
- 56% overall mistake rate
- Major leaks: splits 10/10 (should STAND); hits hard 17 vs 10 (should STAND)

*With Thinking*:  
- Systematic errors concentrated in edge cases
- 6.0% overall mistake rate  
- Remaining errors: over‑doubling soft and low hard hands in a few spots

**Non‑thinking Gemini 2.5 Flash** shows chaotic error patterns across all decision types, with major leaks including splitting strong pairs (10/10) and over‑doubling already strong hands (hard 19). Unlike Gemma3's systematic bias, this represents inconsistent strategic reasoning.

Note on severity vs frequency: mistake rate alone can be misleading for EV — aggressive wrong actions (e.g., bad doubles or splitting tens) carry higher EV penalties than benign STAND errors, so two models with similar mistake rates can have different ΔEV.

These observations raise important questions: why do models perform so differently? What drives the currently observed thinking advantage?

## The Why: Deeper Analysis

Two lenses help explain the performance gaps we observe: (1) where models sit on the current capability threshold, and (2) the practical drivers—what models know versus what they execute, and how decision complexity maps to compute and errors.

### Scaling Perspective

Basic blackjack sits near a moving capability threshold. Today, general‑purpose models reach basic‑strategy parity with test‑time compute (thinking) but not without it. In the recent past, they struggled even with reasoning. A little in the future, stronger models will match basic strategy even without explicit thinking. Test‑time compute acts as a capability multiplier near thresholds and is most valuable in harder or shifting situations[^8].

### Knowledge vs. Execution

Before running benchmarks, we surveyed models about their blackjack knowledge (see [model_thoughts/](https://github.com/jsnider3/BlackjackBench/tree/main/model_thoughts)). Most stated the right rules and core principles (split A/A and 8/8, never split 10/10, stand on hard 17+), with the greatest variation in doubles. Gemma is the only one with clear errors in its stated strategy, as it suggests doubling down on soft 19–21.

**Key finding: knowledge alone isn’t sufficient.** Even models with solid theoretical understanding failed dramatically without thinking enabled. This contrasts with skilled human players, who execute basic strategy automatically because they’ve memorized it.

### The Computational Cost of Strategy: A Decision Complexity Hierarchy

Thinking tokens per decision reveal a consistent complexity hierarchy:

- **Trivial (150–200 tokens)**: A/A split; soft 20 stand
- **Simple (200–500)**: Hard 17–21 stands; hard 7–10 vs weak dealers
- **Complex (500–1,000)**: Hard 13–16 vs dealer 2–3
- **Difficult (1,000–1,500)**: Soft hands vs specific upcards (e.g., soft 17 vs 3)
- **Expert‑level (1,500+)**: Pair 9/9 vs 8 (max 8,191 tokens); soft 18 edge cases

**Key insight**: A ~48× gap between the easiest and hardest decisions shows blackjack isn’t uniformly difficult—compute cost and error rates rise together in the hard tiers.

![Hard Totals Thinking Load](figures/thinking_hard_grid.svg)
*Hard totals grid: rows = hard total, cols = dealer 2–10,A — Model: GPT‑5 Nano (medium thinking)*

![Soft Totals Thinking Load](figures/thinking_soft_grid.svg)
*Soft totals grid: rows = soft total, cols = dealer 2–10,A — Model: GPT‑5 Nano (medium thinking)*

![Pairs Thinking Load](figures/thinking_pairs_grid.svg)
*Pairs grid: rows = pairs A/A..10/10, cols = dealer 2–10,A — Model: GPT‑5 Nano (medium thinking)*

Taken together, scaling, knowledge‑execution gaps, and the complexity hierarchy explain why explicit thinking flips outcomes today. They also set up the economic question we answer in the conclusion: when is on‑demand reasoning worth its cost?

## Conclusion: The Thinking Revolution

BlackjackBench reveals a fundamental shift in how AI models perform at capability thresholds. The dramatic transformation between thinking and non‑thinking modes—exemplified by Gemini 2.5 Flash's leap from −66.6% to −0.43% ΔEV—demonstrates that explicit reasoning doesn't just improve performance, it flips outcomes entirely.

### What We Learned About Blackjack Performance

The benchmark establishes three key findings specific to blackjack strategy:

**Capability threshold effects**: Multiple thinking‑enabled models (GPT‑5, Claude Sonnet 4, GPT‑5 Nano, Gemini 2.5 Flash) achieve basic‑strategy parity, while their non‑thinking counterparts trail by 10‑66 percentage points. This suggests basic blackjack sits precisely at today's reasoning capability boundary.

**Knowledge‑execution gaps**: Models often understand strategy when asked directly yet fail to execute consistently without thinking scaffolds. Even perfect knowledge of rules like "split A/A" doesn't guarantee consistent application across related decisions.

**Economic considerations**: For blackjack specifically, reasoning costs ($0.0002–$0.0044 per decision) exceed the value since lookup tables solve the game perfectly[^9]. However, this cost analysis reveals precisely why blackjack makes an ideal benchmark—it provides a controlled environment to measure reasoning capabilities without the practical utility obscuring the scientific insights. The benchmark's true value lies in understanding when and how AI reasoning transforms performance at capability thresholds, insights that directly apply to domains where lookup tables don't exist and reasoning costs are justified by decision stakes.

### The Broader Implications

This research captures something more significant than blackjack performance—it demonstrates how test‑time compute transforms AI capabilities at critical thresholds. The patterns we observe suggest profound implications for reasoning tasks beyond games.

**The knowledge‑execution bridge**: If models struggle to consistently apply known strategies without explicit reasoning in a constrained domain like blackjack, the gap between understanding and reliable execution in complex real‑world scenarios becomes even more critical to address.

**When reasoning economics favor thinking**: Unlike blackjack's solved lookup tables, most real‑world decisions involve novel situations, changing conditions, and high stakes where reasoning costs pale beside potential impact. Business strategy, investment decisions, and major life choices represent domains where thinking‑enabled models offer transformative value.

**A glimpse of the future**: Today's thinking‑enabled performance hints at tomorrow's implicit capabilities. The 66‑point EV swings we observe in blackjack suggest that as reasoning becomes more sophisticated and more capabilities are distilled into the models, the advantages for complex, open‑ended problems will be even more dramatic.

**The bottom line**: We're witnessing the early stages of a capability transition from AI systems that know the right answer to systems that can reliably find and execute it under pressure. For high‑stakes decisions where consistent strategic reasoning matters, the economics strongly favor the most capable thinking‑enabled models available.

### Future Research Directions

This work opens several promising avenues for further investigation:

**Reasoning analysis**: Deep analysis of thinking traces to understand what specific reasoning patterns drive success versus failure, and how these patterns vary across model architectures.

**Rule variant testing**: Exploring how models perform under different blackjack rule sets, where "basic strategy mistakes" under standard rules might actually be optimal adaptations to modified conditions.

**Strategic consistency**: Comparing models' stated strategic knowledge (when directly asked) versus actual play patterns to better understand the knowledge-execution gap.

**Broader game domains**: Extending beyond blackjack to other games with well-defined optimal strategies (poker, chess tactics) to test generalizability of threshold effects.

**Longitudinal capability tracking**: As models improve, monitoring how the thinking advantage evolves and eventually disappears as capabilities become implicit.

---

## Footnotes

[^1]: **Expected Value Methodology**: The +2.6% EV for Basic Strategy represents the empirical result from the specific 2,750 hands tested, not the theoretical house edge (~-0.5% under standard rules). This sample-specific baseline ensures fair comparison since all models play identical hands with identical random seeds. The positive EV indicates this particular sample was player-favorable, which is within normal variance for blackjack.

[^2]: “Thinking” denotes Chain‑of‑Thought style test‑time reasoning: models generate intermediate reasoning before outputting a single action token. See the LLM Integration section (“What is ‘thinking’?”) for the exact prompt and provider settings. Background on CoT: Wei et al., 2022 (Chain‑of‑Thought Prompting), Kojima et al., 2022 (Zero‑Shot Reasoners), Wang et al., 2022 (Self‑Consistency).

[^3]: **Model specifications**: Exact model identifiers used: Claude Sonnet 4 (`claude-sonnet-4-20250514`), Claude Opus 4.1 (`claude-opus-4-1-20250805`), GPT‑5 (`gpt-5`), Gemini 2.5 Flash (`gemini-2.5-flash`), Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`), Gemini 2.5 Pro (`gemini-2.5-pro`). Sonoma Sky Alpha and Sonoma Dusk Alpha are stealth models hosted on OpenRouter that are strongly suspected to be Grok 4 variants. See, for example: https://manifold.markets/iwakura/who-is-behind-the-sonoma-cloaked-mo

[^4]: **Statistical Confidence**: Wide 95% confidence intervals (e.g., [-4.2%, +5.8%]) reflect the inherent variance in blackjack outcomes. Results are based on 5 repetitions of the 550-cell policy grid (2,750 total hands per model). Significantly more repetitions would be required to achieve tighter confidence bounds for distinguishing top-tier models.

[^5]: **Illegal Move Handling**: The legality guard was rarely triggered across all models tested, with most showing zero illegal attempts. When illegal moves occurred, they were logged and handled by a deliberately bad fallback policy ("BadAgent") that chooses intentionally poor but legal actions (e.g., doubling whenever possible, splitting tens) to penalize rule violations while allowing benchmark continuation. Implementation: [blackjack_bench/agents/guarded.py](https://github.com/jsnider3/BlackjackBench/blob/main/blackjack_bench/agents/guarded.py), [blackjack_bench/agents/bad_agent.py](https://github.com/jsnider3/BlackjackBench/blob/main/blackjack_bench/agents/bad_agent.py), with logging and reporting in [blackjack_bench/eval.py](https://github.com/jsnider3/BlackjackBench/blob/main/blackjack_bench/eval.py) and [blackjack_bench/cli_helpers.py](https://github.com/jsnider3/BlackjackBench/blob/main/blackjack_bench/cli_helpers.py).

[^6]: Six-deck H17 DAS chart used for the baseline policy: https://www.blackjackapprenticeship.com/wp-content/uploads/2024/09/H17-Basic-Strategy.pdf

[^7]: Player two‑card categories are unordered (e.g., A,2 ≡ 2,A), which is why P(A,2) is multiplied by 2 in the example. Under the independence/infinite‑deck approximation, weights across all 550 cells sum to 1.0. Implementation: [blackjack_bench/weights.py::grid_weights_infinite_deck](https://github.com/jsnider3/BlackjackBench/blob/main/blackjack_bench/weights.py).

[^8]: **Test‑time compute for reasoning**: Increasing test‑time sampling/search typically improves reasoning accuracy. See Yao et al., 2023 ("Tree of Thoughts: Deliberate Problem Solving with Large Language Models"; arXiv:2305.10601) and Wang et al., 2022 (Self‑Consistency) for methods that trade additional inference compute for better results.

[^9]: **Reasoning cost methodology**: Costs computed by multiplying observed tokens per decision (prompt + completion, including thinking traces) by provider rates per 1K tokens. Pricing sources: OpenAI API pricing (https://openai.com/api/pricing), Anthropic pricing (https://www.anthropic.com/pricing), and Google Gemini pricing (https://ai.google.dev/pricing or https://cloud.google.com/vertex-ai/pricing#gemini). Normalization: identical accounting across providers; provider‑specific rounding and tiering ignored.

[^10]: **Card counting outperforms basic strategy**: With favorable rules and sufficient penetration, card counting can yield positive player EV, exceeding fixed basic strategy. See Wizard of Odds: https://wizardofodds.com/games/blackjack/card-counting/

## Appendix: Detailed Error Analysis and Repro

Below are detailed per‑model confusion matrices (policy‑grid; decision‑level) and top weighted mistakes (first decision only, weighted by natural frequency). These tables correspond to the baselines referenced in the main text.

### How to Run (Reproducible Examples)
- Policy‑grid weighted (basic):
  - `python -m blackjack_bench.cli run --agent basic --track policy-grid --weighted --reps 100 --seed 7`
- LLM example (Gemini API with thinking):
  - `python -m blackjack_bench.cli run --agent llm --guard --llm-provider gemini --llm-model gemini-2.5-flash --reasoning medium --track policy-grid --weighted --reps 5 --seed 7`
- LLM example (Anthropic Claude with thinking):
  - `python -m blackjack_bench.cli run --agent llm --guard --llm-provider anthropic --llm-model claude-sonnet-4-20250514 --reasoning medium --track policy-grid --weighted --reps 5 --seed 7`
- Inspect confusion (baseline vs agent):
  - `python tools/summarize_confusion.py --track policy-grid logs/<timestamp>_policy-grid_<agent>_<model>.jsonl --csv confusion.csv`

### Gemma3 12B‑IT QAT: Complete Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT | 2011 | 20 | 0 | 122 | 2153 | 0.066 |
| STAND | 3497 | 91 | 0 | 20 | 3608 | 0.975 |
| DOUBLE | 576 | 0 | 0 | 40 | 616 | 1.000 |
| SPLIT | 5 | 0 | 0 | 252 | 257 | 0.019 |
| total | 6089 | 111 | 0 | 434 | 6634 | 0.645 |

Top Weighted Mistakes (First Decision)

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

### Gemini 2.5 Flash (Non‑Thinking): Chaotic Errors

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1851 | 52  | 62  | 122 | 2087 | 0.113 |
| STAND | 2084 | 310 | 444 | 25  | 2863 | 0.892 |
| DOUBLE| 398  | 12  | 170 | 38  | 618  | 0.725 |
| SPLIT | 0    | 0   | 0   | 257 | 257  | 0.000 |
| total | 4333 | 374 | 676 | 442 | 5825 | 0.556 |

Top EV Leaks (First Decision; Weighted by Natural Frequency)

| Category | Dealer | Baseline | Agent | Count | Weighted EV Loss | Share |
|---|:---:|:---:|:---:|---:|---:|---:|
| pair 10/10 | 10 | STAND | SPLIT | 5 | 0.1457 | 7.68% |
| hard 11 | 10 | DOUBLE | HIT | 20 | 0.0728 | 3.84% |
| hard 17 | 10 | STAND | HIT | 10 | 0.0619 | 3.26% |
| hard 18 | 10 | STAND | HIT | 5 | 0.0583 | 3.07% |
| hard 19 | 2 | STAND | DOUBLE | 5 | 0.0546 | 2.88% |

### Gemini 2.5 Flash (Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1585 | 49  | 62  | 20  | 1716 | 0.076 |
| STAND | 113  | 1681| 0   | 0   | 1794 | 0.063 |
| DOUBLE| 7    | 7   | 564 | 0   | 578  | 0.024 |
| SPLIT | 4    | 0   | 0   | 253 | 257  | 0.016 |
| total | 1709 | 1737| 626 | 273 | 4345 | 0.060 |

Top Leaks (First Decision; Weighted by Natural Frequency)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 10 | 10 | HIT | DOUBLE | 12 | 31.89% |
| pair 5/5 | 10 | HIT | DOUBLE | 5 | 6.64% |
| hard 15 | 2  | STAND | HIT | 9 | 5.98% |
| pair 2/2 | 10 | HIT | SPLIT | 3 | 3.99% |
| soft 14 | 4  | HIT | DOUBLE | 5 | 3.32% |

### Claude Sonnet 4 (Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1591 | 53  | 63  | 6  | 1713 | 0.071 |
| STAND | 15   | 1718| 1   | 4  | 1738 | 0.012 |
| DOUBLE| 15   | 6   | 552 | 0  | 573  | 0.037 |
| SPLIT | 6    | 0   | 4   | 247| 257  | 0.039 |
| total | 1627 | 1777| 620 | 257| 4281 | 0.040 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 11 | A  | DOUBLE | HIT    | 8  | 6.30% |
| hard 10 | 10 | HIT    | DOUBLE | 2  | 6.30% |
| soft 14 | 3  | HIT    | DOUBLE | 5  | 3.94% |
| soft 17 | 3  | HIT    | DOUBLE | 5  | 3.94% |

### Claude Sonnet 4 (No Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1443 | 125 | 273 | 117 | 1958 | 0.263 |
| STAND | 706  | 1204| 237 | 5   | 2152 | 0.441 |
| DOUBLE| 287  | 5   | 280 | 0   | 612  | 0.542 |
| SPLIT | 0    | 0   | 0   | 257 | 257  | 0.000 |
| total | 2436 | 1334| 790 | 419 | 4979 | 0.361 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 11 | 10 | DOUBLE | HIT    | 20 | 6.87% |
| hard 12 | 5  | STAND  | DOUBLE | 20 | 3.01% |
| hard 13 | 2  | STAND  | HIT    | 20 | 3.01% |

### Claude Opus 4.1 (No Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1375 | 208 | 160 | 55  | 1798 | 0.235 |
| STAND | 194  | 1537| 36  | 5   | 1772 | 0.133 |
| DOUBLE| 58   | 5   | 532 | 0   | 595  | 0.106 |
| SPLIT | 0    | 0   | 0   | 257 | 257  | 0.000 |
| total | 1627 | 1750| 728 | 317 | 4422 | 0.163 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 15 | 10 | HIT | STAND | 10 | 27.87% |
| hard 16 | 9  | HIT | STAND | 10 | 16.72% |
| hard 15 | 7  | HIT | STAND | 11 | 12.54% |
| hard 12 | 2  | HIT | STAND | 5  | 5.57%  |
| hard 5  | 5  | HIT | DOUBLE| 5  | 3.48%  |

### GPT‑5 (Medium Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1685 | 2   | 28  | 1   | 1716 | 0.018 |
| STAND | 12   | 1774| 7   | 0   | 1793 | 0.011 |
| DOUBLE| 0    | 0   | 575 | 0   | 575  | 0.000 |
| SPLIT | 0    | 0   | 0   | 257 | 257  | 0.000 |
| total | 1697 | 1776| 610 | 258 | 4341 | 0.012 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 12 | 4 | STAND  | HIT    | 3 | 24.74% |
| soft 18 | 2 | STAND  | DOUBLE | 5 | 10.31% |
| soft 17 | 3 | HIT    | DOUBLE | 5 | 10.31% |

### GPT‑5 (No Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1084 | 160 | 425 | 93  | 1762 | 0.385 |
| STAND | 466  | 825 | 348 | 15  | 1654 | 0.501 |
| DOUBLE| 90   | 30  | 482 | 0   | 602  | 0.199 |
| SPLIT | 2    | 0   | 5   | 250 | 257  | 0.027 |
| total | 1642 | 1015| 1260| 358 | 4275 | 0.382 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 15 | 10 | HIT    | DOUBLE | 4  | 3.92% |
| hard 11 | 10 | DOUBLE | HIT    | 12 | 2.94% |
| hard 13 | 6  | STAND  | DOUBLE | 20 | 2.14% |

### GPT‑5 Nano (Medium Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1652 | 9   | 51  | 9   | 1721 | 0.040 |
| STAND | 134  | 1690| 2   | 1   | 1827 | 0.075 |
| DOUBLE| 1    | 7   | 567 | 0   | 575  | 0.014 |
| SPLIT | 3    | 2   | 0   | 252 | 257  | 0.019 |
| total | 1790 | 1708| 620 | 262 | 4380 | 0.050 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 15 | 2 | STAND  | HIT    | 11 | 11.44% |
| hard 13 | 2 | STAND  | HIT    | 13 | 10.95% |
| hard 16 | 2 | STAND  | HIT    | 5  | 8.46% |

### GPT‑5 Nano (No Thinking): Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1586 | 298 | 20  | 116 | 2020 | 0.215 |
| STAND | 2105 | 814 | 21  | 37  | 2977 | 0.727 |
| DOUBLE| 479  | 94  | 7   | 35  | 615  | 0.989 |
| SPLIT | 0    | 0   | 0   | 257 | 257  | 0.000 |
| total | 4170 | 1206| 48  | 445 | 5869 | 0.546 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| pair 10/10 | 10 | STAND | SPLIT  | 5  | 7.0% |
| hard 17    | 10 | STAND | HIT    | 7  | 3.3% |
| hard 11    | 10 | DOUBLE| HIT    | 16 | 2.8% |

### Gemini 2.5 Pro: Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1687 | 8   | 24  | 2   | 1721 | 0.020 |
| STAND | 40   | 1754| 11  | 1   | 1806 | 0.029 |
| DOUBLE| 2    | 1  | 571 | 0   | 574  | 0.005 |
| SPLIT | 0    | 1  | 0   | 256 | 257  | 0.004 |
| total | 1729 | 1764| 606 | 259 | 4358 | 0.021 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 15 | 2 | STAND  | HIT    | 4 | 16% |
| hard 14 | 2 | STAND  | HIT    | 2 | 13% |
| soft 17 | 3 | HIT    | DOUBLE | 5 | 7.9% |

### Gemini 2.5 Flash Lite: Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 529  | 69  | 884 | 117 | 1599 | 0.669 |
| STAND | 331  | 177 | 889 | 15  | 1412 | 0.875 |
| DOUBLE| 81   | 0   | 528 | 0   | 609  | 0.133 |
| SPLIT | 0    | 0   | 0   | 257 | 257  | 0.000 |
| total | 941  | 246 | 2301| 389 | 3877 | 0.615 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Count | Weighted EV Loss | Share |
|---|:---:|:---:|:---:|---:|---:|---:|
| hard 18 | 10 | STAND | DOUBLE | 5 | 0.1311 | 6.18% |
| hard 19 | 10 | STAND | DOUBLE | 5 | 0.1311 | 6.18% |
| pair 10/10 | 5 | STAND | DOUBLE | 5 | 0.0947 | 4.47% |
| hard 19 | 2 | STAND | DOUBLE | 5 | 0.0546 | 2.58% |
| hard 16 | 4 | STAND | DOUBLE | 10 | 0.0482 | 2.28% |

### Sonoma Sky Alpha: Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1543 | 70  | 76  | 21  | 1710 | 0.098 |
| STAND | 141  | 1629| 0   | 2   | 1772 | 0.081 |
| DOUBLE| 6    | 22  | 557 | 0   | 585  | 0.048 |
| SPLIT | 0    | 6   | 0   | 250 | 256  | 0.023 |
| total | 1690 | 1727| 633 | 273 | 4323 | 0.080 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Mistakes | Weighted Share |
|---|:---:|:---:|:---:|---:|---:|
| hard 10 | 10 | HIT   | DOUBLE | 12 | 15.41% |
| hard 14 | 2  | STAND | HIT    | 10 | 7.06%  |
| hard 12 | 2  | HIT   | STAND  | 12 | 6.74%  |
| hard 15 | 3  | STAND | HIT    | 8  | 5.46%  |
| hard 12 | 3  | HIT   | STAND  | 6  | 3.85%  |
| hard 13 | 2  | STAND | HIT    | 6  | 3.85%  |
| hard 15 | 2  | STAND | HIT    | 7  | 3.21%  |
| hard 16 | 2  | STAND | HIT    | 4  | 3.21%  |
| hard 16 | 6  | STAND | HIT    | 4  | 3.21%  |
| hard 14 | 3  | STAND | HIT    | 5  | 2.57%  |
| hard 16 | 3  | STAND | HIT    | 5  | 2.57%  |
| hard 13 | 3  | STAND | HIT    | 2  | 2.57%  |
| hard 15 | 6  | STAND | HIT    | 4  | 2.25%  |
| soft 13 | 4  | HIT   | DOUBLE | 5  | 1.61%  |
| soft 15 | 4  | HIT   | DOUBLE | 5  | 1.61%  |

### Sonoma Dusk Alpha: Detailed Breakdown

Confusion Matrix (Policy‑Grid)

| baseline\\agent | HIT | STAND | DOUBLE | SPLIT | row_total | row_mistake_rate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIT   | 1107 | 205 | 406 | 122 | 1840 | 0.398 |
| STAND | 713  | 1033| 166 | 18  | 1930 | 0.465 |
| DOUBLE| 266  | 44  | 267 | 40  | 617  | 0.567 |
| SPLIT | 0    | 5   | 0   | 252 | 257  | 0.019 |
| total | 2086 | 1287| 839 | 432 | 4644 | 0.427 |

Top Weighted Mistakes (First Decision)

| Category | Dealer | Baseline | Agent | Count | Weighted EV Loss | Share |
|---|:---:|:---:|:---:|---:|---:|---:|
| hard 12 | 10 | HIT | STAND | 6 | 0.0874 | 10.86% |
| hard 11 | 10 | DOUBLE | HIT | 17 | 0.0546 | 6.79% |
| soft 17 | 10 | HIT | DOUBLE | 5 | 0.0218 | 2.71% |
| hard 11 | 3  | DOUBLE | HIT | 15 | 0.0191 | 2.38% |
| pair 4/4 | 10 | HIT | SPLIT | 5 | 0.0182 | 2.26% |

---

Use these commands and files to reproduce the tables and figures referenced in this post.

- Per‑model confusion matrices (policy‑grid):
  - `python tools/summarize_confusion.py --track policy-grid --recompute-baseline baselines/20250911_policy-grid_llm_gpt-5-med-thinking.jsonl --csv figures/gpt5_confusion.csv`
  - `python tools/summarize_confusion.py --track policy-grid --recompute-baseline baselines/20250910_policy-grid_llm_claude-sonnet-4-20250514-thinking.jsonl --csv figures/claude_confusion.csv`
  - `python tools/summarize_confusion.py --track policy-grid --recompute-baseline baselines/20250909_policy-grid_llm_gemini-2-5-flash-thinking.jsonl --csv figures/gemini_flash_confusion.csv`
  - `python tools/summarize_confusion.py --track policy-grid --recompute-baseline baselines/20250911_policy-grid_llm_gpt-5-nano-med-thinking.jsonl --csv figures/gpt5_nano_confusion.csv`

- Top weighted leaks (decision_idx==0 only):
  - `python tools/top_leaks.py baselines/20250911_policy-grid_llm_gpt-5-med-thinking.jsonl --top 15`
  - Repeat for each baseline file in `baselines/`.

- Thinking‑load tables and heatmaps:
  - Build per‑cell averages across models:  
    `python tools/aggregate_thinking.py baselines/20250911_policy-grid_llm_gpt-5-med-thinking.jsonl baselines/20250910_policy-grid_llm_claude-sonnet-4-20250514-thinking.jsonl baselines/20250909_policy-grid_llm_gemini-2-5-flash-thinking.jsonl baselines/20250911_policy-grid_llm_gpt-5-nano-med-thinking.jsonl`
  - Generate grids and SVGs:  
    `python tools/build_thinking_charts.py --per-cell figures/thinking_load_by_cell.csv --out-dir figures`
  - Outputs: `figures/thinking_hard_grid.csv/svg`, `figures/thinking_soft_grid.csv/svg`, `figures/thinking_pairs_grid.csv/svg`.

- Logs/baselines used (audit): see JSONL files under `baselines/` and `logs/` referenced in this post.
