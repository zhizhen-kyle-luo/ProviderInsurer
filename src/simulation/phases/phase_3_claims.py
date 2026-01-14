"""
phase 3: claims adjudication with 3-level unified review workflow

Uses unified_review.py for core 3-level logic, same structure as Phase 2:
- level 0: initial_determination (claims review)
- level 1: internal_appeal (medical reviewer appeal review)
- level 2: independent_review (final IRE review, no pend)
"""

from typing import Dict, Any, TYPE_CHECKING
from src.models import EncounterState
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

    # must have service lines from Phase 2
    if not state.service_lines:
        return "skip"

    # check first service line status (MVP: single line)
    first_line = state.service_lines[0]
    p2_status = first_line.authorization_status

    if p2_status == "approved":
        return "submit_claim"

    # PA was denied/modified/pended - provider must decide whether to submit claim anyway
    decision_reason = "Not specified"
    if first_line.decision_reason:
        decision_reason = "; ".join(first_line.decision_reason)

    prompt = create_phase3_claim_submission_decision_prompt(
        state=state,
        p2_status=p2_status,
        decision_reason=decision_reason,
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
        # internal flow control, not an action in the action space
        return state

    # REUSE service_lines from Phase 2 (already populated by unified_review.py)
    # extract service details from first service line (MVP: single line)
    if not state.service_lines:
        raise ValueError("Phase 3: no service lines found - Phase 2 must populate service_lines")

    first_line = state.service_lines[0]

    # build service_request dict for prompts (maintains backward compatibility with existing prompts)
    service_request = {
        "service_name": first_line.service_name,
        "dosage": first_line.dosage,
        "frequency": first_line.frequency,
        "clinical_rationale": first_line.clinical_rationale,
        "cpt_code": first_line.cpt_code,
        "ndc_code": first_line.ndc_code,
        "j_code": first_line.j_code,
    }

    if case_type == "specialty_medication":
        service_request["medication_name"] = first_line.service_name

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