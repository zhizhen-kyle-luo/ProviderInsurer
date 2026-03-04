from __future__ import annotations
"""
Phase 2 (Prior Authorization) prompt construction.

CONTEXT ENGINEERING PRINCIPLES:
- System prompt = WHO you are, HOW you behave (stable across turns)
- User prompt = WHAT you're looking at, WHAT to do (changes per turn)

System prompt contains:
  - Role and goal
  - Behavioral guidelines (admin cost, strategy)
  - Domain knowledge (policy, workflow definitions)

User prompt structure:
  1. TASK (what to do) - FIRST for clarity
  2. Context metadata (turn, level)
  3. Input data (patient, history, current request)
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
    PHASE2_PROVIDER_REQUEST_SCHEMA,
    PHASE2_PROVIDER_REQUEST_JSON,
    PHASE2_PAYOR_RESPONSE_SCHEMA,
    PHASE2_PAYOR_RESPONSE_JSON,
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


# =============================================================================
# PHASE 2 PROVIDER PROMPTS
# =============================================================================

def create_phase2_provider_system_prompt(provider_params: Optional[Dict[str, Any]] = None) -> str:
    """
    System prompt: WHO you are, HOW you behave (stable across turns)
    - Role and goal
    - Behavioral guidelines
    - Strategy (if any)
    - Policy/clinical guidelines (if any)
    - Workflow definitions (review levels, decision vocab, action vocab)
    """
    params = provider_params or {}

    guidance = PROVIDER_STRATEGY_GUIDANCE[params["strategy"]]
    strategy_block = f"\nSTRATEGY GUIDANCE:\n{guidance}\n" if guidance else ""

    # Policy/clinical guidelines (domain knowledge)
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

    # symmetric context: provider also sees payor's coverage policy
    coverage_policy_block = ""
    if params.get("coverage_policy"):
        coverage_policy = params["coverage_policy"]
        coverage_policy_block = (
            "\nPAYER COVERAGE POLICY (for reference when constructing your request):\n"
            f"Source: {coverage_policy.get('issuer', 'Unknown')}\n"
        )
        data = coverage_policy.get("content", {}).get("data", {})
        if data:
            coverage_policy_block += _render_policy_data(data) + "\n"

    return (
        # WHO you are
        "You are a hospital provider team preparing an authorization request for the insurer.\n"
        "Your goal: get medically necessary services approved by documenting clinical justification.\n"
        # HOW you behave
        "\nADMINISTRATIVE COST CONSIDERATION:\n"
        "Each PA cycle costs ~$11 (manual) to ~$6 (electronic) in staff time (CAQH 2023), plus delays patient care. "
        "Appeals must be filed within 60-180 days of denial.\n\n"
        "RESUBMIT only when:\n"
        "- You made an error (wrong codes, missing documentation you actually have)\n"
        "- You CAN provide what the payor requested\n\n"
        "APPEAL or ABANDON when:\n"
        "- Patient does not meet policy criteria (e.g., no step-therapy trial exists in history)\n"
        "- Payor misapplied policy or ignored evidence already provided\n"
        "- Prior resubmission was denied for the same reason\n\n"
        "If the underlying facts cannot change, resubmitting will fail again.\n"
        f"{strategy_block}"
        f"{policy_block}"
        f"{coverage_policy_block}"
        # Domain knowledge (workflow definitions)
        f"\n{WORKFLOW_ACTION_DEFINITIONS_PROVIDER}"
    )


def _render_service_lines_state(state: object) -> str:
    """render current service lines with their authorization status"""
    lines = state.service_lines
    if lines is None:
        raise ValueError("state.service_lines is None")
    if not lines:
        return ""

    parts = ["CURRENT SERVICE LINES STATE:"]
    for l in lines:
        if l.line_number is None:
            raise ValueError("service_line missing line_number")
        if l.procedure_code is None:
            raise ValueError(f"service_line {l.line_number} missing procedure_code")
        if l.service_name is None:
            raise ValueError(f"service_line {l.line_number} missing service_name")

        ln = l.line_number
        code = l.procedure_code
        name = l.service_name
        status = l.authorization_status if l.authorization_status is not None else "not_reviewed"
        docs = l.requested_documents if l.requested_documents is not None else []
        reason = l.decision_reason if l.decision_reason is not None else ""

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
    """
    User prompt: WHAT you're looking at, WHAT to do (changes per turn)
    Structure:
      1. TASK (what to do) - first for clarity
      2. Context metadata (turn, level)
      3. Patient data
      4. Prior history (if any)
      5. Current state (if turn > 0)
      6. OUTPUT FORMAT (schema + JSON) - last, closest to generation
    """
    if prior_rounds is None:
        prior_rounds = []
    pv = _normalize_patient_visible_data(state.patient_visible_data)
    vitals = pv.get("vital_signs")
    if vitals is None:
        vitals = {}
    labs = pv.get("lab_results")
    if labs is None:
        labs = {}

    # 1. TASK - different for turn 0 vs continuation
    service_lines_block = _render_service_lines_state(state)
    if turn == 0:
        task_instruction = (
            "TASK: Construct an insurer_request with service lines you wish to request.\n"
            "Include clinical_evidence for each line to justify medical necessity.\n"
        )
    else:
        task_instruction = (
            "TASK: Resubmit the insurer_request with lines that require action.\n"
            "- For pending_info lines: include with clinical_evidence addressing requested_documents\n"
            "- For denied lines: include only if appealing with new evidence\n"
            "- Do NOT include approved lines (already authorized)\n"
        )

    # 4. Prior history (if any)
    prior_block = ""
    if prior_rounds:
        prior_lines = ["PRIOR SUBMISSION HISTORY:"]
        for idx, r in enumerate(prior_rounds):
            lvl = r.get("level", 0)
            prior_lines.append(f"\n--- Round {idx + 1} (Level {lvl}) ---")

            requested = r.get("requested_services", [])
            if requested:
                prior_lines.append("Requested:")
                for svc in requested:
                    prior_lines.append(
                        f"  - line {svc.get('line_number')}: {svc.get('procedure_code')} "
                        f"({svc.get('code_type')}) {svc.get('service_name')}"
                    )

            outcomes = r.get("line_outcomes", [])
            if outcomes:
                prior_lines.append("Payor response:")
                for out in outcomes:
                    status = out.get("status", "unknown")
                    reason = out.get("decision_reason", "")
                    docs = out.get("requested_documents", [])
                    mod = out.get("modification_type", "")

                    out_str = f"  - line {out.get('line_number')}: {status}"
                    if reason:
                        out_str += f" | reason: {reason[:100]}"
                    if docs:
                        out_str += f" | requested_docs: {docs}"
                    if mod:
                        out_str += f" | modification: {mod}"
                    prior_lines.append(out_str)

        prior_block = "\n".join(prior_lines) + "\n"

    # 3. Patient data
    medical_history = pv.get("medical_history")
    if medical_history is None:
        medical_history = []
    medications = pv.get("medications")
    if medications is None:
        medications = []
    presenting_symptoms = pv.get("presenting_symptoms")
    if presenting_symptoms is None:
        presenting_symptoms = ""
    physical_exam = pv.get("physical_exam")
    if physical_exam is None:
        physical_exam = ""
    clinical_notes = pv.get("clinical_notes")
    if clinical_notes is None:
        clinical_notes = ""

    admission_source = pv.get("admission_source")
    if admission_source is None:
        admission_source = ""

    patient_block = (
        "PATIENT:\n"
        f"- patient_id: {pv['patient_id']}\n"
        f"- age: {pv['age']}\n"
        f"- sex: {pv['sex']}\n"
        f"- admission_source: {admission_source}\n"
        f"- chief_complaint: {pv['chief_complaint']}\n"
        f"- medical_history: {json.dumps(medical_history, ensure_ascii=False)}\n"
        f"- medications: {json.dumps(medications, ensure_ascii=False)}\n"
        f"- vital_signs: {json.dumps(vitals, ensure_ascii=False)}\n"
        f"- presenting_symptoms: {presenting_symptoms}\n"
        f"- physical_exam: {physical_exam}\n"
        f"- clinical_notes: {clinical_notes}\n"
        f"- lab_results: {json.dumps(labs, ensure_ascii=False)}\n"
    )

    # Build prompt with proper ordering
    parts = [
        # 1. TASK first
        task_instruction,
        # 2. Context metadata
        f"\nTurn: {turn} | Review Level: {level}\n",
        # 3. Patient data
        f"\n{patient_block}",
    ]

    # 4. Prior history (if any)
    if prior_block:
        parts.append(f"\n{prior_block}")

    # 5. Current state (if turn > 0)
    if service_lines_block:
        parts.append(f"\n{service_lines_block}")

    # 6. OUTPUT FORMAT - last, closest to generation
    parts.append(
        f"\nOUTPUT FORMAT:\n"
        f"{PHASE2_PROVIDER_REQUEST_SCHEMA}\n"
        f"Return only valid JSON:\n"
        f"{PHASE2_PROVIDER_REQUEST_JSON}"
    )

    return "".join(parts)


# =============================================================================
# PHASE 2 PAYOR PROMPTS
# =============================================================================

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

    guidance = PROVIDER_STRATEGY_GUIDANCE[params["strategy"]]
    strategy_block = f"\nSTRATEGY GUIDANCE:\n{guidance}\n" if guidance else ""

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
    """
    System prompt: WHO you are, HOW you behave (stable across turns)
    - Role and goal
    - Behavioral guidelines
    - Strategy (if any)
    - Policy (if any)
    - Workflow definitions (review levels, decision vocab - NO provider actions)
    """
    params = payor_params or {}

    guidance = PAYOR_STRATEGY_GUIDANCE[params["strategy"]]
    strategy_block = f"\nSTRATEGY GUIDANCE:\n{guidance}\n" if guidance else ""

    # Coverage policy (domain knowledge)
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

    # symmetric context: payor also sees provider's clinical guideline
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
        # WHO you are
        "You are an insurance utilization management team adjudicating a prior authorization request.\n"
        "Your goal: render coverage decisions based on policy criteria and clinical documentation.\n"
        # HOW you behave
        "\nADMINISTRATIVE COST CONSIDERATION:\n"
        "Each PA review costs ~$3.50 (manual) to ~$0.05 (electronic) in processing (CAQH 2023). "
        "Apply reasonableness standard:\n"
        "- Do not request documentation already submitted\n"
        "- Do not pend repeatedly for the same item\n"
        "- If criteria cannot be met, deny clearly rather than pend indefinitely\n"
        f"{strategy_block}"
        f"{policy_block}"
        f"{clinical_guideline_block}"
        # Domain knowledge (workflow definitions - payor only, no provider actions)
        f"\n{WORKFLOW_ACTION_DEFINITIONS_PAYOR}"
    )


def create_phase2_payor_user_prompt(
    state: object,
    insurer_request: Dict[str, Any],
    *,
    turn: int,
    level: int,
    pend_count_at_level: int = 0,
    encounter_history: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    User prompt: WHAT you're looking at, WHAT to do (changes per turn)
    Structure:
      1. TASK (what to do) - first for clarity
      2. Context metadata (turn, level, pend count)
      3. Patient summary
      4. Encounter history (if any)
      5. Current request to adjudicate
      6. OUTPUT FORMAT (schema + JSON) - last, closest to generation
    """
    pv = _normalize_patient_visible_data(state.patient_visible_data)
    request_json = json.dumps(insurer_request, ensure_ascii=False, indent=2)

    # Level-specific rule
    pend_rule = ""
    if level >= 2:
        pend_rule = "RULE: pending_info is NOT allowed at Level 2; you must approve, modify, or deny.\n"

    # 1. TASK
    task_instruction = (
        "TASK: Adjudicate each requested_service line based on policy criteria.\n"
        "Consider clinical documentation and whether it meets coverage requirements.\n"
        f"{pend_rule}"
    )

    # 4. Encounter history (if any)
    history_block = ""
    if encounter_history:
        history_lines = ["ENCOUNTER HISTORY (your prior decisions for this case):"]
        for entry in encounter_history:
            history_lines.append(f"\n--- Round {entry.get('round')} (Level {entry.get('level')}) ---")

            submitted = entry.get("provider_submission", [])
            if submitted:
                history_lines.append("Provider submitted:")
                for svc in submitted:
                    history_lines.append(
                        f"  - line {svc.get('line_number')}: {svc.get('procedure_code')} {svc.get('service_name')}"
                    )

            decisions = entry.get("my_prior_decision", [])
            if decisions:
                history_lines.append("Your decision:")
                for dec in decisions:
                    dec_str = f"  - line {dec.get('line_number')}: {dec.get('status')}"
                    if dec.get("decision_reason"):
                        dec_str += f" | reason: {dec.get('decision_reason', '')[:80]}"
                    if dec.get("requested_documents"):
                        dec_str += f" | requested: {dec.get('requested_documents')}"
                    history_lines.append(dec_str)

        history_block = "\n".join(history_lines) + "\n"

    # Build prompt with proper ordering
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
        parts.append(f"\n{history_block}")

    # 5. Current request to adjudicate
    parts.append(
        f"\nCURRENT INSURER REQUEST:\n"
        f"{request_json}\n"
    )

    # 6. OUTPUT FORMAT - last, closest to generation
    parts.append(
        f"\nOUTPUT FORMAT:\n"
        f"{PHASE2_PAYOR_RESPONSE_SCHEMA}\n"
        f"Return only valid JSON:\n"
        f"{PHASE2_PAYOR_RESPONSE_JSON}"
    )

    return "".join(parts)
