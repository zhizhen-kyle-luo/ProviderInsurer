"""response schema templates for LLM JSON responses"""
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
        "requested_services": [
            {
                "line_number": <1-based index, ALWAYS start at 1>,
                "request_type": "diagnostic_test" or "treatment" or "level_of_care",

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
                "procedure_code": "<CPT/HCPCS/J-code>",
                "code_type": "CPT" or "HCPCS" or "J-code",
                "service_name": "<requested level of care, e.g. 'Inpatient admission', 'ICU admission'>",
                "requested_status": "<inpatient|observation|hospital_infusion|home_infusion|ICU|floor|SNF>",
                "alternative_status": "<lower level alternative>",
                "severity_indicators": "<objective clinical indicators>"
            }
        ],
        "clinical_notes": "<narrative H&P-style documentation integrating all findings to date>"
    }
}"""


def phase2_treatment_decision_response_format() -> str:
    """Return Phase 2 treatment decision RESPONSE FORMAT (JSON) block."""
    return """{
    "decision": "treat_anyway" or "no_treat",
    "rationale": "<explain your reasoning considering clinical need, financial risk, and legal obligations>"
}"""


def phase2_post_diagnostic_decision_response_format() -> str:
    """Return Phase 2 post-diagnostic decision RESPONSE FORMAT (JSON) block."""
    return """{
    "decision": "request_treatment" or "no_treatment_needed",
    "rationale": "<explain your reasoning based on the test results and clinical picture>"
}"""


def phase2_payor_response_format(
    can_pend: bool,
    role_label: str,
    level: int
) -> str:
    """Return Phase 2 payor RESPONSE FORMAT (JSON) block."""
    lines = [
        "{",
        "    // LINE-LEVEL ADJUDICATION (X12 278 authorization aligned)",
        "    // IMPORTANT: you MUST adjudicate EVERY service line - one entry per line_number",
        "    // IMPORTANT: use EXACTLY these adjudication_status values: approved, modified, denied, pending_info (NOT 'pended')",
        "    \"line_adjudications\": [",
        "        {",
        "            \"line_number\": <1-based index into service_lines>,",
        "            \"adjudication_status\": \"approved\" or \"modified\" or \"denied\" or \"pending_info\",",
        "            \"decision_reason\": \"<reason for this line's decision>\",",
        "            \"approved_quantity\": <if modified: approved quantity>,",
        "            \"modification_type\": \"<if modified: quantity_reduction or code_downgrade>\",",
    ]
    if can_pend:
        lines.append('            "requested_documents": ["<doc1>", "<doc2>"]  // if pending_info')
    lines.extend([
        "        }",
        "    ],",
        "",
        "    // OVERALL FIELDS (for documentation, not decision logic)",
        '    "decision_reason": "<summary of overall rationale>",',
        '    "downgrade_alternative": "<if any line modified: describe approved alternatives>",',
        '    "criteria_used": "<guidelines or policies applied>",',
        f'    "reviewer_type": "{role_label}",',
        f'    "level": {level},',
        "    \"requires_peer_to_peer\": true or false  // optional",
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
                "procedure_code": "<CPT/HCPCS/J-code>",
                "code_type": "CPT" or "HCPCS" or "J-code",
                "service_description": "<service description>",
                "requested_quantity": <number>,
                "charge_amount": <dollar amount per unit>
            }
        ],
        "total_amount_billed": <total dollar amount>,
        "clinical_notes": "<narrative documentation of care delivered>",
        "discharge_summary": "<if applicable, final discharge documentation>",
        "supporting_documentation": "<any additional clarifying records>"
    }
}"""


def phase3_payor_response_format(
    role_label: str,
    level: int,
    can_pend: bool
) -> str:
    """Return Phase 3 payor RESPONSE FORMAT (JSON) block."""
    lines = [
        "{",
        "    // LINE-LEVEL ADJUDICATION (X12 835 remittance advice aligned)",
        "    // IMPORTANT: you MUST adjudicate EVERY procedure code line - one entry per line_number",
        "    // IMPORTANT: use EXACTLY these adjudication_status values: approved, modified, denied, pending_info (NOT 'pended')",
        "    \"line_adjudications\": [",
        "        {",
        "            \"line_number\": <1-based index into procedure_codes array>,",
        "            \"procedure_code\": \"<CPT/HCPCS code from submission>\",",
        "            \"adjudication_status\": \"approved\" or \"modified\" or \"denied\" or \"pending_info\",",
        "            \"charge_amount\": <amount provider billed>,",
        "            \"allowed_amount\": <payor's contractual allowed amount>,",
        "            \"paid_amount\": <actual payment amount>,",
        "            \"decision_reason\": \"<reason for this line's decision>\",",
        "            \"downgraded_code\": \"<if modified, the approved alternative code>\"",
        "        }",
        "    ],",
        "",
        "    // OVERALL FIELDS (for documentation, not decision logic)",
        "    \"total_paid_amount\": <sum of all line paid_amounts>,",
        "    \"decision_reason\": \"<summary of overall rationale>\",",
        "    \"downgrade_alternative\": \"<if any line modified: describe approved alternatives>\",",
    ]
    if can_pend:
        lines.extend([
            "    \"requested_documents\": [\"<if any line pending_info>\"],",
        ])
    lines.extend([
        "    \"criteria_used\": \"<payment guidelines or policies applied>\",",
        f'    "reviewer_type": "{role_label}",',
        f"    \"level\": {level}",
        "}",
    ])
    return "\n".join(lines)
