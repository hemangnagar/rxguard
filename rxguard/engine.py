from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .models import (
    ClaimStatus,
    EvidenceFact,
    Finding,
    MarginResult,
    PharmacyScenario,
    Severity,
)

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(money(value)):,.2f}"


def _fact(fact_id: str, label: str, value: Decimal, *sources: str) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        label=label,
        value=money(value),
        formatted=fmt(value),
        source_refs=list(dict.fromkeys(sources)),
    )


def analyze(scenario: PharmacyScenario) -> MarginResult:
    revenue = money(
        scenario.ingredient_reimbursement.value
        + scenario.dispensing_fee.value
        + scenario.patient_pay.value
    )
    adjustments = money(sum((item.amount.value for item in scenario.adjustments), Decimal("0")))

    actual_cost = scenario.actual_acquisition_cost.value if scenario.actual_acquisition_cost else None
    benchmark_cost = (
        scenario.nadac_unit_cost.value * scenario.drug.quantity
        if scenario.nadac_unit_cost
        else None
    )
    if not scenario.dispensed:
        actual_cost = Decimal("0") if actual_cost is not None else None
        benchmark_cost = Decimal("0") if benchmark_cost is not None else None

    pre_adjustment = money(revenue - actual_cost) if actual_cost is not None else None
    actual_margin = money(revenue + adjustments - actual_cost) if actual_cost is not None else None
    benchmark_margin = (
        money(revenue + adjustments - benchmark_cost) if benchmark_cost is not None else None
    )

    facts = [
        _fact(
            "total-revenue",
            "Total recognized revenue",
            revenue,
            scenario.ingredient_reimbursement.source_ref,
            scenario.dispensing_fee.source_ref,
            scenario.patient_pay.source_ref,
        ),
        _fact(
            "total-adjustments",
            "Post-adjudication adjustments",
            adjustments,
            *(
                [item.amount.source_ref for item in scenario.adjustments]
                or [f"scenario:{scenario.id}#adjustments-empty"]
            ),
        ),
    ]
    if actual_cost is not None:
        facts.extend(
            [
                _fact(
                    "actual-cost",
                    "Actual acquisition cost",
                    actual_cost,
                    scenario.actual_acquisition_cost.source_ref,
                ),
                _fact(
                    "pre-adjustment-margin",
                    "Margin before later adjustments",
                    pre_adjustment,
                    scenario.actual_acquisition_cost.source_ref,
                    scenario.ingredient_reimbursement.source_ref,
                ),
                _fact(
                    "actual-margin",
                    "Actual margin",
                    actual_margin,
                    scenario.actual_acquisition_cost.source_ref,
                    scenario.ingredient_reimbursement.source_ref,
                    *(item.amount.source_ref for item in scenario.adjustments),
                ),
            ]
        )
    if benchmark_cost is not None:
        facts.extend(
            [
                _fact(
                    "nadac-benchmark-cost",
                    "NADAC benchmark cost",
                    benchmark_cost,
                    scenario.nadac_unit_cost.source_ref,
                ),
                _fact(
                    "benchmark-margin",
                    "NADAC benchmark margin",
                    benchmark_margin,
                    scenario.nadac_unit_cost.source_ref,
                    scenario.ingredient_reimbursement.source_ref,
                    *(item.amount.source_ref for item in scenario.adjustments),
                ),
            ]
        )

    findings: list[Finding] = []
    if scenario.claim_status == ClaimStatus.REJECTED:
        findings.append(
            Finding(
                code="CLAIM_REJECTED",
                title="Rejected claim needs action",
                detail=scenario.rejection_reason or "The payer rejected this claim.",
                severity=Severity.HIGH,
                action="Review the rejection and route it to the appropriate staff queue.",
                basis=["rxguard:claim-status-policy"],
            )
        )
    if scenario.claim_status == ClaimStatus.REVERSED and not scenario.replacement_claim_ref:
        findings.append(
            Finding(
                code="UNRESOLVED_REVERSAL",
                title="Reversal has no replacement claim",
                detail="The original claim was reversed and no successful rebill is linked.",
                severity=Severity.HIGH,
                action="Confirm whether the medication was dispensed and locate or create the rebill.",
                basis=["rxguard:reversal-reconciliation-policy"],
            )
        )
    missing_documents = [item.document for item in scenario.audit_requirements if not item.present]
    if missing_documents:
        findings.append(
            Finding(
                code="AUDIT_EVIDENCE_GAP",
                title="Audit evidence is incomplete",
                detail="Missing: " + ", ".join(missing_documents) + ".",
                severity=Severity.HIGH,
                action="Collect the missing evidence before responding to the audit request.",
                basis=["rxguard:audit-evidence-policy"],
            )
        )
    if actual_margin is not None and actual_margin < 0:
        retroactive = pre_adjustment is not None and pre_adjustment >= 0 and adjustments < 0
        findings.append(
            Finding(
                code="RETROACTIVE_LOSS" if retroactive else "ACTUAL_LOSS",
                title="Later adjustment erased the margin" if retroactive else "Prescription filled below cost",
                detail=(
                    f"The fill moved from {fmt(pre_adjustment)} before adjustments to "
                    f"{fmt(actual_margin)} after adjustments."
                    if retroactive
                    else f"Verified margin is {fmt(actual_margin)} using the pharmacy invoice cost."
                ),
                severity=Severity.HIGH,
                action="Review the payer response, adjustment and purchasing evidence before the next refill.",
                basis=["rxguard:actual-margin-policy"],
            )
        )
    elif benchmark_margin is not None and benchmark_margin < 0:
        findings.append(
            Finding(
                code="BENCHMARK_LOSS",
                title="Reimbursement is below the NADAC benchmark",
                detail=f"Benchmark margin is {fmt(benchmark_margin)}; actual invoice cost is needed for a loss claim.",
                severity=Severity.REVIEW,
                action="Attach the wholesaler invoice to calculate actual margin.",
                basis=["cms:nadac", "rxguard:benchmark-margin-policy"],
            )
        )
    if not findings:
        findings.append(
            Finding(
                code="CLEAR",
                title="No configured exception found",
                detail="The claim is profitable and its configured evidence is complete.",
                severity=Severity.CLEAR,
                action="No action required.",
                basis=["rxguard:clear-policy"],
            )
        )

    source_refs = {
        scenario.ingredient_reimbursement.source_ref,
        scenario.dispensing_fee.source_ref,
        scenario.patient_pay.source_ref,
    }
    source_refs.update(item.amount.source_ref for item in scenario.adjustments)
    if scenario.actual_acquisition_cost:
        source_refs.add(scenario.actual_acquisition_cost.source_ref)
    if scenario.nadac_unit_cost:
        source_refs.add(scenario.nadac_unit_cost.source_ref)
    evidence_complete = all(bool(ref.strip()) for ref in source_refs)

    if actual_cost is not None:
        cost_basis = "actual"
    elif benchmark_cost is not None:
        cost_basis = "nadac-benchmark"
    else:
        cost_basis = "none"

    return MarginResult(
        scenario_id=scenario.id,
        actual_margin=actual_margin,
        benchmark_margin=benchmark_margin,
        pre_adjustment_margin=pre_adjustment,
        total_revenue=revenue,
        total_adjustments=adjustments,
        cost_basis=cost_basis,
        findings=findings,
        facts=facts,
        evidence_complete=evidence_complete,
        standards=[
            "hl7:fhir-r4-pharmacy-eob",
            "carin-bb:pharmacy-eob-2.2.0",
            "nlm:rxnorm",
            "fda:ndc-directory",
            "cms:nadac",
            "rxguard:operational-event-0.1",
        ],
    )
