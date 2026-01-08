"""
phase 3: claims adjudication with 3-level unified review workflow

Uses unified_review.py for core 3-level logic, same structure as Phase 2:
- level 0: initial_determination (claims review)
- level 1: internal_appeal (medical reviewer appeal review)
- level 2: independent_review (final IRE review, no pend)
"""

from typing import Dict, Any, TYPE_CHECKING
from src.models.schemas import EncounterState
from src.utils.prompts import (
    create_phase3_claim_submission_decision_prompt,
    create_unified_phase3_provider_request_prompt,
    create_unified_phase3_payor_review_prompt
)
from src.simulation.phases.unified_review import run_unified_multi_level_review

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def _provider_claim_submission_decision(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    _case: Dict[str, Any],
    _case_type: str
) -> str:
    """
    Provider decides whether to submit a claim for payment.

    Returns: "submit_claim" or "skip"

    CRITICAL: This decision happens even if PA was denied.
    """
    import json
    from langchain_core.messages import HumanMessage
    if not state.authorization_request:
        return "skip"
    pa_status = state.authorization_request.authorization_status
    if pa_status == "approved":
        return "submit_claim"

    # PA was denied - provider must decide whether to submit claim anyway
    denial_reason = state.authorization_request.denial_reason if hasattr(state.authorization_request, 'denial_reason') else "Not specified"

    prompt = create_phase3_claim_submission_decision_prompt(
        state=state,
        pa_status=pa_status,
        denial_reason=denial_reason,
    )

    response = sim.provider.llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content.strip()

    # parse decision
    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        decision_data = json.loads(response_text)
        decision = decision_data.get("decision", "skip")

        return decision if decision in ["submit_claim", "skip"] else "skip"

    except (json.JSONDecodeError, KeyError) as e:
        # parsing failed - raise error to surface the bug
        raise ValueError(f"failed to parse provider claim submission decision: {e}\nResponse: {response_text}")


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

    CRITICAL: Provider decides whether to submit claim even if PA was denied
    """
    # provider decision: should I submit a claim? this decision is made even if PA was denied
    provider_decision = _provider_claim_submission_decision(sim, state, case, case_type)

    if provider_decision == "skip":
        #internal flow control, not an action in the action space
        return state

    # extract service details from authorization_request (unified across all case types)
    if state.authorization_request:
        service_request = {
            "service_name": state.authorization_request.service_name,
            "dosage": state.authorization_request.dosage,
            "frequency": state.authorization_request.frequency,
            "clinical_rationale": state.authorization_request.clinical_rationale,
            "cpt_code": state.authorization_request.cpt_code,
            "ndc_code": state.authorization_request.ndc_code,
            "j_code": state.authorization_request.j_code,
        }
        if case_type == "specialty_medication":
            service_request["medication_name"] = state.authorization_request.service_name
    else:
        service_request = {}

    cost_ref = case.get("cost_reference", {})
    phase_2_evidence = {}

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
