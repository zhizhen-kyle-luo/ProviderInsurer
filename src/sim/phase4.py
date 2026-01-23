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

    lines_claimed = 0
    for line in lines:
        if line.superseded_by_line:
            continue

        if line.authorization_status == "approved":
            metrics.lines_approved_phase2 += 1
        elif line.authorization_status == "denied":
            metrics.lines_denied_phase2 += 1
        elif line.authorization_status == "modified":
            metrics.lines_modified_phase2 += 1

        if line.delivered:
            metrics.lines_delivered += 1

        if line.adjudication_status:
            lines_claimed += 1
            if line.adjudication_status == "approved":
                metrics.lines_paid_phase3 += 1
            elif line.adjudication_status == "denied":
                metrics.lines_denied_phase3 += 1

        if line.charge_amount:
            metrics.total_billed_amount += float(line.charge_amount)

        if line.paid_amount:
            metrics.total_paid_amount += float(line.paid_amount)

        metrics.max_appeal_level_reached = max(metrics.max_appeal_level_reached, int(line.current_review_level))

    if metrics.total_lines_requested > 0:
        metrics.authorization_denial_rate = metrics.lines_denied_phase2 / metrics.total_lines_requested

    if lines_claimed > 0:
        metrics.claim_denial_rate = metrics.lines_denied_phase3 / lines_claimed

    if metrics.total_billed_amount > 0:
        metrics.payment_ratio = metrics.total_paid_amount / metrics.total_billed_amount

    phase2_submissions = getattr(state, "phase2_submissions", []) or []
    metrics.phase2_turns = len(phase2_submissions)

    phase3_submissions = getattr(state, "phase3_submissions", []) or []
    metrics.phase3_turns = len(phase3_submissions)

    # oversight effort from submissions/responses
    for sub in phase2_submissions + phase3_submissions:
        if isinstance(sub, dict) and sub.get("oversight"):
            ov = sub["oversight"]
            if ov.get("role") == "provider":
                metrics.provider_review_tokens += int(ov.get("review", {}).get("view", {}).get("view_packet_tokens_proxy", 0))
                metrics.provider_edit_ops += len(ov.get("edit", {}).get("patch_ops", []) or [])

    phase2_responses = getattr(state, "phase2_responses", []) or []
    phase3_responses = getattr(state, "phase3_responses", []) or []
    for resp in phase2_responses + phase3_responses:
        if isinstance(resp, dict) and resp.get("oversight"):
            ov = resp["oversight"]
            if ov.get("role") == "payor":
                metrics.insurer_review_tokens += int(ov.get("review", {}).get("view", {}).get("view_packet_tokens_proxy", 0))
                metrics.insurer_edit_ops += len(ov.get("edit", {}).get("patch_ops", []) or [])

    return metrics
