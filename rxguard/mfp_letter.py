from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from .engine import fmt
from .explain import MONEY_PATTERN
from .mfp_models import MfpFill, MfpReconciliation, MfpRefundStatus

PHARMACY_LETTERHEAD = "Dogwood Pharmacy · 123 Maple Ave SW, Vienna, VA 22180 · NCPDP 3947261"


class LetterAuditError(RuntimeError):
    """A generated letter carried a dollar amount absent from the fact pack."""


def audit_letter(text: str, reconciliation: MfpReconciliation) -> None:
    """Same rule the explanation gate enforces: narration — a demand letter
    included — may not contain a dollar amount that is not a computed fact."""
    allowed = {fact.value for fact in reconciliation.facts}
    allowed.update(-value for value in set(allowed))
    for match in MONEY_PATTERN.finditer(text):
        try:
            value = Decimal(match.group("amount").replace(",", ""))
        except InvalidOperation:
            continue
        if match.group("sign") == "-":
            value = -value
        if value not in allowed:
            raise LetterAuditError(f"Unsupported amount in letter: {fmt(value)}")


def render_letter(fill: MfpFill, reconciliation: MfpReconciliation, as_of: date) -> str | None:
    """Deterministic escalation letter for overdue or short-paid refunds,
    built only from the fill's records and the reconciliation's facts, then
    audited. Returns None when there is nothing to demand."""
    if reconciliation.status not in (MfpRefundStatus.OVERDUE, MfpRefundStatus.SHORT_PAID):
        return None

    short = reconciliation.status == MfpRefundStatus.SHORT_PAID
    kind = "Short-paid" if short else "Overdue"
    if short:
        deposit = fill.deposit
        situation = (
            f"our bank records reflect a deposit of only {fmt(reconciliation.received)} "
            f"({deposit.amount.source_ref}, {deposit.deposit_date.isoformat()})"
        )
        remedy = f"the balance of {fmt(reconciliation.variance)}"
    else:
        situation = "our bank records reflect no matching deposit"
        remedy = f"the full refund of {fmt(reconciliation.variance)}"

    text = f"""{PHARMACY_LETTERHEAD}

{as_of.isoformat()}

{fill.drug.manufacturer} — Medicare MFP Effectuation Team
via CMS Medicare Transaction Facilitator

RE: {kind} Maximum Fair Price refund — Rx {fill.rx_number}, NDC {fill.drug.ndc}

On {fill.fill_date.isoformat()} this pharmacy dispensed {fill.drug.display} ({fill.drug.generic}), {fill.drug.package}, acquired at WAC {fmt(fill.acquisition.value)} ({fill.acquisition.source_ref}). Claim data was transmitted through the Medicare Transaction Facilitator on {fill.transmitted_date.isoformat()} ({fill.transmission_ref}; {fill.adjudication_ref}).

Under the standard default refund requirement, the refund of {fmt(reconciliation.expected_refund)} — WAC {fmt(fill.acquisition.value)} less MFP {fmt(fill.mfp_price.value)} — was due within 14 calendar days, i.e. by {reconciliation.due_date.isoformat()}. As of {as_of.isoformat()}, {situation}.

We request remittance of {remedy} within five (5) business days, referencing {fill.transmission_ref}. Absent payment, we will submit evidence pack {reconciliation.evidence_pack_id} to CMS with a request for enforcement review, and reserve all other remedies.

Sincerely,
[Pharmacist-in-Charge], PharmD

Enclosure: Evidence pack {reconciliation.evidence_pack_id} — every amount above resolves to a source record cited in it."""

    audit_letter(text, reconciliation)
    return text
