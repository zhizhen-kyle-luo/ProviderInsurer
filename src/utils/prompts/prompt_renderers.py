"""text renderers for prompt context summaries"""
from __future__ import annotations

from typing import Dict, Any


def phase2_diagnostic_request_summary(requested_service: Dict[str, Any]) -> str:
    """render Phase 2 diagnostic test request summary"""
    return f"""
DIAGNOSTIC TEST REVIEW REQUEST (Phase 2):
Test: {requested_service.get('service_name')}
Justification: {requested_service.get('test_justification')}
Expected Findings: {requested_service.get('expected_findings')}
"""


def phase2_treatment_request_summary(requested_service: Dict[str, Any], guideline_references: list[str]) -> str:
    """render Phase 2 treatment request summary"""
    return f"""
TREATMENT REVIEW REQUEST (Phase 2):
Treatment: {requested_service.get('service_name')}
Clinical Evidence: {requested_service.get('clinical_evidence')}
Guidelines: {', '.join(guideline_references)}
"""


def phase2_level_of_care_request_summary(requested_service: Dict[str, Any]) -> str:
    """render Phase 2 level-of-care request summary"""
    return f"""
LEVEL OF CARE REVIEW REQUEST (Phase 2):
Requested Status: {requested_service.get('requested_status')}
Alternative Status: {requested_service.get('alternative_status')}
Severity Indicators: {requested_service.get('severity_indicators')}
"""


def phase3_provider_service_details(service_request: Dict[str, Any], case_type) -> str:
    """render Phase 3 provider service details summary"""
    from src.models import CaseType
    if case_type == CaseType.SPECIALTY_MEDICATION:
        return f"""SERVICE DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage Administered: {service_request.get('dosage')}
- Route: {service_request.get('route', 'N/A')}
- Frequency: {service_request.get('frequency', 'N/A')}"""

    service_name = service_request.get(
        'service_name',
        service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
    )
    clinical_indication = service_request.get(
        'clinical_indication',
        service_request.get('treatment_justification', 'N/A')
    )
    return f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}
- Clinical Indication: {clinical_indication}"""


def phase3_provider_coding_section(
    coding_options: list[Dict[str, Any]] | None,
    cost_ref: Dict[str, Any] | None,
    case_type
) -> str:
    """render Phase 3 provider coding & billing section"""
    from src.models import CaseType
    if coding_options:
        coding_section_parts = ["CODING & BILLING OPTIONS:"]
        coding_section_parts.append("You must select ONE diagnosis code based on clinical documentation:")
        coding_section_parts.append("")
        for i, option in enumerate(coding_options, 1):
            coding_section_parts.append(f"OPTION {i}: {option.get('icd10', 'N/A')} - {option.get('diagnosis', 'Unknown')}")
            coding_section_parts.append(f"  - Payment: ${option.get('payment', 0):,.2f}")
            coding_section_parts.append(f"  - DRG: {option.get('drg_code', 'N/A')}")
            coding_section_parts.append("")
        return "\n".join(coding_section_parts)

    if cost_ref:
        if case_type == CaseType.SPECIALTY_MEDICATION:
            total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
            return f"""BILLING INFORMATION:
- Drug Acquisition Cost: ${cost_ref.get('drug_acquisition_cost', 7800):.2f}
- Administration Fee: ${cost_ref.get('administration_fee', 150):.2f}
- Total Amount Billed: ${total_billed:.2f}"""

        total_billed = cost_ref.get('procedure_cost', 7800)
        return f"BILLING INFORMATION:\n- Procedure Cost: ${total_billed:.2f}"

    return "BILLING INFORMATION: (billing details not provided)"


def phase3_payor_service_summary(service_request: Dict[str, Any], case_type) -> str:
    """render Phase 3 payor claim submitted summary"""
    from src.models import CaseType
    if case_type == CaseType.SPECIALTY_MEDICATION:
        return f"""CLAIM SUBMITTED:
- Medication: {service_request.get('medication_name')}
- Dosage Administered: {service_request.get('dosage')}"""

    service_name = service_request.get(
        'service_name',
        service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
    )
    clinical_indication = service_request.get(
        'clinical_indication',
        service_request.get('treatment_justification', 'N/A')
    )
    return f"""CLAIM SUBMITTED:
- Procedure/Service: {service_name}
- Clinical Indication: {clinical_indication}"""


def render_diagnosis_summary(diagnosis_codes: list[Dict[str, Any]]) -> str:
    """render diagnosis codes as formatted text for prompts (shared by phase 2 and 3)"""
    if not diagnosis_codes:
        return ""
    return "\nDiagnosis Codes:\n" + "\n".join([
        f"  - {d.get('icd10')}: {d.get('description')}" for d in diagnosis_codes
    ])


def phase3_payor_procedure_summary(procedure_codes: list[Dict[str, Any]]) -> str:
    """render Phase 3 payor procedure code summary"""
    if not procedure_codes:
        return ""
    procedure_summary = "\nProcedure Codes Submitted:\n"
    for idx, proc in enumerate(procedure_codes, 1):
        procedure_summary += f"  Line {idx}: {proc.get('procedure_code')} ({proc.get('code_type')})\n"
        procedure_summary += f"    Description: {proc.get('service_description')}\n"
        procedure_summary += f"    Quantity: {proc.get('requested_quantity')}\n"
        procedure_summary += f"    Amount Billed: ${proc.get('charge_amount', 0):.2f}\n"
    return procedure_summary