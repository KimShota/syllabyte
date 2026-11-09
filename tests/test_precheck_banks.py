"""Three-tier pre-check generation and publication gates, with no paid model calls."""

import pytest

from assessment_agent import bank_writing, item_writing, question_writing
from assessment_agent.bank import BankMCQ, KuBankGen, TIERS
from assessment_agent.precheck_quality import QuestionQualityError
from curriculum_alignment_agent.deck_kus import UploadKU
from ingestion_agent.upload_jobs import run_question_bank_job
from syllabyte_common.models import RunManifest, Slide, SlideDeck, SlideRef


KU = UploadKU(id="ku-stacks", title="Stacks", short_title="Stacks", summary="Last-in-first-out behavior and undo.",
    bloom_level="understand", cognitive_load="low", prerequisites=[], source_refs=[SlideRef(deck_name="deck", slide_number=1)],
    visual_idea="A stack", short_worthiness=3, short_worthiness_reason="A foundational idea.")
DECK = SlideDeck(name="deck", source_path="deck.pdf", slides=[Slide(deck_name="deck", slide_number=1, text="A stack removes the most recently added item.")])


def generated():
    return KuBankGen(
        basic=BankMCQ(stem="What does a stack remove first?", options=["The newest item", "The oldest item", "The middle item"], correct_index=0, explanation="Stacks remove the most recently added item."),
        applied=BankMCQ(stem="Push red, then blue, then pop. Which item remains?", options=["The red item", "The blue item", "Neither item"], correct_index=0, explanation="Popping removes blue, leaving red."),
        advanced=BankMCQ(stem="An undo system restores the oldest edit first. Which change would make it undo the most recent edit?", options=["Use a stack", "Use a queue", "Sort the edits"], correct_index=0, explanation="A stack restores the most recent edit first."),
        slides=[1], ku_difficulty=-2,
    )


def payload():
    return {"deck_id": "deck", "ku": KU.model_dump(mode="json"), "prereq_titles": [], "avoid": ["An earlier question?"],
        "questions": [{"item_id": f"as-course-ku-stacks-{tier}-bank", "tier": tier, "beta": beta, "target_index": i}
                      for i, (tier, beta) in enumerate(zip(TIERS, (-0.5, 0.5, 1.5)))]}


def verdicts(**kw):
    return item_writing.Verdicts(verdicts=[item_writing.Verdict(id=f"as-ku-stacks-{tier}", ok=True) for tier in TIERS])


def test_writes_three_tiers_in_one_generation_and_one_joint_review(monkeypatch):
    calls = []

    def write(**kw):
        calls.append(("write", kw))
        return generated()

    def review(**kw):
        calls.append(("review", kw))
        return verdicts()

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", review)
    out = run_question_bank_job(payload(), DECK, log=lambda _: None)
    assert [kind for kind, _ in calls] == ["write", "review"]
    assert [q["tier"] for q in out["items"]] == list(TIERS)
    assert [q["difficulty_prior"] for q in out["items"]] == [-0.5, 0.5, 1.5]  # preserve extraction's difficulties
    assert [q["correct_index"] for q in out["items"]] == [0, 1, 2]
    assert all(q["hint"] is None and q["source_refs"] == [{"deck_name": "deck", "slide_number": 1}] for q in out["items"])
    assert out["flags"] == []
    prompt = calls[0][1]["content"][0]["text"]
    assert "An earlier question?" in prompt and "Set hint=null" in prompt
    assert "Do not state, define or explain the target rule" in prompt
    assert "task matches its stated tier" in calls[1][1]["system"]


@pytest.mark.parametrize("review", [
    item_writing.Verdicts(verdicts=[]),
    item_writing.Verdicts(verdicts=[item_writing.Verdict(id="as-ku-stacks-basic", ok=True)]),
    item_writing.Verdicts(verdicts=[item_writing.Verdict(id=f"as-ku-stacks-{t}", ok=True) for t in TIERS] + [item_writing.Verdict(id="as-ku-stacks-basic", ok=True)]),
])
def test_incomplete_or_duplicate_reviews_cannot_publish_a_bank(monkeypatch, review):
    monkeypatch.setattr(bank_writing, "structured", lambda **kw: generated())
    monkeypatch.setattr(item_writing, "structured", lambda **kw: review)
    with pytest.raises(QuestionQualityError, match="exactly one verdict"):
        run_question_bank_job(payload(), DECK, log=lambda _: None)


def test_reviewer_can_reject_answer_giveaways_and_demand_a_rewrite(monkeypatch):
    prompts, reviews = [], []

    def write(**kw):
        prompts.append(kw["content"][0]["text"])
        return generated()

    def review(**kw):
        reviews.append(kw)
        result = verdicts()
        if len(reviews) == 1:
            result.verdicts[0].ok = False
            result.verdicts[0].issue = "The stem teaches the answer; test the rule without defining it."
        return result

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", review)
    assert run_question_bank_job(payload(), DECK, log=lambda _: None)["flags"] == []
    assert len(prompts) == 2 and "The stem teaches the answer" in prompts[1]


def test_unresolved_flags_or_hints_are_never_published(monkeypatch):
    generated_count = []

    def write(**kw):
        generated_count.append(1)
        bank = generated()
        bank.basic.hint = "Choose the newest item."
        return bank

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", verdicts)
    with pytest.raises(QuestionQualityError, match="hint=null"):
        run_question_bank_job(payload(), DECK, log=lambda _: None)
    assert len(generated_count) <= 4  # retries remain bounded


def test_bank_cannot_cite_pages_that_do_not_exist(monkeypatch):
    def write(**kw):
        bank = generated()
        bank.slides = [99]
        return bank

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", verdicts)
    with pytest.raises(ValueError, match="cite pages"):
        run_question_bank_job(payload(), DECK, log=lambda _: None)


def test_three_tiers_cannot_reuse_the_same_question(monkeypatch):
    def write(**kw):
        bank = generated()
        bank.advanced.stem = bank.basic.stem
        return bank

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", verdicts)
    with pytest.raises(QuestionQualityError, match="distinct stems"):
        run_question_bank_job(payload(), DECK, log=lambda _: None)


def test_the_one_question_fallback_also_requires_complete_review(monkeypatch):
    monkeypatch.setattr(question_writing, "structured", lambda **kw: question_writing.QuestionGen(question=generated().basic, slides=[1]))
    monkeypatch.setattr(item_writing, "structured", lambda **kw: item_writing.Verdicts(verdicts=[]))
    with pytest.raises(QuestionQualityError, match="exactly one verdict"):
        question_writing.write_question(KU, [], "basic", ("Stack material", []), avoid=[], model="test", critic_model="test",
            manifest=RunManifest(run_id="test"), log=lambda _: None)


def test_case_sensitive_answer_options_survive_review_and_balancing(monkeypatch):
    def write(**kw):
        bank = generated()
        bank.basic.stem = "In Python 3, which variable is assigned?\n```python\nX = 2\n```\nWhich name was assigned?"
        bank.basic.options = ["X", "x", "y"]
        bank.basic.explanation = "Python variable names are case-sensitive, so X is assigned."
        return bank

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", verdicts)
    result = run_question_bank_job(payload(), DECK, log=lambda _: None)
    assert result["flags"] == []
    assert result["items"][0]["options"] == ["X", "x", "y"]
    assert "```python\nX = 2\n```" in result["items"][0]["stem"]


def test_symbolic_questions_still_require_semantic_review(monkeypatch):
    def write(**kw):
        bank = generated()
        bank.basic.stem = "What is the derivative of x²?"
        bank.basic.options = ["2x", "x + x", "x"]  # two correct answers despite different strings
        return bank

    def reject(**kw):
        result = verdicts()
        result.verdicts[0].ok = False
        result.verdicts[0].issue = "2x and x + x are equivalent; more than one option is correct."
        return result

    monkeypatch.setattr(bank_writing, "structured", write)
    monkeypatch.setattr(item_writing, "structured", reject)
    with pytest.raises(QuestionQualityError, match="equivalent"):
        run_question_bank_job(payload(), DECK, log=lambda _: None)
