# RxGuard

**Evidence-first pharmacy margin and exception analysis.**

RxGuard joins three facts that pharmacy systems often leave in separate places:
what a payer returned, what the pharmacy paid, and what changed later. It then
flags loss-making fills, unresolved reversals, rejected claims and incomplete
audit packets. An explanation—whether produced by the offline baseline or an
optional model—cannot mention a dollar amount that is absent from the computed
fact pack.

All patients, products, claims, invoices and prices in this repository are
**synthetic**. RxGuard is not a clinical decision system, does not implement
NCPDP, and does not claim HIPAA compliance.

## Live demo

Open the interactive, synthetic-data demo: **[rxguard-demo.hemnag.chatgpt.site](https://rxguard-demo.hemnag.chatgpt.site)**

Select any claim to inspect the deterministic calculation, source evidence and generated FHIR `ExplanationOfBenefit`.

## Why this exists

A fill can look profitable on adjudication day and become a loss after a later
adjustment. RxGuard makes that change replayable:

```text
$414.10 revenue - $398.20 invoice cost =  $15.90 initial margin
 $15.90 margin  -  $21.75 adjustment   =  -$5.85 actual margin
```

Every number carries a source reference. The model may narrate those facts; it
does not calculate them.

## Project context and future branch

RxGuard grew out of a broader effort to build public, independently designed
governance demonstrations for regulated data using synthetic data, open-source
components and implemented industry standards. The pharmacy workbench is the
first focused product: it applies those principles to pharmacy financial and
operational exceptions without copying a private governed-data-platform or
claiming compliance that the prototype has not proved.

**CareGuardBench** is the planned healthcare-governance branch of this work. It
will reuse the architectural principles—deterministic policy enforcement,
traceable evidence, constrained AI explanations, FHIR-based interoperability
and explicit conformance boundaries—while addressing broader healthcare data
access, consent, provenance and audit scenarios. It is intentionally outside
the current RxGuard MVP so that RxGuard remains centered on pharmacy margin,
reversal, rejection and audit workflows. A financial-governance demonstration
may follow as a separate application rather than being folded into RxGuard.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m rxguard.api              # http://127.0.0.1:8094
```

Or:

```bash
docker compose up --build
```

## Six reproducible scenarios

| Scenario | Expected result |
|---|---|
| Routine profitable fill | clear; actual margin `$17.00` |
| Filled below acquisition cost | high; actual margin `-$16.50` |
| Later adjustment erased the margin | high; `$15.90` becomes `-$5.85` |
| Reversal without successful rebill | high; unresolved reversal and `-$32.40` |
| Rejected claim awaiting follow-up | high; no inventory cost recognized |
| Incomplete PBM audit packet | high; missing proof of delivery |

The scenarios are JSON content under `rxguard/scenarios/`. Adding a scenario
does not change the engine.

## Open standards and data

RxGuard uses open standards where they fit and declares its own content where
they do not:

- **FHIR R4/R4B** — `ExplanationOfBenefit` structure for claim plus
  adjudication information.
- **CARIN Blue Button Pharmacy EOB 2.2.0** — the emitted profile URI and open
  pharmacy EOB shape. Full implementation-guide conformance is not yet claimed.
- **RxNorm/RxNav** — adapter seam for normalized drug concepts. Synthetic
  fixtures deliberately omit invented RxCUIs.
- **FDA NDC Directory** — adapter seam for real product identifiers. Fixture
  NDCs are visibly synthetic.
- **CMS NADAC** — public benchmark input. A NADAC-derived margin must never be
  presented as actual pharmacy margin without invoice evidence.
- **RxGuard Operational Event 0.1** — later adjustments, invoice facts,
  reversals and audit-document state that should not be forced into FHIR.

The standards registry at `rxguard/standards/registry.json` records whether
each claim is standard-backed, source-backed, referenced or declared, and where
the corresponding implementation lives.

The repository also carries a CycloneDX SBOM and a generated Python dependency
license inventory under `sbom/`. Regenerate both with
`python tools/build_sbom.py`; CI refuses declared AGPL, GPL-2/3, SSPL, BUSL and
Commons Clause dependencies.

### Current conformance boundary

The open-source `fhir.resources` package structurally validates each emitted
FHIR R4B `ExplanationOfBenefit`. The CARIN profile URI is present, but CARIN
conformance is recorded as **spec-referenced** until an implementation-guide
validator is wired into CI. This is intentional: metadata cannot award itself
authority.

## Explanation gate

The default offline explainer keeps the demo reproducible. To use Claude:

```bash
pip install -e ".[ai]"
export ANTHROPIC_API_KEY=...
export RXGUARD_EXPLAINER=anthropic
python -m rxguard.api
```

The same deterministic gate evaluates either path:

1. Every citation must name a fact in the computed fact pack.
2. Every dollar amount in the explanation must equal a computed fact.
3. A proposal without citations is rejected.
4. Rejection returns no narrative, only the reason it was withheld.

No clinical recommendation or legal conclusion belongs in this path.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Synthetic-only status, scenario count and explainer mode |
| `GET /api/standards` | Machine-readable authority registry |
| `GET /api/scenarios` | Work-queue summary |
| `POST /api/scenarios/{id}/run` | Analysis, evidence, gated explanation and FHIR EOB |
| `GET /docs` | OpenAPI documentation |

## What is deliberately not implemented

- NCPDP Telecommunication, SCRIPT, Batch or Audit transactions.
- Connection to a live payer, PBM, pharmacy-management system or wholesaler.
- Clinical recommendations, substitution, dosing or interaction checking.
- Actual PHI or actual pharmacy financial information.
- A claim that NADAC equals a pharmacy's invoice cost.
- A claim of HIPAA, CARIN or payer conformance beyond what tests prove.

The next commercially useful step is an adapter for one pharmacy-management
system's ordinary CSV export, designed with a pharmacist and kept outside the
standards-restricted transaction layer.

## License

MIT. See `LICENSE`.
