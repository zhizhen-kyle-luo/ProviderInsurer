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
                "line_number": <1-based index>,
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


def phase2_payor_response_format(
    decision_options: str,
    can_pend: bool,
    role_label: str,
    level: int
) -> str:
    """Return Phase 2 payor RESPONSE FORMAT (JSON) block."""
    lines = [
        "{",
        f'    "action": "{decision_options.replace(" | ", "\" or \"")}",  // overall decision',
        "",
        "    // LINE-LEVEL ADJUDICATION (X12 278 authorization aligned)",
        "    // adjudicate each service line separately",
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
        "    // OVERALL CLAIM-LEVEL FIELDS",
        '    "decision_reason": "<overall reason for decision>",',
        '    "downgrade_alternative": "<if modified: describe approved alternative>",',
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
    decision_options: str,
    role_label: str,
    level: int,
    can_pend: bool
) -> str:
    """Return Phase 3 payor RESPONSE FORMAT (JSON) block."""
    lines = [
        "{",
        f'    "action": "{decision_options.replace(" | ", "\" or \"")}",  // overall: approved, modified, denied, or pending_info',
        "",
        "    // LINE-LEVEL ADJUDICATION (X12 835 remittance advice aligned)",
        "    // adjudicate each submitted procedure code line separately",
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
        "    // OVERALL CLAIM-LEVEL FIELDS",
        "    \"total_paid_amount\": <sum of all line paid_amounts>,",
        "    \"decision_reason\": \"<overall reason for claim decision>\",",
        "",
        "    // if modified:",
        "    \"downgrade_alternative\": \"<describe approved alternative level/code>\",",
        "",
    ]
    if can_pend:
        lines.extend([
            "    // if pending_info (only for Levels 0-1):",
            "    \"requested_documents\": [\"<discharge summary>\", \"<operative report>\", etc.],",
            "",
        ])
    lines.extend([
        "    \"criteria_used\": \"<payment guidelines or policies applied>\",",
        f'    "reviewer_type": "{role_label}",',
        f"    \"level\": {level}",
        "}",
    ])
    return "\n".join(lines)
