"""
phase 3: claims adjudication with 3-level unified review workflow

applies to ALL PA types: medication, cardiac testing, imaging, etc.

PHASE 3 = RETROSPECTIVE REVIEW / CLAIMS ADJUDICATION:
- Timing: AFTER care is completed
- Record status: FIXED - clinical events already happened
- Payor can: REQUEST_INFO only for existing documentation (discharge summary, etc)
- Decision: PAYMENT for services already rendered

Uses unified_review.py for core 3-level logic, same structure as Phase 2:
- level 0: initial_determination (claims review)
- level 1: internal_appeal (medical reviewer appeal review)
- level 2: independent_review (final IRE review, no pend)
"""

from typing import Dict, Any, TYPE_CHECKING
from src.models.schemas import EncounterState, CaseType
from src.utils.prompts import (
    create_unified_phase3_provider_request_prompt,
    create_unified_phase3_payor_review_prompt
)
from src.simulation.phases.unified_review import run_unified_multi_level_review

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def run_phase_3_claims(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any],
    case_type: str
) -> EncounterState:
    """
    phase 3: claims adjudication with unified 3-level review workflow

    PHASE 3 = RETROSPECTIVE REVIEW:
    - Timing: AFTER care is completed
    - Record is FIXED: cannot order new tests, only clarify existing documentation
    - Decision: PAYMENT for services already rendered
    - Uses same 3-level WORKFLOW_LEVELS as Phase 2, but with different operational context

    applies to all case types: medication, cardiac testing, imaging, etc.
    """
    # only process claims if pa was approved
    if not state.authorization_request or state.authorization_request.authorization_status != "approved":
        return state

    # extract service request data based on PA type
    phase_2_evidence = getattr(state, '_phase_2_evidence', {})

    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_request = case.get("medication_request", {})
    else:
        # for procedures, cardiac testing, imaging: use approved request from phase 2
        approved_req = phase_2_evidence.get('approved_request', {})
        requested_service = approved_req.get('requested_service', {})
        service_request = requested_service if requested_service else approved_req.get('request_details', {})

    cost_ref = case.get("cost_reference", {})

    # extract coding options for DRG upcoding scenarios (grey zone cases)
    environment_data = case.get("environment_hidden_data", {})
    coding_options = environment_data.get("coding_options", [])

    # Call unified review with Phase 3 prompts
    state = run_unified_multi_level_review(
        sim=sim,
        state=state,
        case=case,
        phase="phase_3_claims",
        provider_prompt_fn=create_unified_phase3_provider_request_prompt,
        payor_prompt_fn=create_unified_phase3_payor_review_prompt,
        provider_prompt_kwargs={
            "service_request": service_request,
            "cost_ref": cost_ref,
            "phase_2_evidence": phase_2_evidence,
            "case_type": case_type,
            "coding_options": coding_options
        },
        payor_prompt_kwargs={
            "service_request": service_request,
            "cost_ref": cost_ref,
            "case": case,
            "phase_2_evidence": phase_2_evidence,
            "case_type": case_type,
            "provider_billed_amount": getattr(state, 'phase_3_billed_amount', None)
        },
        max_iterations=sim.max_iterations
    )

    return state
