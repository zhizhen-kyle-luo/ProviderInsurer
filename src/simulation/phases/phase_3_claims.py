"""
phase 3: claims adjudication with 3-level unified review workflow

Uses unified_review.py for core 3-level logic, same structure as Phase 2:
- level 0: initial_determination (claims review)
- level 1: internal_appeal (medical reviewer appeal review)
- level 2: independent_review (final IRE review, no pend)
"""

from typing import Dict, Any, List, TYPE_CHECKING
from src.models import EncounterState, ServiceLineRequest
from src.utils.prompts import (
    create_phase3_claim_submission_decision_prompt,
    create_unified_phase3_provider_request_prompt,
    create_unified_phase3_payor_review_prompt
)
from src.simulation.phases.unified_review import run_unified_multi_level_review

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def _build_service_requests_from_lines(
    service_lines: List[ServiceLineRequest],
    case_type: str
) -> List[Dict[str, Any]]:
    """build service_request dicts from all service lines for prompts"""
    service_requests = []
    for line in service_lines:
        service_request = {
            "line_number": line.line_number,
            "service_name": line.service_name,
            "dosage": line.dosage,
            "frequency": line.frequency,
            "clinical_rationale": line.clinical_rationale,
            "cpt_code": line.cpt_code,
            "ndc_code": line.ndc_code,
            "j_code": line.j_code,
            "procedure_code": line.procedure_code,
            "code_type": line.code_type,
            "service_description": line.service_description,
            "requested_quantity": line.requested_quantity,
        }
        if case_type == "specialty_medication":
            service_request["medication_name"] = line.service_name
        service_requests.append(service_request)
    return service_requests


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

    if not state.service_lines:
        return "skip"

    # check if any service line was approved - auto-submit if so
    any_approved = any(
        line.authorization_status == "approved" for line in state.service_lines
    )
    if any_approved:
        return "submit_claim"

    # build per-line status summary
    line_summaries = []
    for line in state.service_lines:
        status = line.authorization_status or "unknown"
        reason = line.decision_reason or "not specified"
        line_summaries.append(f"Line {line.line_number}: {status} - {reason}")

    p2_status = "; ".join(line_summaries) if line_summaries else "unknown"
    decision_reason = p2_status  # same info, per-line breakdown

    prompt = create_phase3_claim_submission_decision_prompt(
        state=state,
        p2_status=p2_status,
        decision_reason=decision_reason,
    )

    response = sim.provider.llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content.strip()

    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        decision_data = json.loads(response_text)
        decision = decision_data.get("decision", "skip")

        return decision if decision in ["submit_claim", "skip"] else "skip"

    except (json.JSONDecodeError, KeyError) as e:
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
    provider_decision = _provider_claim_submission_decision(sim, state, case, case_type)

    if provider_decision == "skip":
        return state

    if not state.service_lines:
        raise ValueError("Phase 3: no service lines found - Phase 2 must populate service_lines")

    # build service_requests from all lines
    service_requests = _build_service_requests_from_lines(state.service_lines, case_type)

    # for backwards compatibility, also provide single service_request (first line)
    service_request = service_requests[0] if service_requests else {}

    cost_ref = case.get("cost_reference", {})
    phase_2_evidence = {}

    environment_data = case.get("environment_hidden_data", {})
    coding_options = environment_data.get("coding_options", [])

    state = run_unified_multi_level_review(
        sim=sim,
        state=state,
        case=case,
        phase="phase_3_claims",
        provider_prompt_fn=create_unified_phase3_provider_request_prompt,
        payor_prompt_fn=create_unified_phase3_payor_review_prompt,
        provider_prompt_kwargs={
            "service_request": service_request,
            "service_requests": service_requests,
            "cost_ref": cost_ref,
            "phase_2_evidence": phase_2_evidence,
            "case_type": case_type,
            "coding_options": coding_options
        },
        payor_prompt_kwargs={
            "service_request": service_request,
            "service_requests": service_requests,
            "cost_ref": cost_ref,
            "case": case,
            "phase_2_evidence": phase_2_evidence,
            "case_type": case_type,
            "provider_billed_amount": getattr(state, 'phase_3_billed_amount', None)
        },
        max_iterations=sim.max_iterations
    )

    return state