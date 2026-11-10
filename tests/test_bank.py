"""The per-KU item bank: difficulty rules, assembly, answer balancing and validation (no LLM involved)."""

import pytest
from assessment_agent.bank import (
    MIN_TIER_GAP,
    TIERS,
    BankMCQ,
    KuBankGen,
    assemble_ku_items,
    balance_positions,
    bank_item_id,
    lecture_topic_id,
    order_tiers,
    mcq_problems,
    stem_problems,
    tier_beta,
    validate_bank,
)


def mcq(correct: int = 1, tag: str = "item") -> BankMCQ:
    return BankMCQ(
        stem=f"Stem {tag}?", options=[f"{tag} zero", f"{tag} one", f"{tag} two"], correct_index=correct,
        explanation=f"Because {tag}.", hint=None,
    )


def gen(ku_difficulty=0.0, correct=(1, 1, 1)) -> KuBankGen:
    return KuBankGen(
        basic=mcq(correct[0], "basic"), applied=mcq(correct[1], "applied"), advanced=mcq(correct[2], "advanced"),
        slides=[3, 4], ku_difficulty=ku_difficulty,
    )


class TestDifficulty:
    def test_tier_offsets_and_the_ku_rating_both_count(self):
        assert tier_beta("basic", 0.0) == -1.0
        assert tier_beta("applied", 0.0) == 0.0
        assert tier_beta("advanced", 0.0) == 1.0
        assert tier_beta("applied", 2.0) == 1.0  # a hard KU shifts its items up by at most one logit
        assert tier_beta("applied", -2.0) == -1.0

    def test_the_llm_estimate_is_clamped(self):
        assert tier_beta("applied", 99.0) == tier_beta("applied", 2.0)
        assert tier_beta("applied", -99.0) == tier_beta("applied", -2.0)

    def test_tiers_are_forced_into_increasing_order_moving_only_upward(self):
        got = order_tiers({"basic": 0.5, "applied": -0.3, "advanced": 0.1})
        assert got["basic"] == 0.5
        assert got["applied"] == pytest.approx(0.5 + MIN_TIER_GAP)
        assert got["advanced"] == pytest.approx(0.5 + 2 * MIN_TIER_GAP)

    def test_already_ordered_tiers_are_left_alone(self):
        assert order_tiers({"basic": -1.0, "applied": 0.1, "advanced": 1.2}) == {"basic": -1.0, "applied": 0.1, "advanced": 1.2}


class TestAssembly:
    def test_makes_three_bank_items_with_the_fields_cat_needs(self):
        items = assemble_ku_items("ku-a", lecture_topic_id(2), gen())
        assert [i.tier for i in items] == list(TIERS)
        assert [i.id for i in items] == [bank_item_id("ku-a", t) for t in TIERS]
        for i in items:
            assert (i.context, i.topic_id, i.ku_id) == ("assessment", "lecture-2", "ku-a")
            assert i.discrimination == 1.0 and i.allows_not_sure
            assert [r.slide_number for r in i.source_refs] == [3, 4]
        assert [i.difficulty_prior for i in items] == [-1.0, 0.0, 1.0]

    def test_a_hard_ku_shifts_all_three_items_up_and_keeps_the_tier_spread(self):
        easy = [i.difficulty_prior for i in assemble_ku_items("ku-a", "lecture-1", gen(ku_difficulty=-2.0))]
        hard = [i.difficulty_prior for i in assemble_ku_items("ku-a", "lecture-1", gen(ku_difficulty=2.0))]
        assert easy == [-2.0, -1.0, 0.0] and hard == [0.0, 1.0, 2.0]

    def test_the_stored_difficulty_is_beta_not_a_raw_llm_score(self):
        assert [i.difficulty_prior for i in assemble_ku_items("ku-a", "lecture-1", gen(ku_difficulty=1.0))] == [-0.5, 0.5, 1.5]


class TestBalancing:
    def test_spreads_the_keyed_answer_over_all_three_slots(self):
        kus = [f"ku-{k:02d}" for k in range(20)]
        items = [i for k in kus for i in assemble_ku_items(k, "lecture-1", gen(correct=(1, 1, 1)))]
        balance_positions(items, kus)
        counts = [sum(1 for i in items if i.correct_index == s) for s in range(3)]
        assert max(counts) - min(counts) <= 1 and sum(counts) == 60

    def test_keeps_the_keyed_option_text_and_does_not_depend_on_which_kus_are_in_the_run(self):
        kus = [f"ku-{k:02d}" for k in range(6)]
        full = [i for k in kus for i in assemble_ku_items(k, "lecture-1", gen(correct=(0, 2, 1)))]
        only_two = [i for k in kus[2:4] for i in assemble_ku_items(k, "lecture-1", gen(correct=(0, 2, 1)))]
        keyed_before = {i.id: i.options[i.correct_index] for i in full}
        balance_positions(full, kus)
        balance_positions(only_two, kus)  # same course KU list, fewer KUs generated
        assert {i.id: i.options[i.correct_index] for i in full} == keyed_before
        by_id = {i.id: i for i in full}
        assert all(by_id[i.id].correct_index == i.correct_index for i in only_two)


class TestValidation:
    KUS = ["ku-a", "ku-b"]

    def bank(self):
        return [i for k in self.KUS for i in assemble_ku_items(k, "lecture-1", gen())]

    def test_a_complete_bank_is_valid(self):
        assert validate_bank(self.bank(), self.KUS) == []

    def test_reports_a_missing_tier_and_an_uncovered_ku(self):
        items = [i for i in self.bank() if i.id != bank_item_id("ku-a", "advanced")]
        problems = validate_bank(items, [*self.KUS, "ku-c"])
        assert any("ku-a: missing advanced" in p for p in problems)
        assert any("ku-c: missing basic, applied, advanced" in p for p in problems)

    def test_reports_duplicates_unknown_kus_wrong_discrimination_and_disordered_difficulty(self):
        items = self.bank()
        assert any("duplicate" in p for p in validate_bank(items + [items[0]], self.KUS))
        assert any("unknown KUs" in p for p in validate_bank(items, ["ku-a"]))
        items[0].discrimination = 1.4
        assert any("discrimination" in p for p in validate_bank(items, self.KUS))
        items = self.bank()
        items[2].difficulty_prior = items[0].difficulty_prior - 1
        assert any("tier order" in p for p in validate_bank(items, self.KUS))

    def test_rejects_items_that_are_not_bank_items(self):
        from syllabyte_common.learner import Item

        legacy = Item(id="cp-x", topic_id="t", context="checkpoint", stem="?", options=["a", "b", "c"], correct_index=0,
                      allows_not_sure=True, explanation="e")
        assert any("not a bank item" in p for p in validate_bank([legacy], []))


class TestStems:
    def test_flags_a_stem_that_never_asks_anything(self):
        g = gen()
        g.advanced.stem = "A colleague claims a correlation proves causation."
        g.basic.stem = "What is a chart?  "
        assert stem_problems(g) == ["advanced: the stem must end with a question that tells the student what to do"]

    def test_a_question_after_a_claim_is_fine(self):
        g = gen()
        g.applied.stem = "A colleague claims a correlation proves causation; what is wrong with that?"
        assert stem_problems(g) == []


class TestPrecheckQuestions:
    """The check comes before the lecture, on a phone (2026-10-21 review of the ML trial's lecture 1 check)."""

    def test_a_long_stem_is_sent_back(self):
        m = mcq()
        m.stem = " ".join(["word"] * 91) + "?"
        assert mcq_problems(m) == ["the stem has 91 words; keep it to 90 or fewer"]
        m.stem = " ".join(["word"] * 29) + "?"
        assert mcq_problems(m) == []

    def test_a_question_about_slides_the_student_has_not_seen_is_sent_back(self):
        for stem in (
            "The slide nests boxes inside one another; which sit inside machine learning?",
            "In the supervised learning slide, what does the symbol mean?",
            "These slides show a house example; what changes if it also outputs rent?",
        ):
            m = mcq()
            m.stem = stem
            assert any("material the student has not seen" in p for p in mcq_problems(m)), stem

    def test_a_case_described_in_the_stem_is_fine(self):
        m = mcq()
        m.stem = "A bank collects user profiles with the credit decision for each; what does supervised learning do?"
        m.options = ["Hand-code the rules for each profile", "Learn the mapping from the examples", "Cluster the profiles"]
        assert mcq_problems(m) == []

    @pytest.mark.parametrize("stem, options", [
        ("What is the derivative of x²?", ["2x", "x", "0"]),
        ("What is the eigenvalue λ of the 1×1 matrix [2]?", ["2", "3", "4"]),
        ("Which formula states that every element satisfies P?", ["∀x P(x)", "∃x P(x)", "¬∃x P(x)"]),
        ("Which complexity is linear?", ["O(n)", "O(n²)", "O(2ⁿ)"]),
        ("Which statement characterizes an injective function?", ["Distinct inputs have distinct outputs", "Every output has two inputs", "No output has an input"]),
        ("Which expression is the polynomial's derivative?", ["3x² + 2x + 1", "0", "x"]),
        ("Which conclusion follows?", ["Some elements satisfy P", "No elements satisfy P", "Every element satisfies P"]),
        ("A graph has edges A→B and B→C. Is C reachable from A?", ["Yes", "No", "It depends"]),
    ])
    def test_notation_formula_lengths_and_quantifiers_are_left_to_semantic_review(self, stem, options):
        m = mcq()
        m.stem, m.options, m.correct_index = stem, options, 0
        assert mcq_problems(m) == []

    def test_code_is_not_counted_as_prose(self):
        m = mcq()
        m.stem = "In Python 3:\n```python\nvalues = [" + ", ".join(["1"] * 100) + "]\n```\nWhat is len(values)?"
        assert mcq_problems(m) == []

    def test_plain_words_numbers_and_articles_are_not_notation(self):
        m = mcq()
        m.stem = "A robot gets -50 points for a wall and a $340k house costs more; is Feature 1 enough, or do I need a model?"
        m.options = ["A penalty steers it away", "It's the robot's choice", "Plan the route first"]
        assert mcq_problems(m) == []

    def test_an_explanation_or_hint_with_stray_characters_is_sent_back(self):
        # seen in the ML trial: "…across categories.ics", "…can and cannot supply..", "…the molecule example.anything"
        for hint in ("Think about the categories.ics", "Ask what the records can supply..", "Compare it with the example.anything"):
            m = mcq()
            m.hint = hint
            assert mcq_problems(m) == ["the hint must be complete sentences ending in one full stop or question mark, with nothing after it"], hint
        m = mcq()
        m.hint, m.explanation = "Ask what kind of answer each model gives?", 'It is called "supervised."'
        assert mcq_problems(m) == []
