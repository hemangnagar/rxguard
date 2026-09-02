from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClaimStatus(StrEnum):
    PAID = "paid"
    REJECTED = "rejected"
    REVERSED = "reversed"
    PENDING = "pending"


class Severity(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    HIGH = "high"


class SourceFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    source_ref: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def decimal_from_input(cls, value: object) -> Decimal:
        return Decimal(str(value))


class Drug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display: str
    ndc: str
    rxcui: str | None = None
    quantity: Decimal = Field(gt=0)


class Adjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    effective_date: date
    amount: SourceFact
    reason: str


class AuditRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str
    present: bool
    source_ref: str


class PharmacyScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    summary: str
    patient_ref: str
    coverage_ref: str
    drug: Drug
    service_date: date
    claim_status: ClaimStatus
    dispensed: bool
    ingredient_reimbursement: SourceFact
    dispensing_fee: SourceFact
    patient_pay: SourceFact
    actual_acquisition_cost: SourceFact | None = None
    nadac_unit_cost: SourceFact | None = None
    adjustments: list[Adjustment] = Field(default_factory=list)
    rejection_reason: str | None = None
    replacement_claim_ref: str | None = None
    audit_requirements: list[AuditRequirement] = Field(default_factory=list)


class EvidenceFact(BaseModel):
    id: str
    label: str
    value: Decimal
    formatted: str
    source_refs: list[str]


class Finding(BaseModel):
    code: str
    title: str
    detail: str
    severity: Severity
    action: str
    basis: list[str]


class MarginResult(BaseModel):
    scenario_id: str
    actual_margin: Decimal | None
    benchmark_margin: Decimal | None
    pre_adjustment_margin: Decimal | None
    total_revenue: Decimal
    total_adjustments: Decimal
    cost_basis: Literal["actual", "nadac-benchmark", "none"]
    findings: list[Finding]
    facts: list[EvidenceFact]
    evidence_complete: bool
    standards: list[str]


class ExplanationProposal(BaseModel):
    text: str
    cited_fact_ids: list[str]
    provider: str
    model: str


class GatedExplanation(BaseModel):
    accepted: bool
    text: str | None
    provider: str
    model: str
    rejection_reason: str | None = None


class ScenarioRun(BaseModel):
    scenario: PharmacyScenario
    result: MarginResult
    explanation: GatedExplanation
    fhir_eob: dict

