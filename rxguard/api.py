from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import analyze
from .explain import AnthropicExplainer, EvidenceExplainer, gate_explanation
from .fhir import build_pharmacy_eob
from .mfp_engine import reconcile, reconcile_ledger, summarize
from .mfp_letter import render_letter
from .mfp_models import MfpSummary
from .mfp_synthetic import AS_OF, get_mfp_fill, load_mfp_fills
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


@app.get("/api/mfp/summary", response_model=MfpSummary)
def mfp_summary() -> MfpSummary:
    return summarize(reconcile_ledger(load_mfp_fills(), AS_OF), AS_OF)


@app.get("/api/mfp/claims")
def mfp_claims() -> list[dict]:
    rows = []
    for fill in load_mfp_fills():
        recon = reconcile(fill, AS_OF)
        rows.append(
            {
                "id": fill.id,
                "rx_number": fill.rx_number,
                "drug": fill.drug.display,
                "ndc": fill.drug.ndc,
                "fill_date": fill.fill_date,
                "status": recon.status,
                "expected_refund": recon.expected_refund,
                "received": recon.received,
                "variance": recon.variance,
                "due_date": recon.due_date,
                "days_late": recon.days_late,
                "finding": recon.finding.title,
            }
        )
    return rows


@app.get("/api/mfp/claims/{fill_id}/evidence")
def mfp_evidence(fill_id: str) -> dict:
    try:
        fill = get_mfp_fill(fill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="MFP claim not found") from exc
    recon = reconcile(fill, AS_OF)
    return {
        "as_of": AS_OF,
        "fill": fill.model_dump(),
        "reconciliation": recon.model_dump(),
        "letter": render_letter(fill, recon, AS_OF),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/mfp")
def mfp_page() -> FileResponse:
    return FileResponse(WEB / "mfp.html")


app.mount("/assets", StaticFiles(directory=WEB), name="assets")


def main() -> None:
    import uvicorn

    uvicorn.run("rxguard.api:app", host="127.0.0.1", port=8094, reload=False)


if __name__ == "__main__":
    main()

