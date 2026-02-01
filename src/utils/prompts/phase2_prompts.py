from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple
from .workflow_prompts import WORKFLOW_ACTION_DEFINITIONS
from .prompt_renderers import render_line_summary
from .config import PROVIDER_STRATEGY_GUIDANCE, PAYOR_STRATEGY_GUIDANCE
from .schema_definitions import (
    PHASE2_PROVIDER_REQUEST_SCHEMA,
    PHASE2_PROVIDER_REQUEST_JSON,
    PHASE2_PAYOR_RESPONSE_SCHEMA,
    PHASE2_PAYOR_RESPONSE_JSON,
    PROVIDER_ACTION_SCHEMA,
    PROVIDER_ACTION_JSON,
)

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

    strategy_block = ""
    strategy = params.get("strategy")
    if strategy and strategy in PROVIDER_STRATEGY_GUIDANCE:
        strategy_block = f"\nSTRATEGY GUIDANCE:\n{PROVIDER_STRATEGY_GUIDANCE[strategy]}\n"

    return (
        "PHASE 2 PROVIDER SYSTEM PROMPT\n"
        "You are a hospital provider team preparing an authorization request for the insurer.\n"
        "Your goal: get medically necessary services approved by documenting clinical justification.\n"
        f"{strategy_block}"
        "Respond only with valid JSON matching the schema.\n"
        "For clinical_evidence: include patient demographics, symptoms, objective findings "
        "(labs/imaging), guideline citations, and step-therapy rationale.\n"
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
    """Provider prompt for building the insurer_request (submission). No action decision here."""
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
            action = r.get("provider_action", "")
            resubmit_reason = r.get("resubmit_reason", "")
            line_str = f"- level={lvl} decision={decision} reason={reason}"
            if action:
                line_str += f" | your_action={action}"
            if resubmit_reason:
                line_str += f" | resubmit_reason={resubmit_reason}"
            lines.append(line_str)
        prior_block = "\n" + "\n".join(lines) + "\n"

    service_lines_block = _render_service_lines_state(state)

    task_instruction = (
        "TASK\n"
        "Construct an insurer_request with service lines you wish to request or update.\n"
        "Include clinical_evidence for each line to justify medical necessity.\n"
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
        f"{PHASE2_PROVIDER_REQUEST_SCHEMA}\n"
        f"{PHASE2_PROVIDER_REQUEST_JSON}\n"
    )


def create_phase2_provider_action_prompt(
    state: object,
    payor_response: Dict[str, Any],
    *,
    provider_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Provider prompt for deciding action AFTER seeing payor's response.
    Returns (system_prompt, user_prompt).

    This is where the strategic choice happens:
    - Cooperate provider: accept modifications, provide docs promptly
    - Defect provider: appeal aggressively, push back on denials/modifications
    """
    params = provider_params or {}

    # System prompt with strategy
    strategy_block = ""
    strategy = params.get("strategy")
    if strategy and strategy in PROVIDER_STRATEGY_GUIDANCE:
        strategy_block = f"\nSTRATEGY GUIDANCE:\n{PROVIDER_STRATEGY_GUIDANCE[strategy]}\n"

    system_prompt = (
        "PHASE 2 PROVIDER ACTION DECISION\n"
        "You are the provider team deciding how to respond to the payor's decision.\n"
        f"{strategy_block}"
        "Respond only with valid JSON matching the schema.\n"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )

    # Render current line statuses after payor response was applied
    lines = getattr(state, "service_lines", []) or []
    line_status_parts = ["CURRENT LINE STATUSES (after payor decision):"]
    for l in lines:
        ln = getattr(l, "line_number", "?")
        code = getattr(l, "procedure_code", "")
        name = getattr(l, "service_name", "")
        status = getattr(l, "authorization_status", None) or "not_reviewed"
        level = getattr(l, "current_review_level", 0)
        docs = getattr(l, "requested_documents", []) or []
        reason = getattr(l, "decision_reason", "") or ""
        accepted = getattr(l, "accepted_modification", False)
        superseded = getattr(l, "superseded_by_line", None)

        line_str = f"- line {ln}: {code} {name} | status={status} | level={level}"
        if status == "modified":
            line_str += f" | accepted={accepted}"
        if status == "pending_info" and docs:
            line_str += f" | requested_docs={docs}"
        if reason:
            line_str += f" | reason={reason[:80]}"
        if superseded:
            line_str += f" | superseded_by={superseded}"
        line_status_parts.append(line_str)

    line_status_block = "\n".join(line_status_parts)

    # Include payor's response summary
    payor_adjs = payor_response.get("line_adjudications", [])
    payor_summary_parts = ["PAYOR'S DECISION THIS TURN:"]
    for adj in payor_adjs:
        if isinstance(adj, dict):
            ln = adj.get("line_number", "?")
            st = adj.get("authorization_status", "?")
            reason = adj.get("decision_reason", "")[:80] if adj.get("decision_reason") else ""
            payor_summary_parts.append(f"- line {ln}: {st} | {reason}")
    payor_summary_block = "\n".join(payor_summary_parts)

    user_prompt = (
        f"PHASE 2 PROVIDER ACTION PROMPT\n\n"
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
        "   Use when you DISAGREE with the coverage decision.\n\n"
        "3. RESUBMIT - withdraw PA entirely, submit new/corrected request\n"
        "   REQUIRED: Provide resubmit_reason explaining why.\n"
        "   Use for: wrong codes, missing diagnoses, want different services.\n"
        "   NOT a formal appeal - resets to level 0.\n\n"
        "4. ABANDON - stop pursuit entirely\n"
        "   REQUIRED: Set abandon_mode to NO_TREAT or TREAT_ANYWAY.\n\n"
        "INTENT VALUES (only 2 options, use exactly as shown):\n"
        "- \"PROVIDE_DOCS\" - for pending_info lines\n"
        "- \"ACCEPT_MODIFY\" - for modified lines\n\n"
        f"{PROVIDER_ACTION_SCHEMA}\n"
        "Return only valid JSON:\n"
        f"{PROVIDER_ACTION_JSON}\n"
    )

    return system_prompt, user_prompt


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

    strategy_block = ""
    strategy = params.get("strategy")
    if strategy and strategy in PAYOR_STRATEGY_GUIDANCE:
        strategy_block = f"\nSTRATEGY GUIDANCE:\n{PAYOR_STRATEGY_GUIDANCE[strategy]}\n"

    return (
        "PHASE 2 PAYOR SYSTEM PROMPT\n"
        "You are adjudicating an insurer_request.\n"
        "Return only valid JSON that matches the schema described.\n"
        "Be concise and criteria-driven.\n"
        f"{strategy_block}"
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
        f"{PHASE2_PAYOR_RESPONSE_SCHEMA}\n"
        f"{PHASE2_PAYOR_RESPONSE_JSON}\n"
        "Use tokens in workflow definitions exactly as defined."
    )
