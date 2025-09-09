# Sonoma Dusk Alpha Thoughts

These are Sonoma Dusk Alpha's thoughts on blackjack

Command to run the test is probably:

python -m blackjack_bench.cli run --agent llm --guard --llm-provider openrouter --llm-model openrouter/sonoma-dusk-alpha --track policy-grid --reps 5 --weighted --seed 7

## Thoughts

>>> What do you know about blackjack and how would you play it? Answer in at least 150 words. State the rules you assume, then describe your strategy.

Assumed Rules of Blackjack
Blackjack, also known as 21, is a casino card game played with one or more standard 52-card decks (typically 6-8 decks shuffled together). The objective is to beat the dealer by having a hand value closer to 21 without exceeding it. Card values are: numbered cards 2-10 worth their face value, face cards (J, Q, K) worth 10, and Aces worth 1 or 11 (player's choice for best total). Aces and 10-value cards are key for "blackjacks," which pay 3:2.

Basic rules I assume:

Dealing: Each player and the dealer get two cards. Players' cards are face-up; dealer's upcard is face-up, hole card face-down.
Player actions: On your turn, you can hit (take another card), stand (keep your hand), double down (double bet and take one more card), split (if initial cards are a pair, split into two hands and add a bet to the second), or surrender (forfeit half bet, if allowed—I'll assume it's not for simplicity).
Dealer rules: Dealer must hit on 16 or less and stand on 17 or more (including soft 17, unless house rules specify otherwise; I assume hit on soft 17 for a standard Vegas-style game).
Winning: If your hand > dealer's without busting (over 21), you win even money (1:1 payout). Blackjack (Ace + 10-value card) pays 3:2. Push if totals match. Dealer wins if you bust or their hand beats yours. No betting side bets like insurance unless specified.
Game flow: Played at a table with a $5-100 minimum bet, up to 7 players. House edge is about 0.5% with optimal play.
These are standard rules from common casino variants like those in Las Vegas; variations exist (e.g., European no-hole-card rule), but this setup is widely used.

My Strategy for Playing Blackjack
As an AI, I don't gamble with real money, but if simulating or advising, I'd use basic strategy to minimize the house edge—essentially a mathematically derived decision tree based on your hand total, dealer's upcard, and deck rules. This isn't card counting (which requires tracking high/low cards and is impractical for casual play, plus often frowned upon in casinos), but a fixed chart of optimal moves derived from computer simulations of billions of hands.

Here's how I'd play step-by-step, assuming infinite decks and the rules above (no surrender):

Initial Hand Evaluation:

If I get a blackjack (Ace + 10/J/Q/K), I stand and collect the 3:2 payout—game over for that hand.
For pairs: Always split Aces (they can make strong hands) and 8s (to avoid a weak 16). Split 2s/3s/6s/7s if dealer's upcard is 2-7; never split 10s (20 is strong) or 5s (treat as 10). Split 9s if dealer shows 2-6, 8, or 9; stand otherwise. For 4s, split only if dealer shows 5-6 and doubling after split is allowed.
Hard Hands (No Ace or Ace as 1):

8 or less: Always hit—too weak.
9: Double down if dealer shows 3-6 (good odds); else hit.
10: Double if dealer 2-9; hit if 10/A.
11: Double if dealer 2-10; hit if Ace.
12: Hit if dealer 2-3; stand if 4-6; hit if 7-A.
13-16: Stand if dealer 2-6 (their bust chance high); hit if 7-A.
17+: Always stand—strong enough.
Soft Hands (Ace + non-10 card, Ace as 11):

Soft 13-14 (A2/A3): Hit if dealer 5-6? No—double if 5-6, else hit.
Soft 15-16 (A4/A5): Double if 4-6; hit otherwise.
Soft 17 (A6): Double if 3-6; else hit.
Soft 18 (A7): Double if 2-6; stand if 7-8; hit if 9-10/A.
Soft 19+ (A8+): Always stand.
General Tips in Play:

Bet flat (same amount each hand) to manage bankroll—e.g., 1-2% of total per hand to survive variance.
Never take insurance (it's a sucker bet with ~7% house edge).
If doubling, only do so with a hand likely to improve without busting much.
Track the table: Avoid if dealer upcard is strong (10/A), as house edge rises.
This strategy reduces the house edge to under 0.5%, far better than gut feelings (which can push it to 2-5%). In practice, I'd memorize or reference a basic strategy chart. For fun, I'd play conservatively, enjoying the math over chasing losses—blackjack's thrill is in the probabilities, not luck alone. (Word count: 728)
