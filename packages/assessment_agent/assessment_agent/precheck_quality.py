"""Publication checks for diagnostic pre-checks, which must not teach their answers."""

from assessment_agent.bank import BankMCQ, KuBankGen, TIERS, mcq_problems


class QuestionQualityError(RuntimeError):
    """A bounded generation/review attempt ended without publishable questions."""


def precheck_problems(question: BankMCQ) -> list[str]:
    problems = mcq_problems(question)
    if question.hint is not None:
        problems.append("a diagnostic pre-check must have hint=null; do not supply hints")
    # Case is meaningful in code and mathematical symbols (x and X are distinct).
    if any(not option.strip() for option in question.options) or len({o.strip() for o in question.options}) != 3:
        problems.append("provide three distinct, non-empty options")
    return problems


def require_approved(flags: list[dict]) -> None:
    if flags:
        raise QuestionQualityError("Pre-check review failed: " + "; ".join(str(f.get("issue", "unresolved issue")) for f in flags))


def precheck_bank_problems(bank: KuBankGen) -> list[str]:
    problems = [f"{tier}: {p}" for tier in TIERS for p in precheck_problems(getattr(bank, tier))]
    seen = set()
    for tier in TIERS:
        stem = " ".join(getattr(bank, tier).stem.casefold().split())
        if stem in seen:
            problems.append(f"{tier}: questions at different tiers must have distinct stems")
        seen.add(stem)
    return problems
