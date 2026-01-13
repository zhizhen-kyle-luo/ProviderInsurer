"""Prompt response format templates derived from shared schema definitions."""
from __future__ import annotations

from typing import Optional


def phase2_provider_response_format() -> str:
    """Return Phase 2 provider RESPONSE FORMAT (JSON) block."""
    return """{
    "internal_rationale": {
        "reasoning": "<your diagnostic reasoning and why you chose this confidence level>",
        "differential_diagnoses": ["<diagnosis 1>", "<diagnosis 2>"]
    },
    "insurer_request": {
        "diagnosis_codes": [
            {
                "icd10": "<ICD-10 code>",
                "description": "<diagnosis description>"
            }
        ],
        "request_type": "diagnostic_test" or "treatment" or "level_of_care",
        "requested_service": {
            // if diagnostic_test:
            "procedure_code": "<CPT code for test>",
            "code_type": "CPT",
            "service_name": "<specific test>",
            "test_justification": "<why this test will establish diagnosis>",
            "expected_findings": "<what results would confirm/rule out diagnosis>"

            // if treatment:
            "procedure_code": "<CPT/HCPCS/J-code>",
            "code_type": "CPT" or "HCPCS" or "J-code",
            "service_name": "<specific treatment>",
            "clinical_evidence": "<objective data supporting request>",
            "guideline_references": ["<guideline 1>", "<guideline 2>"]

            // if level_of_care:
            "requested_status": "<inpatient|observation|hospital_infusion|home_infusion|ICU|floor|SNF>",
            "alternative_status": "<lower level alternative>",
            "severity_indicators": "<objective clinical indicators: vital signs, lab values, acuity scores, two-midnight rule expectation, specialized monitoring needs, venous access requirements, medical instability factors>"
        },
        "clinical_notes": "<narrative H&P-style documentation integrating all findings to date>"
    }
}"""


def phase2_treatment_decision_response_format() -> str:
    """Return Phase 2 treatment decision RESPONSE FORMAT (JSON) block."""
    return """{
    "decision": "treat_anyway" or "no_treat",
    "rationale": "<explain your reasoning considering clinical need, financial risk, and legal obligations>"
}"""


def phase2_payor_response_format(
    decision_options: str,
    can_pend: bool,
    role_label: str,
    level: int
) -> str:
    """Return Phase 2 payor RESPONSE FORMAT (JSON) block."""
    missing_doc_line: Optional[str] = None
    if can_pend:
        missing_doc_line = "'missing_documentation': ['<doc1>', '<doc2>'],  // if pending_info"

    lines = [
        "{",
        f'    "action": "{decision_options.replace(" | ", "\" or \"")}",',
        '    "denial_reason": "<specific reason if denied' + (" or pended" if can_pend else "") + '>",',
    ]
    if missing_doc_line:
        lines.append(f"    {missing_doc_line}")
    lines.extend([
        '    "downgrade_alternative": "<if downgrade: describe approved alternative (e.g., \'observation status instead of inpatient\', \'home infusion instead of hospital infusion\')>",',
        '    "criteria_used": "<guidelines or policies applied>",',
        f'    "reviewer_type": "{role_label}",',
        f'    "level": {level},',
        "    \"requires_peer_to_peer\": true or false  // optional, set true if peer-to-peer recommended",
        "}",
    ])
    return "\n".join(lines)


def phase3_claim_submission_decision_response_format() -> str:
    """Return Phase 3 claim submission decision RESPONSE FORMAT (JSON) block."""
    return """{
    "decision": "submit_claim" or "skip",
    "rationale": "<explain your reasoning>"
}"""


def phase3_provider_response_format() -> str:
    """Return Phase 3 provider RESPONSE FORMAT (JSON) block."""
    return """{
    "internal_rationale": {
        "reasoning": "<why you expect this claim to be paid or denied>",
        "documentation_completeness": "<assessment of your documentation>"
    },
    "insurer_request": {
        "diagnosis_codes": [
            {
                "icd10": "<ICD-10 code>",
                "description": "<diagnosis description>"
            }
        ],
        "procedure_codes": [
            {
                "code": "<CPT/HCPCS/J-code>",
                "code_type": "CPT" or "HCPCS" or "J-code",
                "description": "<service description>",
                "quantity": <number>,
                "amount_billed": <dollar amount per unit>
            }
        ],
        "total_amount_billed": <total dollar amount>,
        "clinical_notes": "<narrative documentation of care delivered>",
        "discharge_summary": "<if applicable, final discharge documentation>",
        "supporting_documentation": "<any additional clarifying records>"
    }
}"""


def phase3_payor_response_format(
    decision_options: str,
    role_label: str,
    level: int,
    can_pend: bool
) -> str:
    """Return Phase 3 payor RESPONSE FORMAT (JSON) block."""
    lines = [
        "{",
        f'    "action": "{decision_options.replace(" | ", "\" or \"")}",  // overall: approved, downgrade, denied, or pending_info',
        "",
        "    // LINE-LEVEL ADJUDICATION (X12 835 remittance advice aligned)",
        "    // adjudicate each submitted procedure code line separately",
        "    \"line_adjudications\": [",
        "        {",
        "            \"line_number\": <1-based index into procedure_codes array>,",
        "            \"procedure_code\": \"<CPT/HCPCS code from submission>\",",
        "            \"adjudication_status\": \"approved\" or \"denied\" or \"partial\" or \"downgraded\",",
        "            \"billed_amount\": <amount provider billed>,",
        "            \"allowed_amount\": <payor's contractual allowed amount>,",
        "            \"paid_amount\": <actual payment amount>,",
        "            \"adjustment_reason\": \"<reason for denial or adjustment, if any>\",",
        "            \"downgraded_code\": \"<if downgraded, the approved alternative code>\"",
        "        }",
        "    ],",
        "",
        "    // OVERALL CLAIM-LEVEL FIELDS",
        "    \"total_paid_amount\": <sum of all line paid_amounts>,",
        "",
        "    // if downgrade:",
        "    \"downgrade_alternative\": \"<describe approved alternative level/code>\",",
        "",
    ]
    if can_pend:
        lines.extend([
            "    // if pending_info (only for Levels 0-1):",
            "    \"pend_reason\": \"<what EXISTING documentation is missing>\",",
            "    \"requested_documents\": [\"<discharge summary>\", \"<operative report>\", etc.],",
            "",
        ])
    lines.extend([
        "    // if fully denied (all lines denied):",
        "    \"denial_reason\": \"<overall reason for full claim denial>\",",
        "",
        "    \"criteria_used\": \"<payment guidelines or policies applied>\",",
        f'    "reviewer_type": "{role_label}",',
        f"    \"level\": {level}",
        "}",
    ])
    return "\n".join(lines)
