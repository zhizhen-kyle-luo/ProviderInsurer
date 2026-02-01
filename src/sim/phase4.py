from __future__ import annotations
from typing import Any, Dict, List, Optional
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

    metrics = _calculate_metrics(state)
    state.friction_metrics = metrics

    if audit_logger:
        audit_logger.log(
            phase=state.phase,
            turn=0,
            kind="metrics_calculated",
            payload={"metrics": metrics.model_dump()}
        )
        audit_logger.log(phase=state.phase, turn=0, kind="phase_end", payload={})

    return state


def _count_pends_in_responses(responses: List[Dict[str, Any]]) -> int:
    count = 0
    for resp in responses:
        if not isinstance(resp, dict):
            continue
        pay = resp.get("payor_response")
        if not isinstance(pay, dict):
            continue
        line_adjs = pay.get("line_adjudications")
        if not isinstance(line_adjs, list):
            continue
        for adj in line_adjs:
            if not isinstance(adj, dict):
                continue
            st = (adj.get("authorization_status") or adj.get("adjudication_status") or "").lower()
            if st == "pending_info":
                count += 1
    return count


def _calculate_metrics(state: EncounterState) -> FrictionMetrics:
    metrics = FrictionMetrics()
    lines = getattr(state, "service_lines", []) or []

    metrics.total_lines_requested = len([l for l in lines if not l.superseded_by_line])

    for line in lines:
        if line.superseded_by_line:
            continue
        _update_line_metrics(metrics, line)

    phase2_submissions = getattr(state, "phase2_submissions", []) or []
    phase2_responses = getattr(state, "phase2_responses", []) or []
    phase3_submissions = getattr(state, "phase3_submissions", []) or []
    phase3_responses = getattr(state, "phase3_responses", []) or []

    metrics.phase2_turns = len(phase2_submissions)
    metrics.phase3_turns = len(phase3_submissions)
    metrics.phase2_pends = _count_pends_in_responses(phase2_responses)
    metrics.phase3_pends = _count_pends_in_responses(phase3_responses)

    return metrics


def _update_line_metrics(metrics: FrictionMetrics, line) -> None:
    if line.authorization_status == "approved":
        metrics.lines_approved_phase2 += 1
    elif line.authorization_status == "denied":
        metrics.lines_denied_phase2 += 1
    elif line.authorization_status == "modified":
        metrics.lines_modified_phase2 += 1
        if line.accepted_modification:
            metrics.lines_modified_accepted += 1

    if line.delivered:
        metrics.lines_delivered += 1

    if line.adjudication_status == "approved":
        metrics.lines_paid_phase3 += 1
    elif line.adjudication_status == "denied":
        metrics.lines_denied_phase3 += 1

    metrics.phase2_appeals = max(metrics.phase2_appeals, int(line.current_review_level))
    metrics.phase3_appeals = max(metrics.phase3_appeals, int(line.claims_review_level))
    metrics.max_appeal_level_reached = max(
        metrics.max_appeal_level_reached,
        int(line.current_review_level),
        int(line.claims_review_level)
    )
