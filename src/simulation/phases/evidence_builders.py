"""build evidence packets for oversight editing"""
from typing import Dict, Any, List

from src.models import EncounterState


def build_provider_evidence_packet(
    state: EncounterState,
    case: Dict[str, Any],
    prior_iterations: List[Dict]
) -> Dict[str, Any]:
    """build evidence packet for provider oversight editing"""
    patient_data = case.get("patient_visible_data", {})
    # collect test results from prior iterations
    test_results = {}
    for iteration in prior_iterations:
        if "test_results" in iteration:
            test_results.update(iteration["test_results"])

    return {
        "vitals": patient_data.get("vital_signs", {}),
        "labs": case.get("available_test_results", {}).get("labs", {}),
        "icd10_codes": [],
        "cpt_codes": [],
        "test_results": test_results,
        "prior_denials": [
            it.get("payor_decision_reason")
            for it in prior_iterations
            if it.get("payor_decision") == "denied"
        ],
        "stage": state.provider_policy_view.get("content", {}).get("data", {}).get("policy_name", "") if state.provider_policy_view else ""
    }


def build_payor_evidence_packet(
    state: EncounterState,
    provider_request: Dict[str, Any]
) -> Dict[str, Any]:
    """build evidence packet for payor oversight editing"""
    policy_view = state.payor_policy_view or {}
    content_data = policy_view.get("content", {}).get("data", {})

    return {
        "policy_content": content_data,
        "missing_items": provider_request.get("decision_reason", []),
        "provider_diagnosis_codes": [
            d.get("icd10") for d in provider_request.get("diagnosis_codes", [])
        ],
        "provider_clinical_notes": provider_request.get("clinical_notes", "")
    }
