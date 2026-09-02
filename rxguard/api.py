from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import analyze
from .explain import AnthropicExplainer, EvidenceExplainer, gate_explanation
from .fhir import build_pharmacy_eob
from .models import ScenarioRun
from .store import get_scenario, load_scenarios, load_standards

app = FastAPI(
    title="RxGuard",
    description="Evidence-first pharmacy margin and exception analysis using synthetic data.",
    version="0.1.0",
)

WEB = Path(__file__).resolve().parents[1] / "web"


def explainer():
    if os.getenv("RXGUARD_EXPLAINER", "offline") == "anthropic":
        return AnthropicExplainer(os.getenv("RXGUARD_ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))
    return EvidenceExplainer()


def run_scenario(scenario_id: str) -> ScenarioRun:
    try:
        scenario = get_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Scenario not found") from exc
    result = analyze(scenario)
    proposal = explainer().propose(scenario, result)
    explanation = gate_explanation(proposal, result)
    return ScenarioRun(
        scenario=scenario,
        result=result,
        explanation=explanation,
        fhir_eob=build_pharmacy_eob(scenario),
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "synthetic_only": True,
        "scenarios": len(load_scenarios()),
        "explainer": os.getenv("RXGUARD_EXPLAINER", "offline"),
    }


@app.get("/api/standards")
def standards() -> dict:
    return load_standards()


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    rows = []
    for scenario in load_scenarios():
        result = analyze(scenario)
        rows.append(
            {
                "id": scenario.id,
                "title": scenario.title,
                "summary": scenario.summary,
                "drug": scenario.drug.display,
                "claim_status": scenario.claim_status,
                "severity": result.findings[0].severity,
                "finding": result.findings[0].title,
                "actual_margin": result.actual_margin,
                "benchmark_margin": result.benchmark_margin,
            }
        )
    return rows


@app.post("/api/scenarios/{scenario_id}/run", response_model=ScenarioRun)
def run(scenario_id: str) -> ScenarioRun:
    return run_scenario(scenario_id)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/assets", StaticFiles(directory=WEB), name="assets")


def main() -> None:
    import uvicorn

    uvicorn.run("rxguard.api:app", host="127.0.0.1", port=8094, reload=False)


if __name__ == "__main__":
    main()

