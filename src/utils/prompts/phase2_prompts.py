from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from .workflow_prompts import WORKFLOW_ACTION_DEFINITIONS
from .prompt_renderers import render_line_summary

def _normalize_patient_visible_data(pv: object) -> Dict[str, Any]:
    if hasattr(pv, "model_dump"):
        pv = pv.model_dump()
    elif not isinstance(pv, dict):
        raise ValueError("state.patient_visible_data must be PatientVisibleData model or dict")

    required = [
        "patient_id", "age", "sex", "admission_source",
        "chief_complaint", "medical_history", "medications",
        "vital_signs"
    ]
    for key in required:
        if key not in pv:
            raise ValueError(f"patient_visible_data missing required field: {key}")
    return pv


def _render_policy_data(data: Dict[str, Any], indent: int = 0) -> str:
    """render policy data dict as readable text"""
    lines = []
    prefix = "  " * indent
    for k, v in data.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_render_policy_data(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{prefix}{k}:")
            for item in v:
                if isinstance(item, dict):
                    lines.append(_render_policy_data(item, indent + 1))
                else:
                    lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}{k}: {v}")
    return "\n".join(lines)


def create_phase2_provider_system_prompt(provider_params: Optional[Dict[str, Any]] = None) -> str:
    params = provider_params or {}
    policy_block = ""
    if params.get("policy"):
        policy = params["policy"]
        policy_block = (
            "\nCLINICAL GUIDELINES:\n"
            f"Source: {policy.get('issuer', 'Unknown')}\n"
        )
        data = policy.get("content", {}).get("data", {})
        if data:
            policy_block += _render_policy_data(data) + "\n"
    return (
        "PHASE 2 PROVIDER SYSTEM PROMPT\n"
        "You are preparing an insurer authorization request.\n"
        "Respond only with valid JSON that matches the schema described.\n"
        "Be precise. For clinical_evidence: include patient demographics, symptoms, objective findings (labs/imaging), guideline citations, and step-therapy rationale. Do not abbreviate clinical justification.\n"
        f"{policy_block}"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )

def _render_service_lines_state(state: object) -> str:
    """render current service lines with their authorization status"""
    lines = getattr(state, "service_lines", []) or []
    if not lines:
        return ""

    parts = ["CURRENT SERVICE LINES STATE:"]
    for l in lines:
        ln = getattr(l, "line_number", "?")
        code = getattr(l, "procedure_code", "")
        name = getattr(l, "service_name", "")
        status = getattr(l, "authorization_status", None) or "not_reviewed"
        docs = getattr(l, "requested_documents", []) or []
        reason = getattr(l, "decision_reason", "") or ""

        line_str = f"- line {ln}: {code} {name} | status={status}"
        if status == "pending_info" and docs:
            line_str += f" | requested_docs={docs}"
        if reason:
            line_str += f" | reason={reason[:100]}"
        parts.append(line_str)

    return "\n".join(parts) + "\n"


def create_phase2_provider_user_prompt(
    state: object,
    *,
    turn: int,
    level: int,
    prior_rounds: Optional[List[Dict[str, Any]]] = None
) -> str:
    prior_rounds = prior_rounds or []
    pv = _normalize_patient_visible_data(getattr(state, "patient_visible_data", None))
    vitals = pv.get("vital_signs", {}) or {}
    labs = pv.get("lab_results", {}) or {}

    prior_block = ""
    if prior_rounds:
        lines = ["PRIOR ROUND SUMMARY:"]
        for r in prior_rounds:
            lvl = r.get("level")
            decision = r.get("payor_decision", "")
            reason = r.get("payor_decision_reason", "")
            lines.append(f"- level={lvl} decision={decision} reason={reason}")
        prior_block = "\n" + "\n".join(lines) + "\n"

    service_lines_block = _render_service_lines_state(state)

    # different instructions for turn 0 vs continuation
    if turn == 0 or not service_lines_block:
        task_instruction = (
            "TASK\n"
            "Construct an insurer_request with ALL service lines you wish to request.\n"
            "Include all desired services upfront; do not plan to add more lines in later submissions.\n"
        )
    else:
        task_instruction = (
            "TASK\n"
            "Resubmit the insurer_request with lines that require action.\n"
            "- For pending_info lines: include with clinical_evidence addressing requested_documents\n"
            "- For denied lines: include only if appealing with new evidence\n"
            "- Do NOT include approved lines (already authorized, no resubmission needed)\n"
        )

    return (
        f"PHASE 2 PROVIDER USER PROMPT\n"
        f"Turn: {turn}\n"
        f"Review Level: {level}\n\n"
        "PATIENT (provider-visible):\n"
        f"- id: {pv['patient_id']}\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n"
        f"- chief_complaint: {pv['chief_complaint']}\n"
        f"- vitals: {json.dumps(vitals, ensure_ascii=False)}\n"
        f"- labs: {json.dumps(labs, ensure_ascii=False)}\n"
        f"{prior_block}"
        f"{service_lines_block}\n"
        f"{task_instruction}"
        "Return only valid JSON, no extra keys.\n"
        "{\n"
        '  "insurer_request": {\n'
        '    "diagnosis_codes": [{"icd10":"<code>","description":"<text>"}],\n'
        '    "requested_services": [\n'
        "      {\n"
        '        "line_number": 1,\n'
        '        "request_type": "<type>",\n'
        '        "procedure_code": "<code>",\n'
        '        "code_type": "<qualifier>",\n'
        '        "service_name": "<name>",\n'
        '        "service_description": "<description>",\n'
        '        "requested_quantity": <number>,\n'
        '        "quantity_unit": "<unit>",\n'
        '        "site_of_service": "<site>",\n'
        '        "clinical_evidence": "<text>"\n'
        "      }\n"
        "    ],\n"
        '    "clinical_notes": "<H&P narrative>"\n'
        "  }\n"
        "}\n"
        "Use tokens in workflow definitions exactly as defined."
    )


def create_phase2_payor_system_prompt(payor_params: Optional[Dict[str, Any]] = None) -> str:
    params = payor_params or {}
    policy_block = ""
    if params.get("policy"):
        policy = params["policy"]
        policy_block = (
            "\nCOVERAGE POLICY:\n"
            f"Source: {policy.get('issuer', 'Unknown')}\n"
        )
        data = policy.get("content", {}).get("data", {})
        if data:
            policy_block += _render_policy_data(data) + "\n"
    return (
        "PHASE 2 PAYOR SYSTEM PROMPT\n"
        "You are adjudicating an insurer_request.\n"
        "Return only valid JSON that matches the schema described.\n"
        "Be concise and criteria-driven.\n"
        f"{policy_block}"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )

def create_phase2_payor_user_prompt(
    state: object,
    insurer_request: Dict[str, Any],
    *,
    turn: int,
    level: int,
    pend_count_at_level: int = 0
) -> str:
    import json
    from .config import MAX_REQUEST_INFO_PER_LEVEL

    pv = _normalize_patient_visible_data(getattr(state, "patient_visible_data", None))
    request_json = json.dumps(insurer_request, ensure_ascii=False)

    pend_rule = (
        "" if level < 2 else
        "RULE: pending_info is NOT allowed at this level; decide another status.\n"
    )

    return (
        f"PHASE 2 PAYOR USER PROMPT\n"
        f"Turn: {turn}\n"
        f"Review Level: {level}\n"
        f"Pend count at this level: {pend_count_at_level}\n\n"
        "PATIENT SUMMARY:\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n"
        f"- chief_complaint: {pv['chief_complaint']}\n\n"
        "INSURER REQUEST:\n"
        f"{request_json}\n\n"
        f"{pend_rule}"
        "TASK\n"
        "Adjudicate each requested_service line.\n"
        "Return only valid JSON.\n"
        "{\n"
        '  "line_adjudications": [\n'
        "    {\n"
        '      "line_number": <number>,\n'
        '      "authorization_status": "<approved|modified|denied|pending_info>",\n'
        '      "decision_reason": "<text>",\n'
        '      "approved_quantity": <number>,\n'
        '      "authorization_number": "<id>",\n'
        '      "modification_type": "<text>",\n'
        '      "requested_documents": ["<docs>"]\n'
        "    }\n"
        "  ],\n"
        '  "reviewer_type": "<string>",\n'
        f'  "level": {level}\n'
        "}\n"
        "Use tokens in workflow definitions exactly as defined."
    )
