from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .engine import fmt, money
from .models import EvidenceFact, Finding, Severity
from .mfp_models import (
    MfpAgingBucket,
    MfpFill,
    MfpReconciliation,
    MfpRefundStatus,
    MfpSummary,
)

# CMS standard default refund requirement: the manufacturer pays the
# WAC-minus-MFP gap within 14 calendar days of claim-data transmission
# through the Medicare Transaction Facilitator.
REFUND_WINDOW_DAYS = 14

ZERO = Decimal("0.00")


def _fact(fact_id: str, label: str, value: Decimal, *sources: str) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        label=label,
        value=money(value),
        formatted=fmt(value),
        source_refs=list(dict.fromkeys(sources)),
    )


def reconcile(fill: MfpFill, as_of: date) -> MfpReconciliation:
    """Deterministic per-fill refund reconciliation. No model involvement."""
    expected = money(fill.acquisition.value - fill.mfp_price.value)
    received = money(fill.deposit.amount.value) if fill.deposit else ZERO
    variance = money(expected - received)
    due_date = fill.transmitted_date + timedelta(days=REFUND_WINDOW_DAYS)

    days_to_refund = (
        (fill.deposit.deposit_date - fill.transmitted_date).days if fill.deposit else None
    )

    if fill.deposit is not None and variance <= 0:
        status = MfpRefundStatus.PAID
        days_late = 0
    elif fill.deposit is not None:
        status = MfpRefundStatus.SHORT_PAID
        days_late = 0
    elif as_of > due_date:
        status = MfpRefundStatus.OVERDUE
        days_late = (as_of - due_date).days
    else:
        status = MfpRefundStatus.PENDING
        days_late = 0

    received_sources = (
        [fill.deposit.amount.source_ref]
        if fill.deposit
        else [f"mfp:{fill.id}#no-deposit-through-{as_of.isoformat()}"]
    )
    facts = [
        _fact("acquisition-cost", "Acquisition cost (WAC, package)",
              fill.acquisition.value, fill.acquisition.source_ref),
        _fact("mfp-price", "Maximum Fair Price (CMS file)",
              fill.mfp_price.value, fill.mfp_price.source_ref),
        _fact("expected-refund", "Expected manufacturer refund (WAC − MFP)",
              expected, fill.acquisition.source_ref, fill.mfp_price.source_ref),
        _fact("received-amount", "Refund received", received, *received_sources),
        _fact("refund-variance", "Refund variance", variance,
              fill.acquisition.source_ref, fill.mfp_price.source_ref, *received_sources),
    ]

    if status == MfpRefundStatus.OVERDUE:
        finding = Finding(
            code="MFP_REFUND_OVERDUE",
            title="Manufacturer refund past the 14-day standard",
            detail=(
                f"The {fmt(variance)} refund was due {due_date.isoformat()} "
                f"({REFUND_WINDOW_DAYS} calendar days after MTF transmission) and is "
                f"{days_late} days late with no matching deposit."
            ),
            severity=Severity.HIGH,
            action=(
                "Send the escalation letter referencing the MTF transmission; "
                "file the evidence pack with CMS if payment does not follow."
            ),
            basis=["cms:mfp-refund-window-policy", "rxguard:mfp-reconciliation-policy"],
        )
    elif status == MfpRefundStatus.SHORT_PAID:
        finding = Finding(
            code="MFP_REFUND_SHORT",
            title="Refund deposit below the expected amount",
            detail=(
                f"The deposit of {fmt(received)} is {fmt(variance)} short of the "
                f"expected {fmt(expected)} refund."
            ),
            severity=Severity.HIGH,
            action="Request the balance with the deposit and invoice references attached.",
            basis=["cms:mfp-refund-window-policy", "rxguard:mfp-reconciliation-policy"],
        )
    elif status == MfpRefundStatus.PAID and days_to_refund is not None and days_to_refund > REFUND_WINDOW_DAYS:
        finding = Finding(
            code="MFP_REFUND_PAID_LATE",
            title="Refund paid in full, outside the window",
            detail=(
                f"Paid in full {days_to_refund} days after transmission "
                f"(standard: {REFUND_WINDOW_DAYS} calendar days)."
            ),
            severity=Severity.REVIEW,
            action="No recovery needed; the lateness feeds the cash-flow record.",
            basis=["rxguard:mfp-reconciliation-policy"],
        )
    elif status == MfpRefundStatus.PAID:
        finding = Finding(
            code="MFP_REFUND_PAID",
            title="Refund received in full within the window",
            detail=f"Paid in full {days_to_refund} days after transmission.",
            severity=Severity.CLEAR,
            action="No action required.",
            basis=["rxguard:mfp-reconciliation-policy"],
        )
    else:
        finding = Finding(
            code="MFP_REFUND_PENDING",
            title="Refund inside the 14-day window",
            detail=f"The {fmt(expected)} refund is due by {due_date.isoformat()}.",
            severity=Severity.CLEAR,
            action=f"No action until {due_date.isoformat()}.",
            basis=["rxguard:mfp-reconciliation-policy"],
        )

    source_refs = {fill.acquisition.source_ref, fill.mfp_price.source_ref, *received_sources}
    evidence_complete = all(bool(ref.strip()) for ref in source_refs)

    return MfpReconciliation(
        fill_id=fill.id,
        evidence_pack_id=f"EP-{fill.fill_date.year}-{fill.id}",
        status=status,
        due_date=due_date,
        expected_refund=expected,
        received=received,
        variance=variance,
        days_late=days_late,
        days_to_refund=days_to_refund,
        finding=finding,
        facts=facts,
        evidence_complete=evidence_complete,
    )


def reconcile_ledger(fills: tuple[MfpFill, ...], as_of: date) -> list[MfpReconciliation]:
    return [reconcile(fill, as_of) for fill in fills]


_AGING_BUCKETS = (
    ("1–14 days late", 1, 14),
    ("15–30 days late", 15, 30),
    ("31+ days late", 31, None),
)


def summarize(reconciliations: list[MfpReconciliation], as_of: date) -> MfpSummary:
    """Roll-up computed only from reconciliation rows — never entered by hand."""
    unpaid = [r for r in reconciliations
              if r.status in (MfpRefundStatus.PENDING, MfpRefundStatus.OVERDUE)]
    overdue = [r for r in reconciliations if r.status == MfpRefundStatus.OVERDUE]
    shorts = [r for r in reconciliations if r.status == MfpRefundStatus.SHORT_PAID]
    settled_days = sorted(
        r.days_to_refund for r in reconciliations if r.days_to_refund is not None
    )

    aging = []
    for label, lo, hi in _AGING_BUCKETS:
        rows = [r for r in overdue if r.days_late >= lo and (hi is None or r.days_late <= hi)]
        aging.append(
            MfpAgingBucket(
                label=label,
                min_days=lo,
                max_days=hi,
                claims=len(rows),
                amount=money(sum((r.variance for r in rows), Decimal("0"))),
            )
        )

    return MfpSummary(
        as_of=as_of,
        refund_window_days=REFUND_WINDOW_DAYS,
        claims=len(reconciliations),
        outstanding_amount=money(
            sum((r.variance for r in unpaid + shorts), Decimal("0"))
        ),
        outstanding_claims=len(unpaid) + len(shorts),
        overdue_amount=money(sum((r.variance for r in overdue), Decimal("0"))),
        overdue_claims=len(overdue),
        oldest_overdue_days=max((r.days_late for r in overdue), default=0),
        short_paid_amount=money(sum((r.variance for r in shorts), Decimal("0"))),
        short_paid_claims=len(shorts),
        median_days_to_refund=(
            settled_days[len(settled_days) // 2] if settled_days else None
        ),
        aging=aging,
    )
