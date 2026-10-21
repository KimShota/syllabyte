"""The CAT engine: selection, estimation, hints, "Not sure", and the session."""

import math
import random

import numpy as np
import pytest
from assessment_agent import Answer, BankItem, CatConfig, CatSession, estimate_theta, select_next, standard_error
from catsim.item_bank import ItemBank
from catsim.selection import MaxInfoSelector


def pool_of(*bs: float, a: float = 1.0) -> list[BankItem]:
    return [BankItem(f"i{k}", a, b) for k, b in enumerate(bs)]


def log_lik(theta: float, items: list[BankItem], outcomes: list[bool]) -> float:
    total = 0.0
    for it, ok in zip(items, outcomes):
        p = 1 / (1 + math.exp(-it.a * (theta - it.b)))
        total += math.log(p if ok else 1 - p)
    return total


class TestSelection:
    def test_picks_the_item_closest_to_theta_when_discrimination_is_equal(self):
        pool = pool_of(-2.0, -0.4, 0.9, 1.7)
        assert select_next(pool, set(), 0.0).id == "i1"
        assert select_next(pool, set(), 1.0).id == "i2"
        assert select_next(pool, set(), 5.0).id == "i3"

    def test_skips_administered_items_and_ends_when_none_are_left(self):
        pool = pool_of(-1.0, 0.0, 1.0)
        assert select_next(pool, {"i1"}, 0.0).id in {"i0", "i2"}
        assert select_next(pool, {"i0", "i1", "i2"}, 0.0) is None

    def test_breaks_ties_by_pool_order_not_numpy_order(self):
        # b = +0.5 and -0.5 are equally informative at theta = 0.
        assert select_next(pool_of(0.5, -0.5), set(), 0.0).id == "i0"
        assert select_next(pool_of(-0.5, 0.5), set(), 0.0).id == "i0"
        assert select_next(pool_of(0.5, -0.5, 0.5), {"i0"}, 0.0).id == "i1"

    def test_agrees_with_catsims_own_max_info_selector_when_there_are_no_ties(self):
        rng = random.Random(7)
        for _ in range(40):
            pool = [BankItem(f"i{k}", rng.uniform(0.6, 2.2), rng.uniform(-3, 3)) for k in range(rng.randint(3, 25))]
            theta = rng.uniform(-3, 3)
            done = {f"i{k}" for k in rng.sample(range(len(pool)), rng.randint(0, len(pool) - 1))}
            bank = ItemBank(np.array([[it.a, it.b, 0.0, 1.0] for it in pool]), validate=False)
            theirs = MaxInfoSelector().select(
                item_bank=bank, administered_items=[i for i, it in enumerate(pool) if it.id in done], est_theta=theta
            )
            assert select_next(pool, done, theta).id == pool[theirs].id

    def test_uses_discrimination_for_2pl_banks(self):
        # at theta = 0 the sharper item wins even though the other one is closer to theta
        pool = [BankItem("blunt", 0.5, 0.1), BankItem("sharp", 2.0, 0.6)]
        assert select_next(pool, set(), 0.0).id == "sharp"


class TestEstimation:
    def test_no_evidence_leaves_theta_at_the_start(self):
        pool = pool_of(-1.0, 0.0, 1.0)
        assert estimate_theta(pool, [], start_theta=0.3) == 0.3

    def test_all_correct_uses_dodd_over_the_whole_pool_recursively(self):
        pool = pool_of(-1.0, 0.0, 2.0)  # hardest item in the pool: 2.0, even if never asked
        answers = [Answer("i0", "correct")]
        assert estimate_theta(pool, answers) == pytest.approx(1.0)  # 0 + (2 - 0) / 2
        answers.append(Answer("i1", "correct"))
        assert estimate_theta(pool, answers) == pytest.approx(1.5)  # 1 + (2 - 1) / 2

    def test_all_wrong_uses_dodd_toward_the_easiest_item(self):
        pool = pool_of(-1.0, 0.0, 2.0)
        assert estimate_theta(pool, [Answer("i1", "wrong")]) == pytest.approx(-0.5)  # 0 - (0 + 1) / 2

    def test_mixed_answers_give_the_maximum_likelihood_estimate(self):
        pool = pool_of(-1.2, -0.3, 0.4, 1.1, 1.9)
        answers = [Answer("i0", "correct"), Answer("i1", "correct"), Answer("i2", "wrong"), Answer("i3", "wrong")]
        got = estimate_theta(pool, answers)
        grid = np.linspace(-6, 6, 120001)
        outcomes = [True, True, False, False]
        best = grid[int(np.argmax([log_lik(t, pool[:4], outcomes) for t in grid]))]
        assert got == pytest.approx(best, abs=1e-4)

    def test_more_correct_answers_never_lower_theta_among_mixed_patterns(self):
        pool = pool_of(-1.0, -0.5, 0.0, 0.5, 1.0, 1.5)
        order = ["i2", "i3", "i1", "i4", "i0", "i5"]
        # k = 1..4 correct first: both the pattern with k and the one with k + 1 correct still contain a miss
        for k in range(1, 5):
            worse = [Answer(i, "correct" if n < k else "wrong") for n, i in enumerate(order)]
            better = [Answer(i, "correct" if n <= k else "wrong") for n, i in enumerate(order)]
            assert estimate_theta(pool, better) >= estimate_theta(pool, worse)

    def test_dodd_estimates_for_uniform_patterns_stay_inside_the_pool_range(self):
        # Dodd's heuristic is not a maximum-likelihood estimate: with a narrow pool, "all correct" can sit below
        # "all but one correct" (and "all wrong" above "one right"). It is catsim's behaviour and the engine
        # keeps it (plan D7); what it does guarantee is a finite value between the easiest and hardest item.
        pool = pool_of(-1.0, -0.5, 0.0, 0.5, 1.0, 1.5)
        for outcome in ("correct", "wrong"):
            answers = [Answer(f"i{k}", outcome) for k in range(6)]
            for n in range(1, 7):
                assert -1.0 <= estimate_theta(pool, answers[:n]) <= 1.5

    def test_not_sure_is_scored_exactly_as_a_wrong_answer(self):
        pool = pool_of(-1.0, 0.0, 1.0, 0.5)
        base = [Answer("i0", "correct"), Answer("i1", "wrong")]
        wrong = estimate_theta(pool, base + [Answer("i2", "wrong")])
        assert estimate_theta(pool, base + [Answer("i2", "not_sure")]) == wrong
        assert estimate_theta(pool, base + [Answer("i2", "not_sure", hinted=True)]) == wrong  # no hint shift
        assert estimate_theta(pool, [Answer("i2", "not_sure"), Answer("i3", "not_sure")], 0.2) < 0.2

    def test_a_hinted_correct_answer_counts_for_less_than_an_unhinted_one(self):
        pool = pool_of(-1.0, 0.0, 1.0, 0.5)
        rest = [Answer("i0", "correct"), Answer("i2", "wrong"), Answer("i3", "wrong")]
        plain = estimate_theta(pool, rest + [Answer("i1", "correct")])
        hinted = estimate_theta(pool, rest + [Answer("i1", "correct", hinted=True)])
        assert hinted < plain

    def test_a_hinted_wrong_answer_counts_as_worse_than_an_unhinted_one(self):
        pool = pool_of(-1.0, 0.0, 1.0, 0.5)
        rest = [Answer("i0", "correct"), Answer("i2", "correct"), Answer("i3", "correct")]
        plain = estimate_theta(pool, rest + [Answer("i1", "wrong")])
        hinted = estimate_theta(pool, rest + [Answer("i1", "wrong", hinted=True)])
        assert hinted < plain

    def test_hint_shift_is_configurable_and_zero_means_no_effect(self):
        pool = pool_of(-1.0, 0.0, 1.0)
        a = [Answer("i0", "correct"), Answer("i1", "wrong", hinted=True), Answer("i2", "wrong")]
        none = [Answer(x.item_id, x.outcome) for x in a]
        assert estimate_theta(pool, a, hint_beta_shift=0.0) == estimate_theta(pool, none)

    def test_rejects_answers_for_unknown_items_and_duplicate_pool_ids(self):
        with pytest.raises(ValueError, match="unknown item"):
            estimate_theta(pool_of(0.0), [Answer("nope", "correct")])
        with pytest.raises(ValueError, match="duplicate"):
            estimate_theta([BankItem("x", 1, 0), BankItem("x", 1, 1)], [])

    def test_bank_items_must_have_positive_discrimination(self):
        with pytest.raises(ValueError, match="discrimination"):
            BankItem("x", 0.0, 0.0)
        with pytest.raises(ValueError, match="difficulty"):
            BankItem("x", 1.0, float("nan"))


class TestStandardError:
    def test_is_infinite_without_evidence_and_shrinks_with_more_items(self):
        pool = pool_of(-1.0, -0.5, 0.0, 0.5, 1.0)
        assert standard_error(pool, [], 0.0) == math.inf
        two = [Answer("i1", "correct"), Answer("i3", "wrong")]
        five = two + [Answer("i0", "correct"), Answer("i2", "correct"), Answer("i4", "wrong")]
        assert standard_error(pool, five, 0.0) < standard_error(pool, two, 0.0)

    def test_matches_the_closed_form_for_rasch_items(self):
        pool = pool_of(-0.5, 0.5)
        answers = [Answer("i0", "correct"), Answer("i1", "wrong")]
        info = sum(math.exp(-(0 - b)) / (1 + math.exp(-(0 - b))) ** 2 for b in (-0.5, 0.5))
        assert standard_error(pool, answers, 0.0) == pytest.approx(1 / math.sqrt(info))

    def test_with_alpha_one_four_items_leave_an_se_near_one_logit(self):
        # the limitation recorded in the plan (D7): a fixed-length test of 4 cannot reach a tight SE
        pool = pool_of(-0.3, -0.1, 0.1, 0.3)
        answers = [Answer("i0", "correct"), Answer("i1", "wrong"), Answer("i2", "correct"), Answer("i3", "wrong")]
        assert 0.9 < standard_error(pool, answers, 0.0) < 1.2


class TestSession:
    def test_asks_exactly_length_items_and_each_choice_follows_the_answers(self):
        pool = pool_of(-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2)
        s = CatSession(pool, CatConfig(length=4))
        asked = []
        while (it := s.next_item()) is not None:
            asked.append(it.id)
            s.answer(it.id, "correct")
        assert len(asked) == 4 and s.done
        # all correct: theta climbs, so each next item is harder than the last
        bs = [next(i for i in pool if i.id == a).b for a in asked]
        assert bs == sorted(bs) and bs[0] == 0

    def test_not_sure_counts_toward_the_length_and_as_a_wrong_answer(self):
        def run(outcome):
            s = CatSession(pool_of(-1, 0, 1, 2, 3), CatConfig(length=3))
            for _ in range(3):
                s.answer(s.next_item().id, outcome)
            return s

        s = run("not_sure")
        assert s.done and s.n_scored == 3 and s.theta < 0 and math.isfinite(s.standard_error)
        assert s.theta == run("wrong").theta

    def test_stops_early_when_the_pool_runs_out(self):
        s = CatSession(pool_of(-1, 0, 1), CatConfig(length=5))
        while (it := s.next_item()) is not None:
            s.answer(it.id, "wrong")
        assert len(s.answers) == 3 and s.done and s.next_item() is None

    def test_rejects_an_item_twice_or_an_unknown_item(self):
        s = CatSession(pool_of(-1, 0, 1), CatConfig(length=3))
        s.answer("i1", "correct")
        with pytest.raises(ValueError, match="already answered"):
            s.answer("i1", "wrong")
        with pytest.raises(ValueError, match="unknown"):
            s.answer("zzz", "wrong")

    def test_starts_from_the_configured_theta(self):
        s = CatSession(pool_of(-2, -1, 0, 1, 2), CatConfig(length=2, start_theta=-1.4))
        assert s.next_item().b == -1
        assert s.theta == -1.4
