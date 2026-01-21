from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .workflow_prompts import WORKFLOW_ACTION_DEFINITIONS

def _normalize_patient_visible_data(pv: object) -> Dict[str, Any]:
    if hasattr(pv, "model_dump"):
        pv = pv.model_dump()
    elif not isinstance(pv, dict):
        raise ValueError("state.patient_visible_data must be PatientVisibleData model or dict")

    required = ["patient_id", "age", "sex"]
    for key in required:
        if key not in pv:
            raise ValueError(f"patient_visible_data missing required field: {key}")
    return pv


def create_phase3_provider_system_prompt(provider_params: Optional[Dict[str, Any]] = None) -> str:
    _ = provider_params or {}
    return (
        "PHASE 3 PROVIDER SYSTEM PROMPT\n"
        "You are preparing a claim submission for services delivered.\n"
        "Include only delivered service lines with authorization numbers when available.\n"
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

    return (
        f"PHASE 3 PROVIDER USER PROMPT\n"
        f"Turn: {turn}\n"
        f"Review Level: {level}\n\n"
        "PATIENT:\n"
        f"- id: {pv['patient_id']}\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n\n"
        "DELIVERED SERVICE LINES:\n"
        f"{json.dumps(lines_summary, ensure_ascii=False, indent=2)}\n"
        f"{prior_block}\n"
        "TASK\n"
        "Construct a claim_submission with delivered service lines.\n"
        "Return only valid JSON, no extra keys.\n"
        "{\n"
        '  "claim_submission": {\n'
        '    "billed_lines": [\n'
        "      {\n"
        '        "line_number": <number>,\n'
        '        "procedure_code": "<code>",\n'
        '        "charge_amount": <float>,\n'
        '        "authorization_number": "<auth_num>",\n'
        '        "clinical_documentation": "<text>"\n'
        "      }\n"
        "    ],\n"
        '    "provider_notes": "<narrative>"\n'
        "  }\n"
        "}\n"
        "Use tokens in workflow definitions exactly as defined."
    )


def create_phase3_payor_system_prompt(payor_params: Optional[Dict[str, Any]] = None) -> str:
    _ = payor_params or {}
    return (
        "PHASE 3 PAYOR SYSTEM PROMPT\n"
        "You are adjudicating a clinical claim.\n"
        "Focus on match between billed services and documentation.\n"
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
        "{\n"
        '  "line_adjudications": [\n'
        "    {\n"
        '      "line_number": <number>,\n'
        '      "adjudication_status": "<approved|modified|denied|pending_info>",\n'
        '      "decision_reason": "<text>",\n'
        '      "allowed_amount": <float>,\n'
        '      "paid_amount": <float>,\n'
        '      "adjustment_group_code": "<CO|PR|OA>",\n'
        '      "adjustment_amount": <float>,\n'
        '      "requested_documents": ["<docs>"]\n'
        "    }\n"
        "  ],\n"
        '  "reviewer_type": "<string>",\n'
        f'  "level": {level}\n'
        "}\n"
        "Use tokens in workflow definitions exactly as defined."
    )
