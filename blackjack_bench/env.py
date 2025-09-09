from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

from .cards import Card, Shoe, hand_totals
from .rules import Rules
from .types import Action, Observation, HandView


def hilo_delta(card: Card) -> int:
    if card.rank in ("2", "3", "4", "5", "6"):
        return 1
    if card.rank in ("10", "J", "Q", "K", "A"):
        return -1
    return 0


@dataclass
class HandState:
    cards: List[Card]
    bet: int = 1
    is_doubled: bool = False
    is_split_aces: bool = False


class BlackjackEnv:
    def __init__(self, rules: Optional[Rules] = None, seed: Optional[int] = None, expose_count: bool = True, illegal_policy: str = "error"):
        self.rules = rules or Rules()
        self.shoe = Shoe(self.rules.num_decks, seed=seed)
        self.running_count = 0
        self.hands: List[HandState] = []
        self.active_index = 0
        self.dealer_cards: List[Card] = []
        self.expose_count = expose_count
        # illegal_policy: 'error' to raise on illegal actions, 'hit' to treat as HIT
        self.illegal_policy = illegal_policy

    def _draw(self) -> Card:
        c = self.shoe.draw()
        self.running_count += hilo_delta(c)
        return c

    def _take_from_shoe(self, want_rank: str) -> Card:
        # Prefer exact rank; if wanting '10' but none left, allow any 10-value rank
        # Search from end to align with pop() behavior
        idx = None
        for i in range(len(self.shoe._cards) - 1, -1, -1):
            c = self.shoe._cards[i]
            if c.rank == want_rank:
                idx = i
                break
        if idx is None and want_rank == "10":
            for i in range(len(self.shoe._cards) - 1, -1, -1):
                c = self.shoe._cards[i]
                if c.rank in ("10", "J", "Q", "K"):
                    idx = i
                    break
        if idx is None:
            raise RuntimeError(f"Card of rank {want_rank} not available in shoe")
        card = self.shoe._cards.pop(idx)
        return card

    # API: one episode = one round/hand (including possible splits)
    # Optional forced start: dict with keys 'p1','p2','du' ranks (e.g., 'A','2','10')
    def play_hand(self, agent, bet: int = 1, start: Optional[Dict[str, str]] = None) -> Tuple[float, Dict]:
        self.hands = []
        self.active_index = 0
        self.dealer_cards = []
        if start is None:
            self.hands = [HandState(cards=[self._draw(), self._draw()], bet=bet)]
            self.dealer_cards = [self._draw(), self._draw()]
        else:
            # normalize T->'10'
            def norm(r: str) -> str:
                return "10" if r in ("T", "t") else r

            p1 = self._take_from_shoe(norm(start["p1"]))
            p2 = self._take_from_shoe(norm(start["p2"]))
            du = self._take_from_shoe(norm(start["du"]))
            # update running count for visible cards as if drawn
            self.running_count += hilo_delta(p1)
            self.running_count += hilo_delta(p2)
            self.running_count += hilo_delta(du)
            self.hands = [HandState(cards=[p1, p2], bet=bet)]
            self.dealer_cards = [du, self._draw()]

        # Natural blackjacks
        player_total, _ = hand_totals(self.hands[0].cards)
        dealer_total, _ = hand_totals(self.dealer_cards)
        player_blackjack = player_total == 21 and len(self.hands[0].cards) == 2
        dealer_blackjack = dealer_total == 21 and len(self.dealer_cards) == 2
        trace: Dict = {"decisions": []}

        if player_blackjack or dealer_blackjack:
            reward: float = 0.0
            outcomes: List[str] = []
            outcome_labels: List[str] = []
            if player_blackjack and dealer_blackjack:
                reward = 0.0
                outcomes = ["both_blackjack_push"]
                outcome_labels = ["Both blackjack (push)"]
            elif player_blackjack:
                reward = self.rules.blackjack_payout * bet
                outcomes = ["player_blackjack"]
                outcome_labels = ["Player blackjack"]
            else:
                reward = -float(bet)
                outcomes = ["dealer_blackjack"]
                outcome_labels = ["Dealer blackjack"]
            result_txt = "win" if reward > 0 else ("loss" if reward < 0 else "push")
            result_detail = "Player wins" if reward > 0 else ("Player loses" if reward < 0 else "Push")
            return reward, self._summary(
                trace,
                extra={
                    "outcomes": outcomes,
                    "outcome_labels": outcome_labels,
                    "result": result_txt,
                    "result_detail": result_detail,
                },
            )

        # Player actions for each hand (in order); allow dynamic inserts
        i = 0
        while i < len(self.hands):
            self.active_index = i
            while True:
                obs = self._observation()
                meta: Dict = {}
                action = agent.act(obs, info=meta)
                _obsd = {
                    "player": {
                        "cards": obs.player.cards,
                        "total": obs.player.total,
                        "is_soft": obs.player.is_soft,
                        "can_split": obs.player.can_split,
                        "can_double": obs.player.can_double,
                    },
                    "dealer_upcard": obs.dealer_upcard,
                    "hand_index": obs.hand_index,
                    "num_hands": obs.num_hands,
                    "allowed_actions": [a.name for a in obs.allowed_actions],
                }
                if obs.running_count is not None:
                    _obsd["running_count"] = obs.running_count
                if obs.true_count is not None:
                    _obsd["true_count"] = obs.true_count
                trace["decisions"].append({
                    "hand_index": i,
                    "obs": _obsd,
                    "action": action.name,
                    "meta": meta,
                })
                if action == Action.STAND:
                    break
                elif action == Action.HIT:
                    self.hands[i].cards.append(self._draw())
                    total, _ = hand_totals(self.hands[i].cards)
                    if total > 21:
                        break  # bust
                    continue
                elif action == Action.DOUBLE:
                    if not obs.player.can_double:
                        if self.illegal_policy == "hit":
                            self.hands[i].cards.append(self._draw())
                            continue
                        raise ValueError("Illegal DOUBLE attempted")
                    self.hands[i].bet *= 2
                    self.hands[i].is_doubled = True
                    self.hands[i].cards.append(self._draw())
                    break
                elif action == Action.SPLIT:
                    if not obs.player.can_split:
                        if self.illegal_policy == "hit":
                            self.hands[i].cards.append(self._draw())
                            continue
                        raise ValueError("Illegal SPLIT attempted")
                    if len(self.hands) >= self.rules.max_splits:
                        # max hands reached, ignore split
                        self.hands[i].cards.append(self._draw())
                        continue
                    c1 = self.hands[i].cards[0]
                    c2 = self.hands[i].cards[1]
                    # replace current with first
                    first = HandState(cards=[c1, self._draw()], bet=bet)
                    self.hands[i] = first
                    # add second as new hand next
                    split_aces = c1.rank == "A" and c2.rank == "A"
                    new_hand = HandState(cards=[c2, self._draw()], bet=bet, is_split_aces=split_aces)
                    self.hands.insert(i + 1, new_hand)
                    # if split aces with one-card rule, both hands stand after one draw
                    if split_aces and self.rules.split_aces_one_card:
                        break
                    # continue current hand loop after split; allow DAS
                    continue
                elif action == Action.SURRENDER:
                    if not self.rules.surrender_allowed:
                        if self.illegal_policy == "hit":
                            self.hands[i].cards.append(self._draw())
                            continue
                        raise ValueError("Illegal SURRENDER attempted")
                    # late surrender: give up and move to next hand
                    break
                else:
                    break
            i += 1

        # Dealer plays
        self._dealer_play()

        # Settle
        reward: float = 0.0
        outcomes: List[str] = []
        outcome_labels: List[str] = []
        dealer_total, _ = hand_totals(self.dealer_cards)
        for h in self.hands:
            total, _ = hand_totals(h.cards)
            if total > 21:
                reward -= float(h.bet)
                outcomes.append("player_bust")
                outcome_labels.append("Player busts")
            else:
                if dealer_total > 21 or total > dealer_total:
                    reward += float(h.bet)
                    if dealer_total > 21:
                        outcomes.append("dealer_bust")
                        outcome_labels.append("Dealer busts")
                    else:
                        outcomes.append("player_win")
                        outcome_labels.append("Player wins")
                elif total < dealer_total:
                    reward -= float(h.bet)
                    outcomes.append("player_lose")
                    outcome_labels.append("Player loses")
                else:
                    reward += 0.0
                    outcomes.append("push")
                    outcome_labels.append("Push")

        result_txt = "win" if reward > 0 else ("loss" if reward < 0 else "push")
        result_detail = "Player wins" if reward > 0 else ("Player loses" if reward < 0 else "Push")
        return reward, self._summary(
            trace,
            extra={
                "outcomes": outcomes,
                "outcome_labels": outcome_labels,
                "result": result_txt,
                "result_detail": result_detail,
            },
        )

    def _dealer_play(self):
        # reveal dealer hole card is already included; play to rule
        while True:
            total, is_soft = hand_totals(self.dealer_cards)
            if total > 21:
                return
            if self.rules.hit_soft_17:
                # hit on soft 17
                if total < 17 or (total == 17 and is_soft):
                    self.dealer_cards.append(self._draw())
                    continue
                else:
                    return
            else:
                if total < 17:
                    self.dealer_cards.append(self._draw())
                    continue
                else:
                    return

    def _observation(self) -> Observation:
        hand = self.hands[self.active_index]
        total, is_soft = hand_totals(hand.cards)
        dealer_up = self.dealer_cards[0]
        allowed = [Action.STAND, Action.HIT]
        if len(hand.cards) == 2 and self.rules.double_allowed and (not hand.is_split_aces or self.rules.double_after_split):
            allowed.append(Action.DOUBLE)
        # split if exactly two cards of same rank and below max
        if len(hand.cards) == 2:
            r0, r1 = hand.cards[0].rank, hand.cards[1].rank
            same_rank = (r0 == r1) or (r0 in ("10", "J", "Q", "K") and r1 in ("10", "J", "Q", "K"))
            if same_rank and len(self.hands) < self.rules.max_splits:
                if r0 == "A" and not self.rules.resplit_aces and hand.is_split_aces:
                    pass
                else:
                    allowed.append(Action.SPLIT)
        if self.rules.surrender_allowed and len(hand.cards) == 2:
            allowed.append(Action.SURRENDER)
        hv = HandView(
            cards=[c.label() for c in hand.cards],
            total=total,
            is_soft=is_soft,
            can_split=Action.SPLIT in allowed,
            can_double=Action.DOUBLE in allowed,
        )
        true_count = None
        if self.expose_count and self.shoe.remaining() > 0:
            decks_remaining = max(self.shoe.remaining() / 52.0, 0.25)
            true_count = self.running_count / decks_remaining
        return Observation(
            player=hv,
            dealer_upcard=dealer_up.label(),
            hand_index=self.active_index,
            num_hands=len(self.hands),
            allowed_actions=allowed,
            running_count=self.running_count if self.expose_count else None,
            true_count=true_count,
        )

    def _summary(self, trace: Dict, extra: Optional[Dict] = None) -> Dict:
        out = {
            "dealer": [c.label() for c in self.dealer_cards],
            "hands": [[c.label() for c in h.cards] for h in self.hands],
            "bets": [h.bet for h in self.hands],
            "trace": trace,
        }
        if extra:
            out.update(extra)
        return out
