from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .models import EvidenceFact, Finding, SourceFact


class MfpRefundStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    SHORT_PAID = "short_paid"
    OVERDUE = "overdue"


class MfpDrugProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display: str
    generic: str
    ndc: str
    package: str
    manufacturer: str


class MfpDeposit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: SourceFact
    deposit_date: date


class MfpFill(BaseModel):
    """One dispensing of an MFP-selected drug and the records around it.

    The pharmacy acquires at roughly WAC, the Part D claim adjudicates against
    the lower Maximum Fair Price, and the manufacturer owes the gap as a
    refund routed through the Medicare Transaction Facilitator within 14
    calendar days of claim-data transmission. Every monetary input is a
    SourceFact so the reconciliation can cite its records.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    rx_number: str
    drug: MfpDrugProduct
    fill_date: date
    adjudication_ref: str
    transmitted_date: date
    transmission_ref: str
    acquisition: SourceFact
    mfp_price: SourceFact
    deposit: MfpDeposit | None = None


class MfpReconciliation(BaseModel):
    fill_id: str
    evidence_pack_id: str
    status: MfpRefundStatus
    due_date: date
    expected_refund: Decimal
    received: Decimal
    variance: Decimal
    days_late: int
    days_to_refund: int | None
    finding: Finding
    facts: list[EvidenceFact]
    evidence_complete: bool


class MfpAgingBucket(BaseModel):
    label: str
    min_days: int
    max_days: int | None
    claims: int
    amount: Decimal


class MfpSummary(BaseModel):
    as_of: date
    refund_window_days: int
    claims: int
    outstanding_amount: Decimal
    outstanding_claims: int
    overdue_amount: Decimal
    overdue_claims: int
    oldest_overdue_days: int
    short_paid_amount: Decimal
    short_paid_claims: int
    median_days_to_refund: int | None
    aging: list[MfpAgingBucket]
