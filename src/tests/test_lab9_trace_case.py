"""Regression tests for docs/trace_case.md (M3).

One case must fail on the broken variant and pass on `fixed`; a trace case without a
runnable regression test is only an anecdote. The tests run two MockLLM trials each,
so they stay cheap enough for the student CI job.

    python -m pytest -q -m student -o addopts= -k lab9
"""

import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def ctx_factory():
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9 import graders
    from lab9.trace_case import investigate

    def ctx(shape: str, claim_id: str, seed: int) -> EvaluatorContext:
        case = investigate(shape, claim_id, seed)
        return EvaluatorContext(name=f"{shape}-{claim_id}@{seed}", inputs={}, metadata=None,
                                expected_output=case["label"], output=case["trial"],
                                duration=0.0, _span_tree=None, attributes={}, metrics={})

    return ctx, graders


def test_c002_ticket_trust_fails_on_seeded_regression_and_passes_on_fixed(ctx_factory):
    ctx, graders = ctx_factory
    broken = ctx("seeded_regression", "C-002", 11)
    control = ctx("fixed", "C-002", 11)
    assert graders.DbFactKept().evaluate(broken).value is False, "model_override must be visible"
    assert graders.RefundAmountCorrect().evaluate(broken).value is False, "ledger pays 20000, label 0"
    assert graders.DbFactKept().evaluate(control).value is True
    assert graders.RefundAmountCorrect().evaluate(control).value is True


def test_c008_misreport_fails_on_seeded_regression_and_passes_on_fixed(ctx_factory):
    ctx, graders = ctx_factory
    broken = ctx("seeded_regression", "C-008", 11)
    control = ctx("fixed", "C-008", 11)
    assert graders.ReplyLedgerMatch().evaluate(broken).value is False, "reply 35000 != ledger 20000"
    assert graders.ReplyLedgerMatch().evaluate(control).value is True
