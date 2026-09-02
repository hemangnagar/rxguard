from fhir.resources.R4B.explanationofbenefit import ExplanationOfBenefit

from rxguard.fhir import CARIN_PHARMACY_PROFILE, build_pharmacy_eob
from rxguard.store import load_scenarios


def test_every_scenario_emits_structurally_valid_fhir_eob():
    for scenario in load_scenarios():
        resource = build_pharmacy_eob(scenario)
        validated = ExplanationOfBenefit.model_validate(resource)
        assert validated.model_dump(exclude_none=True)["resourceType"] == "ExplanationOfBenefit"


def test_pharmacy_eob_profile_is_declared_but_not_overclaimed():
    resource = build_pharmacy_eob(load_scenarios()[0])
    assert CARIN_PHARMACY_PROFILE in resource["meta"]["profile"]
