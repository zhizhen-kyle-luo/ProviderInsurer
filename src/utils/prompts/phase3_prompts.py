from __future__ import annotations
"""
Phase 3 (Claims) prompt construction.

CONTEXT ENGINEERING PRINCIPLES:
- System prompt = WHO you are, HOW you behave (stable across turns)
- User prompt = WHAT you're looking at, WHAT to do (changes per turn)

System prompt contains:
  - Role and goal
  - Behavioral guidelines (admin cost, strategy)
  - Domain knowledge (workflow definitions)

User prompt structure:
  1. TASK (what to do) - FIRST for clarity
  2. Context metadata (turn, level)
  3. Input data (patient, delivered lines on turn 0, history, current state)
  4. OUTPUT FORMAT (schema + JSON template) - LAST, closest to generation
"""

import json
from typing import Any, Dict, List, Optional

from .workflow_prompts import (
    WORKFLOW_ACTION_DEFINITIONS_PROVIDER,
    WORKFLOW_ACTION_DEFINITIONS_PAYOR,
)
from .config import PROVIDER_STRATEGY_GUIDANCE, PAYOR_STRATEGY_GUIDANCE
from .schema_definitions import (
    PHASE3_PROVIDER_CLAIM_SCHEMA,
    PHASE3_PROVIDER_CLAIM_JSON,
    PHASE3_PAYOR_RESPONSE_SCHEMA,
    PHASE3_PAYOR_RESPONSE_JSON,
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


def _render_policy_data(data: Dict[str, Any], indent: int = 0) -> str:
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


def create_phase3_provider_system_prompt(provider_params: Optional[Dict[str, Any]] = None) -> str:
    params = provider_params or {}
    guidance = PROVIDER_STRATEGY_GUIDANCE[params["strategy"]]
    strategy_block = f"\nSTRATEGY GUIDANCE:\n{guidance}\n" if guidance else ""

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

    coverage_policy_block = ""
    if params.get("coverage_policy"):
        coverage_policy = params["coverage_policy"]
        coverage_policy_block = (
            "\nPAYER COVERAGE POLICY (for reference):\n"
            f"Source: {coverage_policy.get('issuer', 'Unknown')}\n"
        )
        data = coverage_policy.get("content", {}).get("data", {})
        if data:
            coverage_policy_block += _render_policy_data(data) + "\n"

    return (
        "You are a hospital provider team submitting claims for delivered services.\n"
        "Your goal: get delivered services paid by matching claims to authorization and documentation.\n"
        "\nADMINISTRATIVE COST CONSIDERATION:\n"
        "Claim submission costs ~$6 (manual) to ~$3 (electronic) per claim (CAQH 2023). "
        "Fighting a denied claim costs ~$57 in staff time (Premier 2023). "
        "Corrected claims must be filed within 60-120 days of denial.\n\n"
        "RESUBMIT only when:\n"
        "- You made an error (wrong codes, incorrect authorization references)\n"
        "- You CAN correct what caused the denial\n\n"
        "APPEAL or ABANDON when:\n"
        "- Payor misapplied policy or ignored documentation already provided\n"
        "- Prior resubmission was denied for the same reason\n\n"
        "If the underlying facts cannot change, resubmitting will fail again.\n"
        f"{strategy_block}"
        f"{policy_block}"
        f"{coverage_policy_block}"
        f"\n{WORKFLOW_ACTION_DEFINITIONS_PROVIDER}"
    )


def create_phase3_provider_user_prompt(
    state: object,
    *,
    turn: int,
    level: int,
    prior_rounds: Optional[List[Dict[str, Any]]] = None
) -> str:
    if prior_rounds is None:
        prior_rounds = []
    pv = _normalize_patient_visible_data(state.patient_visible_data)

    lines = state.service_lines
    if lines is None:
        raise ValueError("state.service_lines is None")
    delivered_lines = [l for l in lines if getattr(l, "delivered", False)]

    lines_summary = []
    for l in delivered_lines:
        lines_summary.append({
            "line_number": l.line_number,
            "procedure_code": l.procedure_code,
            "service_name": l.service_name,
            "requested_quantity": l.requested_quantity,
            # "charge_amount": l.charge_amount,
            "authorization_number": l.authorization_number,
            "authorization_status": l.authorization_status,
        })

    prior_block = ""
    if prior_rounds:
        plines = ["PRIOR CLAIM HISTORY:"]
        for idx, r in enumerate(prior_rounds):
            lvl = r.get("level", 0)
            plines.append(f"\n--- Round {idx + 1} (Level {lvl}) ---")

            # What was billed
            billed = r.get("billed_lines", [])
            if billed:
                plines.append("Billed:")
                for line in billed:
                    plines.append(
                        f"  - line {line.get('line_number')}: {line.get('procedure_code')} "
                        f"(auth: {line.get('authorization_number')})"
                    )

            # What payor decided
            outcomes = r.get("line_outcomes", [])
            if outcomes:
                plines.append("Payor response:")
                for out in outcomes:
                    status = out.get("status", "unknown")
                    reason = out.get("decision_reason", "")
                    docs = out.get("requested_documents", [])
                    # paid = out.get("paid_amount")

                    out_str = f"  - line {out.get('line_number')}: {status}"
                    # if paid is not None:
                    #     out_str += f" | paid: ${paid}"
                    if reason:
                        out_str += f" | reason: {reason[:100]}"
                    if docs:
                        out_str += f" | requested_docs: {docs}"
                    plines.append(out_str)

        prior_block = "\n" + "\n".join(plines) + "\n"

    # current claim state for turn 2+
    current_state_block = ""
    phase3_submissions = state.phase3_submissions if state.phase3_submissions is not None else []
    phase3_responses = state.phase3_responses if state.phase3_responses is not None else []
    if phase3_submissions and phase3_responses:
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
                "claims_review_level": getattr(l, "current_review_level", 0),
                "decision_reason": getattr(l, "decision_reason", None),
            })
        current_state_lines.append(f"Current line statuses: {json.dumps(adj_summary, ensure_ascii=False)}")
        current_state_block = "\n" + "\n".join(current_state_lines) + "\n"

    # 1. TASK - different for turn 0 vs continuation
    if turn == 0:
        task_instruction = (
            "TASK: Submit a claim for delivered services.\n"
            "Include all delivered service lines with their authorization numbers.\n"
        )
    else:
        task_instruction = (
            "TASK: Resubmit the claim with lines that require action.\n"
            "- For pending_info lines: include with documentation addressing requested items\n"
            "- For denied lines: include only if appealing with corrected billing\n"
            "- Do NOT include approved lines (already adjudicated)\n"
        )

    # Build prompt: TASK first, OUTPUT FORMAT last
    parts = [
        # 1. TASK first
        task_instruction,
        # 2. Context metadata
        f"\nTurn: {turn} | Review Level: {level}\n",
        # 3. Patient summary
        f"\nPATIENT:\n"
        f"- id: {pv['patient_id']}\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n"
        f"- chief_complaint: {pv['chief_complaint']}\n",
    ]

    # 4. Delivered lines - only on turn 0
    if turn == 0:
        parts.append(
            f"\nDELIVERED SERVICE LINES:\n"
            f"{json.dumps(lines_summary, ensure_ascii=False, indent=2)}\n"
        )

    # 5. Prior history (if any)
    if prior_block:
        parts.append(prior_block)

    # 6. Current state (if turn > 0)
    if current_state_block:
        parts.append(current_state_block)

    # 7. OUTPUT FORMAT - last, closest to generation
    parts.append(
        f"\nOUTPUT FORMAT:\n"
        f"{PHASE3_PROVIDER_CLAIM_SCHEMA}\n"
        f"Return only valid JSON:\n"
        f"{PHASE3_PROVIDER_CLAIM_JSON}"
    )

    return "".join(parts)


def create_phase3_payor_system_prompt(payor_params: Optional[Dict[str, Any]] = None) -> str:
    params = payor_params or {}
    guidance = PAYOR_STRATEGY_GUIDANCE[params["strategy"]]
    strategy_block = f"\nSTRATEGY GUIDANCE:\n{guidance}\n" if guidance else ""

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

    clinical_guideline_block = ""
    if params.get("clinical_guideline"):
        guideline = params["clinical_guideline"]
        clinical_guideline_block = (
            "\nPROVIDER CLINICAL GUIDELINE (for reference when evaluating clinical justification):\n"
            f"Source: {guideline.get('issuer', 'Unknown')}\n"
        )
        data = guideline.get("content", {}).get("data", {})
        if data:
            clinical_guideline_block += _render_policy_data(data) + "\n"

    return (
        "You are an insurance claims adjudication team processing a clinical claim.\n"
        "Your goal: render payment decisions based on coverage policy, authorization status, and clinical documentation.\n"
        "\nADMINISTRATIVE COST CONSIDERATION:\n"
        "Claim processing costs ~$1 (manual) to ~$0.10 (electronic) per claim (CAQH 2023). "
        "Overturning a denial costs ~$40-50 per claim (Advisory Board). "
        "Apply reasonableness standard:\n"
        "- Do not request documentation already submitted\n"
        "- Avoid repeated pends for the same item\n"
        "- If criteria cannot be met, deny clearly rather than pend indefinitely\n"
        f"{strategy_block}"
        f"{policy_block}"
        f"{clinical_guideline_block}"
        f"\n{WORKFLOW_ACTION_DEFINITIONS_PAYOR}"
    )


def create_phase3_payor_user_prompt(
    state: object,
    claim_obj: Dict[str, Any],
    *,
    turn: int,
    level: int = 0,
    pend_count_at_level: int = 0,
    encounter_history: Optional[List[Dict[str, Any]]] = None
) -> str:
    pv = _normalize_patient_visible_data(state.patient_visible_data)
    claim_text = json.dumps(claim_obj, ensure_ascii=False, indent=2)

    pend_rule = (
        "" if level < 2 else
        "RULE: pending_info is NOT allowed at this level; decide another status.\n"
    )

    # Build encounter history block
    history_block = ""
    if encounter_history:
        history_lines = ["CLAIM ENCOUNTER HISTORY (your prior interactions):"]
        for entry in encounter_history:
            history_lines.append(f"\n--- Round {entry.get('round')} (Level {entry.get('level')}) ---")

            billed = entry.get("provider_billed", [])
            if billed:
                history_lines.append("Provider billed:")
                for line in billed:
                    history_lines.append(
                        f"  - line {line.get('line_number')}: {line.get('procedure_code')} "
                        f"(auth: {line.get('authorization_number')})"
                    )

            decisions = entry.get("my_prior_decision", [])
            if decisions:
                history_lines.append("Your decision:")
                for dec in decisions:
                    dec_str = f"  - line {dec.get('line_number')}: {dec.get('status')}"
                    # if dec.get("paid_amount") is not None:
                    #     dec_str += f" | paid: ${dec.get('paid_amount')}"
                    if dec.get("decision_reason"):
                        dec_str += f" | reason: {dec.get('decision_reason', '')[:80]}"
                    history_lines.append(dec_str)

        history_block = "\n" + "\n".join(history_lines) + "\n\n"

    # 1. TASK
    task_instruction = (
        "TASK: Adjudicate billed service lines.\n"
        "Verify services match authorization and documentation supports medical necessity.\n"
        f"{pend_rule}"
    )

    # Build prompt: TASK first, OUTPUT FORMAT last
    parts = [
        # 1. TASK first
        task_instruction,
        # 2. Context metadata
        f"\nTurn: {turn} | Review Level: {level} | Pends at this level: {pend_count_at_level}\n",
        # 3. Patient summary
        f"\nPATIENT SUMMARY:\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n"
        f"- chief_complaint: {pv['chief_complaint']}\n",
    ]

    # 4. Encounter history (if any)
    if history_block:
        parts.append(history_block)

    # 5. Current claim to adjudicate
    parts.append(
        f"\nCURRENT CLAIM:\n"
        f"{claim_text}\n"
    )

    # 6. OUTPUT FORMAT - last, closest to generation
    parts.append(
        f"\nOUTPUT FORMAT:\n"
        f"{PHASE3_PAYOR_RESPONSE_SCHEMA}\n"
        f"Return only valid JSON:\n"
        f"{PHASE3_PAYOR_RESPONSE_JSON}"
    )

    return "".join(parts)
