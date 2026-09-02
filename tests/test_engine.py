from decimal import Decimal

import pytest

from rxguard.engine import analyze
from rxguard.store import get_scenario, load_scenarios


def test_six_scenarios_are_content_not_code():
    assert len(load_scenarios()) == 6


@pytest.mark.parametrize(
    ("scenario_id", "actual_margin", "finding"),
    [
        ("profitable-fill", Decimal("17.00"), "CLEAR"),
        ("below-cost-fill", Decimal("-16.50"), "ACTUAL_LOSS"),
        ("retroactive-loss", Decimal("-5.85"), "RETROACTIVE_LOSS"),
        ("unresolved-reversal", Decimal("-32.40"), "UNRESOLVED_REVERSAL"),
        ("rejected-claim", None, "CLAIM_REJECTED"),
        ("audit-evidence-gap", Decimal("18.30"), "AUDIT_EVIDENCE_GAP"),
    ],
)
def test_expected_scenario_outcomes(scenario_id, actual_margin, finding):
    result = analyze(get_scenario(scenario_id))
    assert result.actual_margin == actual_margin
    assert result.findings[0].code == finding
    assert result.evidence_complete


def test_retroactive_loss_reconciles_exactly():
    result = analyze(get_scenario("retroactive-loss"))
    assert result.pre_adjustment_margin == Decimal("15.90")
    assert result.total_adjustments == Decimal("-21.75")
    assert result.actual_margin == Decimal("-5.85")


def test_nadac_is_never_used_as_actual_cost():
    result = analyze(get_scenario("rejected-claim"))
    assert result.actual_margin is None
    assert result.cost_basis == "nadac-benchmark"


def test_every_money_fact_carries_source_evidence():
    for scenario in load_scenarios():
        for fact in analyze(scenario).facts:
            assert fact.source_refs
            assert all(ref.strip() for ref in fact.source_refs)

