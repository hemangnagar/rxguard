from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .engine import fmt
from .models import ExplanationProposal, GatedExplanation, MarginResult, PharmacyScenario

MONEY_PATTERN = re.compile(r"(?<![\w])(?P<sign>-?)\$(?P<amount>[0-9][0-9,]*\.\d{2})")


class Explainer(Protocol):
    def propose(self, scenario: PharmacyScenario, result: MarginResult) -> ExplanationProposal: ...


class EvidenceExplainer:
    """Offline baseline. An optional model can replace it behind the same gate."""

    def propose(self, scenario: PharmacyScenario, result: MarginResult) -> ExplanationProposal:
        finding = result.findings[0]
        margin = result.actual_margin if result.actual_margin is not None else result.benchmark_margin
        fact_id = "actual-margin" if result.actual_margin is not None else "benchmark-margin"
        if margin is None:
            text = f"{finding.title}. {finding.detail} {finding.action}"
            cited = ["total-revenue"]
        else:
            text = f"{finding.title}. The verified margin is {fmt(margin)}. {finding.action}"
            cited = [fact_id]
        return ExplanationProposal(
            text=text,
            cited_fact_ids=cited,
            provider="offline-baseline",
            model="evidence-template-v1",
        )


class AnthropicExplainer:
    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        from anthropic import Anthropic

        self.client = Anthropic()
        self.model = model

    def propose(self, scenario: PharmacyScenario, result: MarginResult) -> ExplanationProposal:
        fact_pack = "\n".join(f"{fact.id}: {fact.formatted} — {fact.label}" for fact in result.facts)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=220,
            system=(
                "Write a concise pharmacy work-queue explanation. Use only supplied facts. "
                "Never add a dollar amount, clinical recommendation, or legal conclusion."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Scenario: {scenario.title}\n"
                        f"Finding: {result.findings[0].model_dump_json()}\n"
                        f"Facts:\n{fact_pack}\n"
                        "Return two sentences and then a final line `CITES: fact-id[,fact-id]`."
                    ),
                }
            ],
        )
        raw = response.content[0].text.strip()
        text, _, cites = raw.rpartition("CITES:")
        return ExplanationProposal(
            text=text.strip(),
            cited_fact_ids=[item.strip() for item in cites.split(",") if item.strip()],
            provider="anthropic",
            model=self.model,
        )


def gate_explanation(proposal: ExplanationProposal, result: MarginResult) -> GatedExplanation:
    facts = {fact.id: fact for fact in result.facts}
    unknown = sorted(set(proposal.cited_fact_ids) - set(facts))
    if unknown:
        return GatedExplanation(
            accepted=False,
            text=None,
            provider=proposal.provider,
            model=proposal.model,
            rejection_reason="Unknown evidence citation(s): " + ", ".join(unknown),
        )

    allowed_values = {fact.value for fact in result.facts}
    for match in MONEY_PATTERN.finditer(proposal.text):
        try:
            value = Decimal(match.group("amount").replace(",", ""))
            if match.group("sign") == "-":
                value = -value
        except InvalidOperation:
            continue
        if value not in allowed_values:
            return GatedExplanation(
                accepted=False,
                text=None,
                provider=proposal.provider,
                model=proposal.model,
                rejection_reason=f"Unsupported amount in explanation: {fmt(value)}",
            )

    if not proposal.cited_fact_ids:
        return GatedExplanation(
            accepted=False,
            text=None,
            provider=proposal.provider,
            model=proposal.model,
            rejection_reason="Explanation supplied no evidence citations.",
        )
    return GatedExplanation(
        accepted=True,
        text=proposal.text,
        provider=proposal.provider,
        model=proposal.model,
    )

