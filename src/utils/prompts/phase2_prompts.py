from __future__ import annotations

from typing import Any, Dict, List, Optional


def _require(pv: Dict[str, Any], key: str):
    if key not in pv:
        raise ValueError(f"patient_visible_data missing required field: {key}")
    return pv[key]

def _normalize_patient_visible_data(pv: object) -> Dict[str, Any]:
    if not isinstance(pv, dict):
        raise ValueError("state.patient_visible_data must be a dict")
    _require(pv, "patient_id")
    _require(pv, "age")
    _require(pv, "sex")
    _require(pv, "admission_source")
    _require(pv, "chief_complaint")
    _require(pv, "medical_history")
    _require(pv, "medications")
    _require(pv, "vital_signs")
    _ = pv.get("lab_results", {})  # optional in your schema
    return pv

def create_phase2_provider_system_prompt(provider_params: Optional[Dict[str, Any]] = None) -> str:
    _ = provider_params or {}
    return (
        "You are a hospital provider team preparing an insurer utilization review request (X12 278-like).\n"
        "Be specific and concise. Return only valid JSON matching the schema.\n"
        "Do not add extra keys.\n"
    )


def create_phase2_payor_system_prompt(payor_params: Optional[Dict[str, Any]] = None) -> str:
    _ = payor_params or {}
    return (
        "You are an insurer utilization management reviewer responding to an authorization request.\n"
        "Adjudicate each service line independently. Return only valid JSON matching the schema.\n"
        "Do not add extra keys.\n"
    )


def create_phase2_provider_user_prompt(
    state: object,
    *,
    turn: int,
    level: int,
    prior_rounds: Optional[List[Dict[str, Any]]] = None,
) -> str:
    prior_rounds = prior_rounds or []
    pv = _normalize_patient_visible_data(getattr(state, "patient_visible_data", None))

    vitals = pv.get("vital_signs", {}) or {}
    labs = pv.get("lab_results", {}) or {}

    prior_block = ""
    if prior_rounds:
        lines: List[str] = ["PRIOR ROUNDS (most recent last):"]
        for r in prior_rounds:
            lvl = r.get("level")
            decision = r.get("payor_decision", "")
            reason = r.get("payor_decision_reason", "")
            lines.append(f"- level={lvl} decision={decision} reason={reason}")
        prior_block = "\n" + "\n".join(lines) + "\n"

    return f"""PHASE 2 - PROVIDER SUBMISSION
Turn: {turn}
Review Level: {level}

PATIENT
- id: {pv["patient_id"]}
- age: {pv["age"]}
- sex: {pv["sex"]}
- admission_source: {pv["admission_source"]}
- chief_complaint: {pv["chief_complaint"]}
- presenting_symptoms: {pv.get("presenting_symptoms", "")}
- physical_exam: {pv.get("physical_exam", "")}
- clinical_notes: {pv.get("clinical_notes", "")}
- vitals: {vitals}
- labs: {labs}

{prior_block}
TASK
Create an insurer authorization request with one or more service lines.

STRICT RESPONSE FORMAT (JSON ONLY):
{{
  "insurer_request": {{
    "diagnosis_codes": [{{"icd10": "<ICD-10>", "description": "<text>"}}],
    "requested_services": [
      {{
        "line_number": 1,
        "request_type": "diagnostic_test" or "treatment" or "level_of_care",
        "procedure_code": "<CPT/HCPCS/J-code/NDC>",
        "code_type": "CPT" or "HCPCS" or "J-code" or "NDC",
        "service_name": "<short display name>",

        "test_justification": "<if diagnostic_test>",
        "expected_findings": "<if diagnostic_test>",

        "clinical_evidence": "<if treatment>",

        "requested_status": "<if level_of_care>",
        "alternative_status": "<if level_of_care>",
        "severity_indicators": "<if level_of_care>"
      }}
    ],
    "clinical_notes": "<H&P style narrative>"
  }}
}}

Return ONLY valid JSON."""


def create_phase2_payor_user_prompt(
    state: object,
    insurer_request: Dict[str, Any],
    *,
    turn: int,
    level: int,
    pend_count_at_level: int = 0,
) -> str:
    pv = _normalize_patient_visible_data(getattr(state, "patient_visible_data", None))

    requested_services = insurer_request.get("requested_services")
    if not isinstance(requested_services, list):
        requested_services = []

    line_nums = [svc.get("line_number") for svc in requested_services if isinstance(svc, dict)]
    line_nums = [int(x) for x in line_nums if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())]

    no_pend_note = ""
    if level >= 2:
        no_pend_note = "NOTE: At level 2 (final review), you MUST NOT use pending_info; decide approved/modified/denied.\n"

    return f"""PHASE 2 - PAYOR REVIEW
Turn: {turn}
Review Level: {level}
Pend count at this level: {pend_count_at_level}

PATIENT (provider-visible summary)
- age: {pv["age"]}
- sex: {pv["sex"]}
- chief_complaint: {pv["chief_complaint"]}

INSURER REQUEST (provider submission)
{insurer_request}

{no_pend_note}
TASK
Adjudicate EVERY requested service line. One entry per line_number.
Valid authorization_status values: approved, modified, denied, pending_info

STRICT RESPONSE FORMAT (JSON ONLY):
{{
  "line_adjudications": [
    {{
      "line_number": <one of {line_nums}>,
      "authorization_status": "approved" or "modified" or "denied" or "pending_info",
      "decision_reason": "<why>",
      "approved_quantity": <if approved/modified and quantity matters>,
      "authorization_number": "<optional>",
      "modification_type": "<if modified: quantity_reduction or code_downgrade>",
      "requested_documents": ["<if pending_info>"]
    }}
  ],
  "reviewer_type": "<string>",
  "level": {level}
}}

Return ONLY valid JSON."""

