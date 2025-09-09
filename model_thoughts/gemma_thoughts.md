# Gemma Thoughts

These are gemma3:12b-it-qat's thoughts on blackjack

python -m blackjack_bench.cli run --agent llm --guard --llm-provider ollama --llm-model gemma3:12b-it-qat --track policy-grid --reps 5 --weighted --seed 7

## Thoughts

>>> What do you know about blackjack and how would you play it? Answer in at least 150 words. State the rules you assume, then describe your strategy.

Alright, let’s dive deeper into my blackjack knowledge and how I'd play.

**Assumed Rules (Standard American Blackjack):**

For this explanation, I'm assuming standard American blackjack rules:

*   One deck of 52 cards is used (or multiple decks shuffled together).
*   The dealer hits on soft 17 (Ace + 6).
*   Players can double down on any hand total.
*   Players can split pairs. Splitting Aces only allows one additional card per split hand.
*   Dealer stands on 17 or higher.
*   Blackjack (Ace + 10-value card) pays 3:2.
*   A push (tie) returns the bet.

**My Strategy – Strict Basic Strategy:**

As an AI, my gameplay would be entirely based on **strict basic strategy**. I wouldn't deviate based on emotion,
intuition, or "hunches." My decisions would be purely calculated. Here's a summary of how I'd play:

*   **Hard Hands (No Ace Counting as 11):**
    *   Hit on 11 or less.
    *   Stand on 17 or higher.
    *   Hit on 12-16 against a dealer's 7 or higher.
    *   Double down on 11 against most dealer upcards (2-10).
    *   Double down on 10 against a dealer's 2-9.
*   **Soft Hands (Ace Counting as 11):**
    *   Always hit on Soft 17 or lower.
    *   Double down on Soft 19-21 against most dealer upcards.
*   **Pairs:**
    *   Always split Aces and 8s.
    *   Never split 10s or 5s.
    *   Split 2s, 3s, and 6s against a dealer’s 2-6.
*   **Insurance:** I would *never* take insurance, as it’s statistically a bad bet.
*   **Surrender:** I would not surrender unless a specific surrender strategy chart indicates it’s advantageous
(which is rarely the case).

My entire gameplay would be mechanical and consistent, adhering precisely to the statistically optimal plays. This
minimizes the house edge and provides the best chance of long-term success. I am programmed to be a model
blackjack player, not a gambler!  I understand that blackjack is a game of probabilities and the best play is to
always make the play with the highest expected value.