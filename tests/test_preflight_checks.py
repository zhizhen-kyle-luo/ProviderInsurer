"""
Lightweight preflight checks to catch prompt/data mismatches before long runs.
Run: python tests/test_preflight_checks.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.data.case_registry import get_case
from src.data.case_converter import convert_case_to_models
from src.models.authorization import AuthorizationRequest
from src.models.state import EncounterState
from src.utils.prompts import (
    create_unified_provider_request_prompt,
    create_unified_phase3_provider_request_prompt,
    create_unified_phase3_payor_review_prompt,
)


def _extract_amount_billed(prompt: str) -> float | None:
    for line in prompt.splitlines():
        if "Amount Billed:" not in line:
            continue
        match = re.search(r"\$([\d,]+(?:\.\d{2})?)", line)
        if not match:
            continue
        return float(match.group(1).replace(",", ""))
    return None


def _build_state(case_id: str) -> EncounterState:
    case = convert_case_to_models(get_case(case_id))
    state = EncounterState(
        case_id=case["case_id"],
        admission=case["admission"],
        clinical_presentation=case["clinical_presentation"],
        case_type=case["case_type"],
    )
    return state


def main() -> int:
    failures: list[str] = []

    case_id = "infliximab_crohns_2015"
    case = convert_case_to_models(get_case(case_id))
    state = _build_state(case_id)

    # Phase 2 provider prompt should not mention aggressiveness.
    p2_prompt = create_unified_provider_request_prompt(state, case, 0, [])
    if "Authorization aggressiveness" in p2_prompt:
        failures.append("Phase 2 provider prompt still mentions aggressiveness.")

    # Phase 3 provider prompt: PA approved implies service delivered.
    state.authorization_request = AuthorizationRequest(
        request_type="treatment",
        service_name="Infliximab",
        clinical_rationale="test",
        diagnosis_codes=["K50.012"],
        authorization_status="approved",
    )
    p3_provider_prompt = create_unified_phase3_provider_request_prompt(
        state=state,
        case=case,
        iteration=0,
        prior_iterations=[],
        stage="initial_determination",
        service_request={"medication_name": "Infliximab", "dosage": "5 mg/kg"},
        cost_ref=case.get("cost_reference", {}),
        phase_2_evidence={},
        case_type=case["case_type"],
        coding_options=[],
    )
    if "assume it WAS delivered as authorized" not in p3_provider_prompt:
        failures.append("Phase 3 provider prompt missing delivered-service assumption.")
    if "Medication: Infliximab" not in p3_provider_prompt:
        failures.append("Phase 3 provider prompt missing medication name.")
    if "Authorization aggressiveness" in p3_provider_prompt:
        failures.append("Phase 3 provider prompt still mentions aggressiveness.")
    if "Submit a payable, itemized claim" not in p3_provider_prompt:
        failures.append("Phase 3 provider prompt missing itemized-claim instruction for approved PA.")

    # Phase 3 payor prompt should compute Amount Billed from procedure codes.
    provider_request = {
        "diagnosis_codes": [{"icd10": "K50.012", "description": "Crohn's"}],
        "procedure_codes": [
            {"code": "J1745", "code_type": "J-code", "description": "Infliximab", "quantity": 10, "amount_billed": 100.0},
            {"code": "96413", "code_type": "CPT", "description": "Infusion", "quantity": 1, "amount_billed": 250.0},
        ],
        # deliberately omit total_amount_billed to test fallback
    }
    payor_prompt = create_unified_phase3_payor_review_prompt(
        state=state,
        provider_request=provider_request,
        iteration=0,
        stage="initial_determination",
        level=0,
        service_request={"medication_name": "Infliximab", "dosage": "5 mg/kg"},
        cost_ref=None,
        case=case,
        phase_2_evidence={},
        case_type=case["case_type"],
        provider_billed_amount=None,
    )
    amount_billed = _extract_amount_billed(payor_prompt)
    if amount_billed != 1250.00:
        failures.append(f"Phase 3 payor prompt Amount Billed expected $1250.00, got {amount_billed}.")
    if "Line 1: J1745" not in payor_prompt or "Line 2: 96413" not in payor_prompt:
        failures.append("Phase 3 payor prompt missing procedure line details.")
    if "Decision options: approved | denied | pending_info" not in payor_prompt:
        failures.append("Phase 3 level 0 payor prompt missing pending_info option.")

    # Phase 3 payor prompt: level 2 should not allow pending_info.
    payor_prompt_level2 = create_unified_phase3_payor_review_prompt(
        state=state,
        provider_request=provider_request,
        iteration=2,
        stage="independent_review",
        level=2,
        service_request={"medication_name": "Infliximab", "dosage": "5 mg/kg"},
        cost_ref=None,
        case=case,
        phase_2_evidence={},
        case_type=case["case_type"],
        provider_billed_amount=None,
    )
    if "Decision options: approved | denied" not in payor_prompt_level2:
        failures.append("Phase 3 level 2 payor prompt still allows pending_info.")
    if "REQUEST_INFO (pending_info) is NOT available at this level." not in payor_prompt_level2:
        failures.append("Phase 3 level 2 payor prompt missing no-pend warning.")

    # AuthorizationRequest should not expose deprecated approved_quantity.
    if "approved_quantity" in AuthorizationRequest.model_fields:
        failures.append("AuthorizationRequest still has approved_quantity field.")

    # Phase 3 payor prompt should show Amount Billed with commas and quantity math.
    provider_request_with_commas = {
        "diagnosis_codes": [{"icd10": "K50.012", "description": "Crohn's"}],
        "procedure_codes": [
            {"code": "J1745", "code_type": "J-code", "description": "Infliximab", "quantity": 1, "amount_billed": 1000.0},
            {"code": "96413", "code_type": "CPT", "description": "Infusion", "quantity": 2, "amount_billed": 250.0},
        ],
    }
    payor_prompt_commas = create_unified_phase3_payor_review_prompt(
        state=state,
        provider_request=provider_request_with_commas,
        iteration=0,
        stage="initial_determination",
        level=0,
        service_request={"medication_name": "Infliximab", "dosage": "5 mg/kg"},
        cost_ref=None,
        case=case,
        phase_2_evidence={},
        case_type=case["case_type"],
        provider_billed_amount=None,
    )
    amount_billed_commas = _extract_amount_billed(payor_prompt_commas)
    if amount_billed_commas != 1500.00:
        failures.append(f"Phase 3 payor prompt Amount Billed expected $1500.00, got {amount_billed_commas}.")
    if "Amount Billed: $1,500.00" not in payor_prompt_commas:
        failures.append("Phase 3 payor prompt missing comma formatting for Amount Billed.")

    if failures:
        print("Preflight checks failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
