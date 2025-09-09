from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Type, Callable, Optional

from .env import BlackjackEnv
from .rules import Rules
from .types import Observation, Action, HandView
from .agents.basic import BasicStrategyAgent


@dataclass
class PolicyMetrics:
    hands: int
    total_return: float
    ev_per_hand: float
    decisions: int
    mistakes: int
    mistake_rate: float


def run_policy_track(agent: Any, hands: int = 10000, seed: int | None = 42, rules: Rules | None = None, *, log_fn: Optional[Callable[[Dict], None]] = None) -> Dict:
    env = BlackjackEnv(rules=rules, seed=seed)
    baseline = BasicStrategyAgent()
    total_return = 0
    mistakes = 0
    decisions = 0
    traces: List[Dict] = []
    # Reset illegal counters if supported (GuardedAgent)
    if hasattr(agent, "reset_illegals"):
        try:
            agent.reset_illegals()  # type: ignore[attr-defined]
        except Exception:
            pass

    for hand_idx in range(hands):
        reward, summary = env.play_hand(agent, bet=1)
        total_return += reward
        # compare decisions to baseline
        made_any = False
        for j, d in enumerate(summary["trace"].get("decisions", [])):
            obsd = d["obs"]
            obs = Observation(
                player=HandView(
                    cards=obsd["player"]["cards"],
                    total=obsd["player"]["total"],
                    is_soft=obsd["player"]["is_soft"],
                    can_split=obsd["player"]["can_split"],
                    can_double=obsd["player"]["can_double"],
                ),
                dealer_upcard=obsd["dealer_upcard"],
                hand_index=obsd["hand_index"],
                num_hands=obsd["num_hands"],
                allowed_actions=[Action[a] for a in obsd["allowed_actions"]],
                running_count=obsd.get("running_count"),
                true_count=obsd.get("true_count"),
            )
            agent_action = Action[d["action"]]
            baseline_action = baseline.act(obs, info={})
            decisions += 1
            mistake = agent_action != baseline_action
            if mistake:
                mistakes += 1
            if log_fn is not None:
                event = {
                        "track": "policy",
                        "hand": hand_idx,
                        "decision_idx": j,
                        "obs": d["obs"],
                        "agent_action": agent_action.name,
                        "baseline_action": baseline_action.name,
                        "mistake": mistake,
                        "meta": d.get("meta", {}),
                        "final": {
                            "reward": reward,
                            "dealer": summary.get("dealer"),
                            "hands": summary.get("hands"),
                            "bets": summary.get("bets"),
                            "outcomes": summary.get("outcomes"),
                            "result": summary.get("result"),
                            "outcome_labels": summary.get("outcome_labels"),
                            "result_detail": summary.get("result_detail"),
                        },
                    }
                try:
                    log_fn(event)
                except Exception:
                    pass
            made_any = True
        traces.append(summary)
        # If no decisions occurred (e.g., naturals), still emit a minimal event
        if log_fn is not None and not made_any:
            try:
                log_fn({
                    "track": "policy",
                    "hand": hand_idx,
                    "decision_idx": None,
                    "no_decision": True,
                    "final": {
                        "reward": reward,
                        "dealer": summary.get("dealer"),
                        "hands": summary.get("hands"),
                        "bets": summary.get("bets"),
                        "outcomes": summary.get("outcomes"),
                        "result": summary.get("result"),
                        "outcome_labels": summary.get("outcome_labels"),
                        "result_detail": summary.get("result_detail"),
                    },
                })
            except Exception:
                pass

    ev = total_return / hands if hands else 0.0
    mr = mistakes / decisions if decisions else 0.0
    out = {
        "track": "policy",
        "metrics": PolicyMetrics(
            hands=hands,
            total_return=total_return,
            ev_per_hand=ev,
            decisions=decisions,
            mistakes=mistakes,
            mistake_rate=mr,
        ).__dict__,
        "samples": min(10, len(traces)),
        "trace_preview": traces[:10],
    }
    if hasattr(agent, "illegal_count"):
        out["metrics"]["illegal_actions"] = int(getattr(agent, "illegal_count"))
        out["metrics"]["illegal_rate"] = (getattr(agent, "illegal_count") / decisions) if decisions else 0.0
    return out


def _grid_weights_infinite_deck() -> Dict[Tuple[str, str, str], float]:
    # Ranks with 10-grouping; probabilities under infinite-deck approximation
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    pr = {r: (4/13 if r == "10" else 1/13) for r in ranks}
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]
    pd = {d: pr[d] for d in dealer_up}

    weights: Dict[Tuple[str, str, str], float] = {}
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:
            p_player = (pr[r1] ** 2) if r1 == r2 else (2 * pr[r1] * pr[r2])
            for du in dealer_up:
                weights[(r1, r2, du)] = p_player * pd[du]
    # Sum is 1.0 under independence
    return weights


def run_policy_grid(
    agent: Any,
    seed: int | None = 123,
    rules: Rules | None = None,
    *,
    weighted: bool = False,
    reps: int = 1,
    log_fn: Optional[Callable[[Dict], None]] = None,
    resume_from: Optional[str] = None,
) -> Dict:
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    dealer_up = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]

    baseline = BasicStrategyAgent()
    total_return = 0
    mistakes = 0
    decisions = 0
    traces: List[Dict] = []
    weights = _grid_weights_infinite_deck() if weighted else None
    weighted_return = 0.0
    sum_w = 0.0
    if hasattr(agent, "reset_illegals"):
        try:
            agent.reset_illegals()  # type: ignore[attr-defined]
        except Exception:
            pass

    # Build skip set for resume: (p1, p2, du, rep)
    skip: set[tuple[str, str, str, int]] = set()
    if resume_from:
        try:
            with open(resume_from, "r", encoding="utf-8") as fh:
                import json as _json
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = _json.loads(line)
                    except Exception:
                        continue
                    if ev.get("track") != "policy-grid":
                        continue
                    cell = ev.get("cell") or {}
                    rep = ev.get("rep")
                    if not isinstance(rep, int):
                        continue
                    p1, p2, du = cell.get("p1"), cell.get("p2"), cell.get("du")
                    if isinstance(p1, str) and isinstance(p2, str) and isinstance(du, str):
                        skip.add((p1, p2, du, rep))
        except FileNotFoundError:
            pass

    cell_index = 0
    cell_count = 0
    executed_hands = 0
    for i, r1 in enumerate(ranks):
        for r2 in ranks[i:]:  # combinations with repetition
            for du in dealer_up:
                cell_count += 1
                cell_total = 0
                exec_reps = 0
                for rep in range(reps):
                    if (r1, r2, du, rep) in skip:
                        continue
                    # fresh env per replicate for independence
                    env = BlackjackEnv(rules=rules, seed=(None if seed is None else (seed + cell_index * 1009 + rep)), expose_count=False)
                    reward, summary = env.play_hand(agent, bet=1, start={"p1": r1, "p2": r2, "du": du})
                    cell_total += reward
                    exec_reps += 1
                    executed_hands += 1
                    made_any = False
                    for j, d in enumerate(summary["trace"].get("decisions", [])):
                        obsd = d["obs"]
                        obs = Observation(
                            player=HandView(
                                cards=obsd["player"]["cards"],
                                total=obsd["player"]["total"],
                                is_soft=obsd["player"]["is_soft"],
                                can_split=obsd["player"]["can_split"],
                                can_double=obsd["player"]["can_double"],
                            ),
                            dealer_upcard=obsd["dealer_upcard"],
                            hand_index=obsd["hand_index"],
                            num_hands=obsd["num_hands"],
                            allowed_actions=[Action[a] for a in obsd["allowed_actions"]],
                            running_count=None,
                            true_count=None,
                        )
                        agent_action = Action[d["action"]]
                        baseline_action = baseline.act(obs, info={})
                        decisions += 1
                        mistake = agent_action != baseline_action
                        if mistake:
                            mistakes += 1
                        if log_fn is not None:
                            event = {
                                "track": "policy-grid",
                                "cell": {"p1": r1, "p2": r2, "du": du},
                                "rep": rep,
                                "decision_idx": j,
                                "obs": d["obs"],
                                "agent_action": agent_action.name,
                                "baseline_action": baseline_action.name,
                                "mistake": mistake,
                                "meta": d.get("meta", {}),
                                "final": {
                                    "reward": reward,
                                    "dealer": summary.get("dealer"),
                                    "hands": summary.get("hands"),
                                    "bets": summary.get("bets"),
                                    "outcomes": summary.get("outcomes"),
                                    "result": summary.get("result"),
                                    "outcome_labels": summary.get("outcome_labels"),
                                    "result_detail": summary.get("result_detail"),
                                },
                            }
                            try:
                                log_fn(event)
                            except Exception:
                                pass
                        made_any = True
                    # If no decisions for this (cell,rep), still emit an event so resume/progress counts it
                    if log_fn is not None and not made_any:
                        try:
                            log_fn({
                                "track": "policy-grid",
                                "cell": {"p1": r1, "p2": r2, "du": du},
                                "rep": rep,
                                "decision_idx": None,
                                "no_decision": True,
                                "final": {
                                    "reward": reward,
                                    "dealer": summary.get("dealer"),
                                    "hands": summary.get("hands"),
                                    "bets": summary.get("bets"),
                                    "outcomes": summary.get("outcomes"),
                                    "result": summary.get("result"),
                                    "outcome_labels": summary.get("outcome_labels"),
                                    "result_detail": summary.get("result_detail"),
                                },
                            })
                        except Exception:
                            pass
                    if cell_index < 10 and rep == 0:
                        traces.append(summary)
                total_return += cell_total
                if weighted and weights is not None and exec_reps > 0:
                    w = weights[(r1, r2, du)]
                    sum_w += w
                    weighted_return += w * (cell_total / exec_reps)
                cell_index += 1

    hands = executed_hands
    ev = total_return / hands if hands else 0.0
    mr = mistakes / decisions if decisions else 0.0
    out = {
        "track": "policy-grid",
        "metrics": PolicyMetrics(
            hands=hands,
            total_return=total_return,
            ev_per_hand=ev,
            decisions=decisions,
            mistakes=mistakes,
            mistake_rate=mr,
        ).__dict__,
        "samples": min(10, len(traces)),
        "trace_preview": traces[:10],
    }
    if weighted:
        out["metrics"]["ev_weighted"] = weighted_return if sum_w else 0.0
        out["metrics"]["sum_weights"] = sum_w
        out["metrics"]["weighted"] = True
        out["metrics"]["reps"] = reps
    else:
        out["metrics"]["weighted"] = False
        out["metrics"]["reps"] = reps
    if hasattr(agent, "illegal_count"):
        out["metrics"]["illegal_actions"] = int(getattr(agent, "illegal_count"))
        out["metrics"]["illegal_rate"] = (getattr(agent, "illegal_count") / decisions) if decisions else 0.0
    return out
