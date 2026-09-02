from __future__ import annotations

from fhir.resources.R4B.explanationofbenefit import ExplanationOfBenefit

from .engine import money
from .models import PharmacyScenario

CARIN_PHARMACY_PROFILE = (
    "http://hl7.org/fhir/us/carin-bb/StructureDefinition/"
    "C4BB-ExplanationOfBenefit-Pharmacy"
)


def build_pharmacy_eob(scenario: PharmacyScenario) -> dict:
    revenue = money(
        scenario.ingredient_reimbursement.value
        + scenario.dispensing_fee.value
        + scenario.patient_pay.value
    )
    resource = {
        "resourceType": "ExplanationOfBenefit",
        "id": f"eob-{scenario.id}",
        "meta": {"profile": [CARIN_PHARMACY_PROFILE]},
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "pharmacy",
                    "display": "Pharmacy",
                }
            ]
        },
        "use": "claim",
        "patient": {"reference": scenario.patient_ref},
        "created": scenario.service_date.isoformat(),
        "insurer": {"reference": "Organization/synthetic-payer"},
        "provider": {"reference": "Organization/synthetic-pharmacy"},
        "outcome": "complete" if scenario.claim_status.value == "paid" else "partial",
        "insurance": [{"focal": True, "coverage": {"reference": scenario.coverage_ref}}],
        "item": [
            {
                "sequence": 1,
                "productOrService": {
                    "coding": [
                        {
                            "system": "http://hl7.org/fhir/sid/ndc",
                            "code": scenario.drug.ndc,
                            "display": scenario.drug.display,
                        }
                    ]
                },
                "servicedDate": scenario.service_date.isoformat(),
                "quantity": {"value": float(scenario.drug.quantity)},
                "adjudication": [
                    {
                        "category": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/adjudication",
                                    "code": "benefit",
                                }
                            ]
                        },
                        "amount": {"value": float(revenue), "currency": "USD"},
                    }
                ],
            }
        ],
        "total": [
            {
                "category": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/adjudication",
                            "code": "benefit",
                        }
                    ]
                },
                "amount": {"value": float(revenue), "currency": "USD"},
            }
        ],
    }
    # Structural validation is performed by the open-source fhir.resources R4B
    # models. CARIN profile conformance is a stronger claim and is intentionally
    # not made without running an implementation-guide validator.
    validated = ExplanationOfBenefit.model_validate(resource)
    return validated.model_dump(exclude_none=True)

