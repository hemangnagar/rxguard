from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from rxguard.api import app
from rxguard.mfp_engine import REFUND_WINDOW_DAYS, reconcile, reconcile_ledger, summarize
from rxguard.mfp_letter import LetterAuditError, audit_letter, render_letter
from rxguard.mfp_models import MfpRefundStatus
from rxguard.mfp_synthetic import AS_OF, get_mfp_fill, load_mfp_fills


def _recons():
    return reconcile_ledger(load_mfp_fills(), AS_OF)


def test_ledger_is_deterministic_content():
    fills = load_mfp_fills()
    assert len(fills) == 47
    assert fills == load_mfp_fills()
    # transmission always follows the fill by 2-4 days, never precedes it
    for fill in fills:
        assert timedelta(days=2) <= fill.transmitted_date - fill.fill_date <= timedelta(days=4)


def test_expected_refund_is_wac_minus_mfp_with_sources():
    for fill, recon in zip(load_mfp_fills(), _recons()):
        assert recon.expected_refund == fill.acquisition.value - fill.mfp_price.value
        assert recon.variance == recon.expected_refund - recon.received
        expected_fact = next(f for f in recon.facts if f.id == "expected-refund")
        assert fill.acquisition.source_ref in expected_fact.source_refs
        assert fill.mfp_price.source_ref in expected_fact.source_refs
        assert recon.evidence_complete


def test_status_breakdown_matches_curated_ledger():
    by_status = {}
    for recon in _recons():
        by_status.setdefault(recon.status, []).append(recon)
    assert len(by_status[MfpRefundStatus.PAID]) == 32
    assert len(by_status[MfpRefundStatus.PENDING]) == 7
    assert len(by_status[MfpRefundStatus.OVERDUE]) == 6
    assert len(by_status[MfpRefundStatus.SHORT_PAID]) == 2


def test_summary_totals_reconcile_to_the_row_level():
    recons = _recons()
    summary = summarize(recons, AS_OF)
    assert summary.claims == 47
    assert summary.outstanding_amount == Decimal("9703.00")
    assert summary.overdue_amount == Decimal("6510.00")
    assert summary.short_paid_amount == Decimal("689.00")
    assert summary.median_days_to_refund == 20
    assert summary.refund_window_days == REFUND_WINDOW_DAYS
    # the aging buckets partition the overdue amount exactly
    assert sum(b.amount for b in summary.aging) == summary.overdue_amount
    assert sum(b.claims for b in summary.aging) == summary.overdue_claims


def test_overdue_age_is_measured_from_the_due_date():
    hero = max(
        (r for r in _recons() if r.status == MfpRefundStatus.OVERDUE),
        key=lambda r: r.variance,
    )
    fill = get_mfp_fill(hero.fill_id)
    assert fill.drug.display.startswith("Enbrel")
    assert hero.expected_refund == Decimal("4750.00")
    assert hero.due_date == fill.transmitted_date + timedelta(days=REFUND_WINDOW_DAYS)
    assert hero.days_late == (AS_OF - hero.due_date).days
    assert hero.finding.code == "MFP_REFUND_OVERDUE"


def test_paid_late_is_flagged_for_review_not_recovery():
    late = [r for r in _recons() if r.finding.code == "MFP_REFUND_PAID_LATE"]
    assert late, "curated ledger includes late-but-paid refunds"
    for recon in late:
        assert recon.variance == Decimal("0.00")
        assert recon.days_to_refund > REFUND_WINDOW_DAYS


def test_pending_inside_window_is_not_overdue():
    fill = get_mfp_fill("C039")  # eliquis 2026-08-17 — window still open at AS_OF
    recon = reconcile(fill, AS_OF)
    assert recon.status == MfpRefundStatus.PENDING
    # ...and the same fill is overdue once the window has lapsed
    later = reconcile(fill, recon.due_date + timedelta(days=3))
    assert later.status == MfpRefundStatus.OVERDUE
    assert later.days_late == 3


def test_letter_renders_only_for_demandable_statuses():
    for fill, recon in zip(load_mfp_fills(), _recons()):
        letter = render_letter(fill, recon, AS_OF)
        demandable = recon.status in (MfpRefundStatus.OVERDUE, MfpRefundStatus.SHORT_PAID)
        assert (letter is not None) == demandable
        if letter:
            assert fill.transmission_ref in letter
            assert recon.evidence_pack_id in letter


def test_letter_gate_rejects_an_amount_outside_the_fact_pack():
    fill = next(f for f in load_mfp_fills() if f.drug.display.startswith("Enbrel") and f.deposit is None)
    recon = reconcile(fill, AS_OF)
    letter = render_letter(fill, recon, AS_OF)
    audit_letter(letter, recon)  # the genuine letter passes
    with pytest.raises(LetterAuditError):
        audit_letter(letter.replace("$4,750.00", "$4,950.00", 1), recon)


def test_mfp_api_surfaces_the_same_numbers():
    client = TestClient(app)
    summary = client.get("/api/mfp/summary").json()
    assert summary["outstanding_amount"] == "9703.00"
    claims = client.get("/api/mfp/claims").json()
    assert len(claims) == 47
    hero_id = max(
        (c for c in claims if c["status"] == "overdue"),
        key=lambda c: Decimal(c["variance"]),
    )["id"]
    evidence = client.get(f"/api/mfp/claims/{hero_id}/evidence").json()
    assert evidence["letter"] is not None
    assert evidence["reconciliation"]["finding"]["code"] == "MFP_REFUND_OVERDUE"
    assert client.get("/api/mfp/claims/NOPE/evidence").status_code == 404
