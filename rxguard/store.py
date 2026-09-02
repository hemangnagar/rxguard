from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

from .models import PharmacyScenario


@lru_cache(maxsize=1)
def load_scenarios() -> tuple[PharmacyScenario, ...]:
    directory = files("rxguard").joinpath("scenarios")
    loaded: list[PharmacyScenario] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.name.endswith(".json"):
            loaded.append(PharmacyScenario.model_validate_json(path.read_text()))
    return tuple(loaded)


def get_scenario(scenario_id: str) -> PharmacyScenario:
    for scenario in load_scenarios():
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(scenario_id)


@lru_cache(maxsize=1)
def load_standards() -> dict:
    path = files("rxguard").joinpath("standards", "registry.json")
    return json.loads(path.read_text())

