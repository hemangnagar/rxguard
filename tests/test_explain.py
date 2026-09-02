from rxguard.engine import analyze
from rxguard.explain import EvidenceExplainer, gate_explanation
from rxguard.models import ExplanationProposal
from rxguard.store import get_scenario


def test_offline_explanation_passes_same_gate_as_model_output():
    scenario = get_scenario("retroactive-loss")
    result = analyze(scenario)
    proposal = EvidenceExplainer().propose(scenario, result)
    gated = gate_explanation(proposal, result)
    assert gated.accepted
    assert "-$5.85" in gated.text


def test_gate_rejects_invented_dollar_amount():
    result = analyze(get_scenario("retroactive-loss"))
    proposal = ExplanationProposal(
        text="The verified loss is -$999.00.",
        cited_fact_ids=["actual-margin"],
        provider="test",
        model="bad-model",
    )
    gated = gate_explanation(proposal, result)
    assert not gated.accepted
    assert gated.text is None
    assert "Unsupported amount" in gated.rejection_reason


def test_gate_rejects_unknown_citation():
    result = analyze(get_scenario("profitable-fill"))
    proposal = ExplanationProposal(
        text="The fill is profitable.",
        cited_fact_ids=["made-up-fact"],
        provider="test",
        model="bad-model",
    )
    gated = gate_explanation(proposal, result)
    assert not gated.accepted
    assert "Unknown evidence" in gated.rejection_reason

