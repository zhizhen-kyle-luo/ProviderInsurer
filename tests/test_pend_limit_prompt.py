#!/usr/bin/env python3
"""test that pend limit enforcement appears correctly in payor prompts"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.data.case_registry import get_case
from src.data.case_converter import convert_case_to_models
from src.models.authorization import AuthorizationRequest
from src.models.state import EncounterState
from src.utils.prompts import (
    create_unified_payor_review_prompt,
    create_unified_phase3_payor_review_prompt,
    MAX_REQUEST_INFO_PER_LEVEL,
)


def test_phase2_pend_limit_in_prompt():
    """verify phase 2 prompt shows pend limit warning when limit reached"""
    case_id = "infliximab_crohns_2015"
    case = convert_case_to_models(get_case(case_id))
    state = EncounterState(
        case_id=case["case_id"],
        admission=case["admission"],
        clinical_presentation=case["clinical_presentation"],
        case_type=case["case_type"],
    )
    state.provider_policy_view = {"policy_name": "stub", "content": {"data": {}}}
    state.payor_policy_view = {"policy_name": "stub", "content": {"data": {}}}

    provider_request = {
        "request_type": "treatment",
        "requested_service": {"service_name": "Infliximab"},
        "diagnosis_codes": [{"icd10": "K50.012", "description": "Crohn's"}],
    }

    # prompt with pend_count < limit: should allow pending_info in decision options
    prompt_below_limit = create_unified_payor_review_prompt(
        state=state,
        provider_request=provider_request,
        iteration=0,
        level=0,
        pend_count_at_level=0,
    )
    assert "Decision options: approved | modified | denied | pending_info" in prompt_below_limit
    assert "maximum REQUEST_INFO limit" not in prompt_below_limit

    # prompt with pend_count = limit: should show warning and remove pending_info from decision options
    prompt_at_limit = create_unified_payor_review_prompt(
        state=state,
        provider_request=provider_request,
        iteration=0,
        level=0,
        pend_count_at_level=MAX_REQUEST_INFO_PER_LEVEL,
    )
    assert "Decision options: approved | modified | denied | pending_info" not in prompt_at_limit
    assert "Decision options: approved | modified | denied" in prompt_at_limit
    assert f"maximum REQUEST_INFO limit ({MAX_REQUEST_INFO_PER_LEVEL} pends)" in prompt_at_limit
    assert "NO LONGER available" in prompt_at_limit

    print(f"phase 2 pend limit prompt test passed (limit={MAX_REQUEST_INFO_PER_LEVEL})")


def test_phase3_pend_limit_in_prompt():
    """verify phase 3 prompt shows pend limit warning when limit reached"""
    case_id = "infliximab_crohns_2015"
    case = convert_case_to_models(get_case(case_id))
    state = EncounterState(
        case_id=case["case_id"],
        admission=case["admission"],
        clinical_presentation=case["clinical_presentation"],
        case_type=case["case_type"],
    )
    state.provider_policy_view = {"policy_name": "stub", "content": {"data": {}}}
    state.payor_policy_view = {"policy_name": "stub", "content": {"data": {}}}
    state.authorization_request = AuthorizationRequest(
        request_type="treatment",
        service_name="Infliximab",
        clinical_rationale="test",
        diagnosis_codes=["K50.012"],
        authorization_status="approved",
    )

    provider_request = {
        "diagnosis_codes": [{"icd10": "K50.012", "description": "Crohn's"}],
        "procedure_codes": [
            {"code": "J1745", "code_type": "J-code", "description": "Infliximab", "requested_quantity": 10, "charge_amount": 100.0},
        ],
    }

    # prompt with pend_count < limit: should allow pending_info in decision options
    prompt_below_limit = create_unified_phase3_payor_review_prompt(
        state=state,
        provider_request=provider_request,
        iteration=0,
        level=0,
        service_request={"medication_name": "Infliximab", "dosage": "5 mg/kg"},
        cost_ref=None,
        case=case,
        phase_2_evidence={},
        case_type=case["case_type"],
        provider_billed_amount=None,
        pend_count_at_level=0,
    )
    assert "Decision options: approved | modified | denied | pending_info" in prompt_below_limit
    assert "maximum REQUEST_INFO limit" not in prompt_below_limit

    # prompt with pend_count = limit: should show warning and remove pending_info from decision options
    prompt_at_limit = create_unified_phase3_payor_review_prompt(
        state=state,
        provider_request=provider_request,
        iteration=0,
        level=0,
        service_request={"medication_name": "Infliximab", "dosage": "5 mg/kg"},
        cost_ref=None,
        case=case,
        phase_2_evidence={},
        case_type=case["case_type"],
        provider_billed_amount=None,
        pend_count_at_level=MAX_REQUEST_INFO_PER_LEVEL,
    )
    assert "Decision options: approved | modified | denied | pending_info" not in prompt_at_limit
    assert "Decision options: approved | modified | denied" in prompt_at_limit
    assert f"maximum REQUEST_INFO limit ({MAX_REQUEST_INFO_PER_LEVEL} pends)" in prompt_at_limit
    assert "NO LONGER available" in prompt_at_limit

    print(f"phase 3 pend limit prompt test passed (limit={MAX_REQUEST_INFO_PER_LEVEL})")


if __name__ == "__main__":
    test_phase2_pend_limit_in_prompt()
    test_phase3_pend_limit_in_prompt()
    print("\nall pend limit prompt tests passed!")
