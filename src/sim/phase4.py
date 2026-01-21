from __future__ import annotations
from typing import Optional
from src.models.state import EncounterState
from src.models.metrics import FrictionMetrics
from src.utils.audit_logger import AuditLogger


def run_phase4(
    *,
    state: EncounterState,
    audit_logger: Optional[AuditLogger] = None,
) -> EncounterState:
    state.phase = "phase_4_financial"
    state.turn = 0

    if audit_logger:
        audit_logger.log(phase=state.phase, turn=0, kind="phase_start", payload={})

    metrics = _calculate_financial_metrics(state)
    state.friction_metrics = metrics

    if audit_logger:
        audit_logger.log(
            phase=state.phase,
            turn=0,
            kind="metrics_calculated",
            payload={"metrics": metrics.model_dump()}
        )

    if audit_logger:
        audit_logger.log(phase=state.phase, turn=0, kind="phase_end", payload={})

    return state


def _calculate_financial_metrics(state: EncounterState) -> FrictionMetrics:
    metrics = FrictionMetrics()

    lines = getattr(state, "service_lines", []) or []

    metrics.total_lines_requested = len([l for l in lines if not l.superseded_by_line])

    for line in lines:
        if line.superseded_by_line:
            continue

        if line.authorization_status == "approved":
            metrics.lines_approved_phase2 += 1
        elif line.authorization_status == "denied":
            metrics.lines_denied_phase2 += 1
        elif line.authorization_status == "modified":
            metrics.lines_modified_phase2 += 1
        elif line.authorization_status == "pending_info":
            metrics.lines_pending_final_phase2 += 1

        if line.delivered:
            metrics.lines_delivered += 1

        if line.adjudication_status:
            metrics.lines_claimed += 1
            if line.adjudication_status == "approved":
                metrics.lines_paid_phase3 += 1
            elif line.adjudication_status == "denied":
                metrics.lines_denied_phase3 += 1
            elif line.adjudication_status == "modified":
                metrics.lines_modified_phase3 += 1

        if line.charge_amount:
            metrics.total_billed_amount += float(line.charge_amount)

        if line.approved_quantity and line.authorization_status in {"approved", "modified"}:
            metrics.total_authorized_amount += float(line.charge_amount or 0.0)

        if line.allowed_amount:
            metrics.total_allowed_amount += float(line.allowed_amount)

        if line.paid_amount:
            metrics.total_paid_amount += float(line.paid_amount)

        if line.adjustment_amount:
            metrics.total_adjustment_amount += float(line.adjustment_amount)

        metrics.pend_rounds_total += int(line.pend_total)
        metrics.max_appeal_level_reached = max(metrics.max_appeal_level_reached, int(line.current_review_level))

    if metrics.total_lines_requested > 0:
        metrics.authorization_denial_rate = metrics.lines_denied_phase2 / metrics.total_lines_requested

    if metrics.lines_claimed > 0:
        metrics.claim_denial_rate = metrics.lines_denied_phase3 / metrics.lines_claimed

    if metrics.total_billed_amount > 0:
        metrics.payment_ratio = metrics.total_paid_amount / metrics.total_billed_amount

    phase2_submissions = getattr(state, "phase2_submissions", []) or []
    phase2_responses = getattr(state, "phase2_responses", []) or []
    metrics.phase2_turns = len(phase2_submissions)

    for resp in phase2_responses:
        if isinstance(resp, dict):
            pay = resp.get("payor_response")
            if isinstance(pay, dict):
                line_adjs = pay.get("line_adjudications")
                if isinstance(line_adjs, list):
                    metrics.insurer_line_decisions_total += len(line_adjs)
                    for adj in line_adjs:
                        if isinstance(adj, dict):
                            st = (adj.get("authorization_status") or "").lower()
                            if st == "approved":
                                metrics.insurer_approve += 1
                            elif st == "denied":
                                metrics.insurer_deny += 1
                            elif st == "pending_info":
                                metrics.insurer_pend += 1
                            elif st == "modified":
                                metrics.insurer_modify += 1

    phase3_submissions = getattr(state, "phase3_submissions", []) or []
    metrics.phase3_turns = len(phase3_submissions)

    if state.care_abandoned:
        metrics.provider_abandoned = True

    return metrics
