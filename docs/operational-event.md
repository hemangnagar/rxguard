# RxGuard Operational Event 0.1

FHIR represents clinical and claims-exchange concepts. RxGuard keeps internal
pharmacy business evidence in a separate event rather than creating misleading
FHIR extensions.

Required fields:

| Field | Meaning |
|---|---|
| `event_id` | Stable event identifier |
| `event_type` | `invoice_cost`, `post_adjudication_adjustment`, `reversal`, `rebill`, or `audit_evidence` |
| `claim_reference` | Reference to the relevant FHIR EOB or source claim |
| `effective_date` | Date the business event became effective |
| `source_reference` | Location of the evidence from which the event was measured |

Money-bearing events additionally carry a decimal `amount` and ISO 4217
`currency`. A later adjustment is signed: charges are negative and credits are
positive. The engine never infers whether a payment includes patient pay or a
dispensing fee; adapters must map those facts explicitly.

This is a declared project format, not an HL7 or NCPDP standard.

