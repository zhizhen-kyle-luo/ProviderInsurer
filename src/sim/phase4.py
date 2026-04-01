from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.models.state import EncounterState
from src.models.metrics import FrictionMetrics, PolicyReference, EnvironmentConfig
from src.utils.audit_logger import AuditLogger


def run_phase4(
    *,
    state: EncounterState,
    provider_params: Optional[Dict[str, Any]] = None,
    payor_params: Optional[Dict[str, Any]] = None,
    environment_config: Optional[Dict[str, Any]] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> EncounterState:
    state.phase = "phase_4_financial"
    state.turn = 0

    if audit_logger:
        audit_logger.log(phase=state.phase, turn=0, kind="phase_start", payload={})

    metrics = _calculate_metrics(state)

    # add policy references
    if provider_params and provider_params.get("policy"):
        p = provider_params["policy"]
        metrics.provider_policy = PolicyReference(
            policy_id=p.get("policy_id", ""),
            issuer=p.get("issuer", ""),
            source=p.get("source"),
        )
    if payor_params and payor_params.get("policy"):
        p = payor_params["policy"]
        metrics.payor_policy = PolicyReference(
            policy_id=p.get("policy_id", ""),
            issuer=p.get("issuer", ""),
            source=p.get("source"),
        )

    # add environment config
    if environment_config:
        metrics.environment_config = EnvironmentConfig(
            allow_synthesis=environment_config.get("allow_synthesis", True),
            synthesis_model=environment_config.get("synthesis_model"),
        )

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



def _calculate_metrics(state: EncounterState) -> FrictionMetrics:
    from src.data.pricing.cms_rates import (
        lookup_rate,
        UnknownProcedureCodeError,
        check_code_match,
        get_description,
        ADMIN_COST_PROVIDER_L0,
        ADMIN_COST_INSURER_L0,
        ADMIN_COST_PROVIDER_L12,
        ADMIN_COST_INSURER_L12,
        IRE_CASE_COST,
        PROMPT_PAY_RATE,
        REVIEW_DELAY_DAYS,
    )

    metrics = FrictionMetrics()
    lines = getattr(state, "service_lines", []) or []

    metrics.total_lines_requested = len([l for l in lines if not l.superseded_by_line])

    unpriced: List[str] = []
    hallucination_warnings: List[str] = []
    line_pricing: List[Dict[str, Any]] = []
    total_service_value = 0.0
    total_reimbursement = 0.0
    insurer_exposure = 0.0  # S^I: value of lines submitted to insurer (excludes treat_anyway)

    for line in lines:
        if line.superseded_by_line:
            continue

        if line.authorization_status == "approved":
            metrics.lines_approved_phase2 += 1
        elif line.authorization_status == "denied":
            metrics.lines_denied_phase2 += 1
        elif line.authorization_status == "modified":
            metrics.lines_modified_phase2 += 1
            if getattr(line, "accepted_modification", False):
                metrics.lines_modified_accepted += 1

        if line.delivered:
            metrics.lines_delivered += 1

        if line.adjudication_status:
            if line.adjudication_status == "approved":
                metrics.lines_paid_phase3 += 1
            elif line.adjudication_status == "denied":
                metrics.lines_denied_phase3 += 1

        metrics.max_appeal_level_reached = max(
            metrics.max_appeal_level_reached, int(line.current_review_level)
        )

        code = line.procedure_code
        qty = line.requested_quantity

        try:
            rate = lookup_rate(code)
        except UnknownProcedureCodeError:
            unpriced.append(code)
            rate = None

        is_consistent, warning = check_code_match(code, line.service_name)
        if warning:
            hallucination_warnings.append(warning)

        sv = rate * qty if rate is not None and qty > 0 else 0.0
        total_service_value += sv

        # insurer exposure excludes treat_anyway lines (provider-absorbed, not insurer liability)
        if not getattr(line, "treat_anyway", False):
            insurer_exposure += sv

        paid_value = 0.0
        if line.adjudication_status == "approved" and rate is not None:
            paid_qty = line.approved_quantity if line.approved_quantity else qty
            paid_value = rate * paid_qty

        total_reimbursement += paid_value

        line_pricing.append({
            "line_number": line.line_number,
            "procedure_code": code,
            "service_name": line.service_name,
            "official_description": get_description(code),
            "is_consistent": is_consistent,
            "hallucination_warning": warning,
            "requested_quantity": qty,
            "rate": rate,
            "service_value": round(sv, 2),
            "paid": line.adjudication_status == "approved",
            "paid_value": round(paid_value, 2),
        })

    phase2_submissions = getattr(state, "phase2_submissions", []) or []
    metrics.phase2_turns = len(phase2_submissions)

    phase3_submissions = getattr(state, "phase3_submissions", []) or []
    metrics.phase3_turns = len(phase3_submissions)

    phase2_responses = getattr(state, "phase2_responses", []) or []
    phase3_submissions = getattr(state, "phase3_submissions", []) or []
    phase3_responses = getattr(state, "phase3_responses", []) or []

    metrics.phase2_appeals, metrics.phase2_pends = _count_appeals_and_pends(phase2_responses)
    metrics.phase3_appeals, metrics.phase3_pends = _count_appeals_and_pends(phase3_responses)

    # level-differentiated admin costs (CAQH 2023): L0+Phase3 at electronic rate, L1-2 at manual rate
    # count turns by level from phase2 responses
    phase2_responses = getattr(state, "phase2_responses", []) or []
    n_l0 = sum(1 for r in phase2_responses if isinstance(r, dict) and int(r.get("level", 0)) == 0)
    n_l12 = sum(1 for r in phase2_responses if isinstance(r, dict) and int(r.get("level", 0)) > 0)
    n_phase3 = metrics.phase3_turns  # phase3 claims adjudication at electronic rate

    admin_p = (n_l0 + n_phase3) * ADMIN_COST_PROVIDER_L0 + n_l12 * ADMIN_COST_PROVIDER_L12
    admin_i = (n_l0 + n_phase3) * ADMIN_COST_INSURER_L0 + n_l12 * ADMIN_COST_INSURER_L12

    # IRE reversal costs: F_IRE if case reached L2; prompt-pay interest if IRE overturned denial
    ire_cost = 0.0
    if metrics.max_appeal_level_reached >= 2:
        ire_cost += IRE_CASE_COST
        # prompt-pay interest applies when IRE overturns and insurer must pay retroactively
        if total_reimbursement > 0:
            ire_cost += PROMPT_PAY_RATE * total_reimbursement * REVIEW_DELAY_DAYS / 365

    metrics.total_service_value = round(total_service_value, 2)
    metrics.total_reimbursement = round(total_reimbursement, 2)
    metrics.total_admin_cost_provider = round(admin_p, 2)
    metrics.total_admin_cost_insurer = round(admin_i, 2)
    metrics.provider_utility = round(total_reimbursement - admin_p, 2)
    metrics.insurer_utility = round(insurer_exposure - total_reimbursement - admin_i - ire_cost, 2)
    metrics.line_pricing = line_pricing
    metrics.unpriced_codes = sorted(set(unpriced))
    metrics.hallucination_warnings = hallucination_warnings

    return metrics


def _count_appeals_and_pends(responses: list) -> tuple:
    appeals = 0
    pends = 0
    prev_level = 0

    for resp in responses:
        if not isinstance(resp, dict):
            continue

        current_level = int(resp.get("level", 0))
        if current_level > prev_level:
            appeals += 1
        prev_level = current_level

        payor_resp = resp.get("payor_response")
        if not isinstance(payor_resp, dict):
            continue

        line_adjs = payor_resp.get("line_adjudications", [])
        if not isinstance(line_adjs, list):
            continue

        for adj in line_adjs:
            if not isinstance(adj, dict):
                continue
            status = (adj.get("authorization_status") or adj.get("adjudication_status") or "").lower()
            if status == "pending_info":
                pends += 1
                break  # count once per response, not per line

    return appeals, pends
