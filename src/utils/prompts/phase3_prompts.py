from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .workflow_prompts import WORKFLOW_ACTION_DEFINITIONS
from .config import PROVIDER_STRATEGY_GUIDANCE, PAYOR_STRATEGY_GUIDANCE
from .schema_definitions import (
    PHASE3_PROVIDER_CLAIM_SCHEMA,
    PHASE3_PROVIDER_CLAIM_JSON,
    PHASE3_PAYOR_RESPONSE_SCHEMA,
    PHASE3_PAYOR_RESPONSE_JSON,
    PROVIDER_ACTION_SCHEMA,
    PROVIDER_ACTION_JSON,
)

def _normalize_patient_visible_data(pv: object) -> Dict[str, Any]:
    if hasattr(pv, "model_dump"):
        pv = pv.model_dump()
    elif not isinstance(pv, dict):
        raise ValueError("state.patient_visible_data must be PatientVisibleData model or dict")

    required = ["patient_id", "age", "sex", "chief_complaint"]
    for key in required:
        if key not in pv:
            raise ValueError(f"patient_visible_data missing required field: {key}")
    return pv


def create_phase3_provider_system_prompt(provider_params: Optional[Dict[str, Any]] = None) -> str:
    params = provider_params or {}
    strategy_block = ""
    strategy = params.get("strategy")
    if strategy and strategy in PROVIDER_STRATEGY_GUIDANCE:
        strategy_block = f"\nSTRATEGY GUIDANCE:\n{PROVIDER_STRATEGY_GUIDANCE[strategy]}\n"

    return (
        "PHASE 3 PROVIDER SYSTEM PROMPT\n"
        "You are preparing a claim submission for services delivered.\n"
        "Include only delivered service lines with authorization numbers when available.\n"
        "CRITICAL: Use the exact procedure_code from the delivered service lines. Do not substitute codes.\n"
        f"{strategy_block}"
        "Respond only with valid JSON that matches the schema described.\n"
        "Be precise and concise.\n"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )


def create_phase3_provider_user_prompt(
    state: object,
    *,
    turn: int,
    level: int,
    prior_rounds: Optional[List[Dict[str, Any]]] = None
) -> str:
    prior_rounds = prior_rounds or []
    pv = _normalize_patient_visible_data(getattr(state, "patient_visible_data", None))

    lines = getattr(state, "service_lines", []) or []
    delivered_lines = [l for l in lines if getattr(l, "delivered", False)]

    lines_summary = []
    for l in delivered_lines:
        lines_summary.append({
            "line_number": l.line_number,
            "procedure_code": l.procedure_code,
            "service_name": l.service_name,
            "requested_quantity": l.requested_quantity,
            "charge_amount": l.charge_amount,
            "authorization_number": l.authorization_number,
            "authorization_status": l.authorization_status,
        })

    prior_block = ""
    if prior_rounds:
        plines = ["PRIOR ROUND SUMMARY:"]
        for r in prior_rounds:
            lvl = r.get("level")
            decision = r.get("payor_decision", "")
            reason = r.get("payor_decision_reason", "")
            plines.append(f"- level={lvl} decision={decision} reason={reason}")
        prior_block = "\n" + "\n".join(plines) + "\n"

    # current claim state for turn 2+
    current_state_block = ""
    phase3_submissions = getattr(state, "phase3_submissions", []) or []
    phase3_responses = getattr(state, "phase3_responses", []) or []
    is_continuation = bool(phase3_submissions and phase3_responses)
    if is_continuation:
        last_sub = phase3_submissions[-1]
        last_resp = phase3_responses[-1]
        current_state_lines = ["CURRENT CLAIM STATE:"]
        if isinstance(last_sub, dict) and last_sub.get("claim_submission"):
            current_state_lines.append(f"Last submission: {json.dumps(last_sub['claim_submission'], ensure_ascii=False)}")
        if isinstance(last_resp, dict) and last_resp.get("payor_response"):
            pay_resp = last_resp["payor_response"]
            current_state_lines.append(f"Last payor response: {json.dumps(pay_resp, ensure_ascii=False)}")
        # per-line adjudication status
        adj_summary = []
        for l in delivered_lines:
            adj_summary.append({
                "line_number": l.line_number,
                "adjudication_status": getattr(l, "adjudication_status", None),
                "claims_review_level": getattr(l, "claims_review_level", 0),
                "decision_reason": getattr(l, "decision_reason", None),
            })
        current_state_lines.append(f"Current line statuses: {json.dumps(adj_summary, ensure_ascii=False)}")
        current_state_block = "\n" + "\n".join(current_state_lines) + "\n"

    task_instruction = (
        "TASK\n"
        "Construct a claim_submission with delivered service lines.\n"
        "Include clinical_documentation for each line.\n"
    )

    return (
        f"PHASE 3 PROVIDER USER PROMPT\n"
        f"Turn: {turn}\n"
        f"Review Level: {level}\n\n"
        "PATIENT:\n"
        f"- id: {pv['patient_id']}\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n"
        f"- chief_complaint: {pv['chief_complaint']}\n\n"
        "DELIVERED SERVICE LINES:\n"
        f"{json.dumps(lines_summary, ensure_ascii=False, indent=2)}\n"
        f"{prior_block}"
        f"{current_state_block}\n"
        f"{task_instruction}"
        "Return only valid JSON, no extra keys.\n"
        f"{PHASE3_PROVIDER_CLAIM_SCHEMA}\n"
        f"{PHASE3_PROVIDER_CLAIM_JSON}\n"
    )


def create_phase3_provider_action_prompt(
    state: object,
    payor_response: Dict[str, Any],
    *,
    provider_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Provider prompt for deciding action AFTER seeing payor's response in Phase 3.
    Returns (system_prompt, user_prompt).
    """
    params = provider_params or {}

    # System prompt with strategy
    strategy_block = ""
    strategy = params.get("strategy")
    if strategy and strategy in PROVIDER_STRATEGY_GUIDANCE:
        strategy_block = f"\nSTRATEGY GUIDANCE:\n{PROVIDER_STRATEGY_GUIDANCE[strategy]}\n"

    system_prompt = (
        "PHASE 3 PROVIDER ACTION DECISION\n"
        "You are the provider team deciding how to respond to the payor's claim adjudication.\n"
        f"{strategy_block}"
        "Respond only with valid JSON matching the schema.\n"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )

    # Render current line statuses after payor response was applied
    lines = getattr(state, "service_lines", []) or []
    delivered_lines = [l for l in lines if getattr(l, "delivered", False)]

    line_status_parts = ["CURRENT LINE STATUSES (after payor decision):"]
    for l in delivered_lines:
        ln = getattr(l, "line_number", "?")
        code = getattr(l, "procedure_code", "")
        name = getattr(l, "service_name", "")
        status = getattr(l, "adjudication_status", None) or "not_reviewed"
        level = getattr(l, "claims_review_level", 0)
        reason = getattr(l, "decision_reason", "") or ""
        accepted = getattr(l, "accepted_modification", False)

        line_str = f"- line {ln}: {code} {name} | status={status} | level={level}"
        if status == "modified":
            line_str += f" | accepted={accepted}"
        if reason:
            line_str += f" | reason={reason[:80]}"
        line_status_parts.append(line_str)

    line_status_block = "\n".join(line_status_parts)

    # Include payor's response summary
    payor_adjs = payor_response.get("line_adjudications", [])
    payor_summary_parts = ["PAYOR'S DECISION THIS TURN:"]
    for adj in payor_adjs:
        if isinstance(adj, dict):
            ln = adj.get("line_number", "?")
            st = adj.get("adjudication_status", "?")
            reason = adj.get("decision_reason", "")[:80] if adj.get("decision_reason") else ""
            payor_summary_parts.append(f"- line {ln}: {st} | {reason}")
    payor_summary_block = "\n".join(payor_summary_parts)

    user_prompt = (
        f"PHASE 3 PROVIDER ACTION PROMPT\n\n"
        f"{line_status_block}\n\n"
        f"{payor_summary_block}\n\n"
        "TASK: Choose ONE action and provide per-line details where required.\n\n"
        "ACTION OPTIONS:\n"
        "1. CONTINUE - proceed without escalating review level\n"
        "   REQUIRED: For each non-approved line, include in 'lines' array:\n"
        "   - pending_info lines: {\"line_number\": X, \"intent\": \"PROVIDE_DOCS\"}\n"
        "   - modified lines you accept: {\"line_number\": X, \"intent\": \"ACCEPT_MODIFY\"}\n"
        "   (approved lines need no entry)\n\n"
        "2. APPEAL - escalate denied/modified lines to next review level\n"
        "   REQUIRED: For each line you appeal, include in 'lines' array:\n"
        "   - {\"line_number\": X, \"to_level\": <current_level + 1>}\n"
        "   Use when you DISAGREE with the payment decision.\n\n"
        "3. ABANDON - stop pursuit entirely\n"
        "   REQUIRED: Set abandon_mode to WRITE_OFF.\n\n"
        "INTENT VALUES (only 2 options, use exactly as shown):\n"
        "- \"PROVIDE_DOCS\" - for pending_info lines\n"
        "- \"ACCEPT_MODIFY\" - for modified lines\n\n"
        f"{PROVIDER_ACTION_SCHEMA}\n"
        "Return only valid JSON:\n"
        f"{PROVIDER_ACTION_JSON}\n"
    )

    return system_prompt, user_prompt


def create_phase3_payor_system_prompt(payor_params: Optional[Dict[str, Any]] = None) -> str:
    params = payor_params or {}
    strategy_block = ""
    strategy = params.get("strategy")
    if strategy and strategy in PAYOR_STRATEGY_GUIDANCE:
        strategy_block = f"\nSTRATEGY GUIDANCE:\n{PAYOR_STRATEGY_GUIDANCE[strategy]}\n"

    return (
        "PHASE 3 PAYOR SYSTEM PROMPT\n"
        "You are adjudicating a clinical claim.\n"
        "Focus on match between billed services and documentation.\n"
        f"{strategy_block}"
        "Return only valid JSON matching the schema for claim response.\n"
        "Be concise and criteria-based.\n"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )


def create_phase3_payor_user_prompt(
    state: object,
    claim_obj: Dict[str, Any],
    *,
    turn: int,
    level: int = 0,
    pend_count_at_level: int = 0
) -> str:
    from .config import MAX_REQUEST_INFO_PER_LEVEL

    pv = _normalize_patient_visible_data(getattr(state, "patient_visible_data", None))
    claim_text = json.dumps(claim_obj, ensure_ascii=False, indent=2)

    pend_rule = (
        "" if level < 2 else
        "RULE: pending_info is NOT allowed at this level; decide another status.\n"
    )

    return (
        f"PHASE 3 PAYOR USER PROMPT\n"
        f"Turn: {turn}\n"
        f"Review Level: {level}\n"
        f"Pend count at this level: {pend_count_at_level}\n\n"
        "PATIENT SUMMARY:\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n\n"
        "CLAIM DATA:\n"
        f"{claim_text}\n\n"
        f"{pend_rule}"
        "TASK\n"
        "Adjudicate billed service lines.\n"
        "Return only valid JSON.\n"
        f"{PHASE3_PAYOR_RESPONSE_SCHEMA}\n"
        f"{PHASE3_PAYOR_RESPONSE_JSON}\n"
        "Use tokens in workflow definitions exactly as defined."
    )
