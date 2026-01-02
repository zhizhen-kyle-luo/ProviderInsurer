"""
phase 3: claims adjudication with provider decision and appeal loop

applies to ALL PA types: medication, cardiac testing, imaging, etc.

workflow:
1. provider submits claim (LLM)
2. payor reviews claim (LLM)
3. if denied:
   - provider decides: write-off / appeal / bill patient (LLM)
   - if appeal: loop until max iterations OR approved OR provider stops
"""

import json
from typing import Dict, Any, TYPE_CHECKING
from datetime import timedelta
from langchain_core.messages import HumanMessage

from src.models.schemas import EncounterState, PAType
from src.utils.prompts import (
    create_provider_prompt,
    create_payor_prompt,
    create_claim_adjudication_prompt,
    create_provider_claim_submission_prompt,
    create_provider_claim_appeal_decision_prompt,
    create_provider_claim_appeal_prompt,
    create_payor_claim_appeal_review_prompt,
    MAX_ITERATIONS,
    MAX_REQUEST_INFO_PER_LEVEL
)

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def run_phase_3_claims(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any],
    pa_type: str
) -> EncounterState:
    """
    phase 3: claims adjudication with provider decision and appeal loop

    applies to ALL PA types: medication, cardiac testing, imaging, etc.
    """
    # only process claims if pa was approved
    if not state.medication_authorization or state.medication_authorization.authorization_status != "approved":
        return state

    # extract service request data based on PA type
    phase_2_evidence = getattr(state, '_phase_2_evidence', {})

    if pa_type == PAType.SPECIALTY_MEDICATION:
        service_request = case.get("medication_request", {})
        service_name = service_request.get('medication_name', 'medication')
    else:
        # for procedures, cardiac testing, imaging: use approved request from phase 2
        approved_req = phase_2_evidence.get('approved_request', {})
        requested_service = approved_req.get('requested_service', {})

        service_name = requested_service.get('service_name')
        if not service_name:
            req_details = approved_req.get('request_details', {})
            if pa_type == PAType.CARDIAC_TESTING:
                service_name = req_details.get('treatment_name', req_details.get('procedure_name', 'procedure'))
            else:
                service_name = req_details.get('treatment_name', req_details.get('test_name', 'service'))

        service_request = requested_service if requested_service else approved_req.get('request_details', {})

    cost_ref = case.get("cost_reference", {})

    # extract coding options for DRG upcoding scenarios (grey zone cases)
    environment_data = case.get("environment_hidden_data", {})
    coding_options = environment_data.get("coding_options", [])

    claim_date = state.appeal_date if state.appeal_date else state.review_date
    claim_date = claim_date + timedelta(days=7)

    # STEP 1: provider submits claim
    provider_system_prompt = create_provider_prompt()
    provider_claim_prompt = create_provider_claim_submission_prompt(
        state, service_request, cost_ref, phase_2_evidence, pa_type, coding_options
    )

    messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_claim_prompt}")]
    response = sim.provider.llm.invoke(messages)
    provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

    try:
        response_text = response.content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        claim_submission = json.loads(response_text)
    except Exception:
        default_amount = cost_ref.get('drug_acquisition_cost', cost_ref.get('procedure_cost', 7800))
        if pa_type == PAType.SPECIALTY_MEDICATION:
            default_amount += cost_ref.get('administration_fee', 150)
        claim_submission = {
            "claim_submission": {
                "service_delivered": service_name,
                "amount_billed": default_amount
            }
        }

    # log provider claim submission
    sim.audit_logger.log_interaction(
        phase="phase_3_claims",
        agent="provider",
        action="claim_submission",
        system_prompt=provider_system_prompt,
        user_prompt=provider_claim_prompt,
        llm_response=response.content,
        parsed_output=claim_submission,
        metadata={
            "service": service_name,
            "pa_type": pa_type,
            "pa_approved": True,
            "cache_hit": provider_cache_hit,
            "coding_options_available": len(coding_options) if coding_options else 0
        }
    )

    # STEP 2: payor reviews claim
    provider_billed_amount = None
    provider_diagnosis_code = None
    if claim_submission and "claim_submission" in claim_submission:
        provider_billed_amount = claim_submission["claim_submission"].get("total_amount_billed")
        diagnosis_codes = claim_submission["claim_submission"].get("diagnosis_codes", [])
        if diagnosis_codes and len(diagnosis_codes) > 0:
            provider_diagnosis_code = diagnosis_codes[0].get("icd10")

    # store on state for Phase 4 financial settlement
    state.phase_3_billed_amount = provider_billed_amount
    state.phase_3_diagnosis_code = provider_diagnosis_code

    payor_system_prompt = create_payor_prompt(sim.payor_params)
    payor_claim_prompt = create_claim_adjudication_prompt(
        state, service_request, cost_ref, case, phase_2_evidence, pa_type, provider_billed_amount
    )

    messages = [HumanMessage(content=f"{payor_system_prompt}\n\n{payor_claim_prompt}")]
    response = sim.payor.llm.invoke(messages)
    payor_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

    try:
        response_text = response.content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        claim_decision = json.loads(response_text)
    except Exception:
        claim_decision = {
            "claim_status": "approved",
            "criteria_used": "Standard billing guidelines",
            "reviewer_type": "Claims adjudicator"
        }

    # log payor claim review
    sim.audit_logger.log_interaction(
        phase="phase_3_claims",
        agent="payor",
        action="claim_review",
        system_prompt=payor_system_prompt,
        user_prompt=payor_claim_prompt,
        llm_response=response.content,
        parsed_output=claim_decision,
        metadata={
            "service": service_name,
            "pa_type": pa_type,
            "claim_status": claim_decision.get("claim_status"),
            "cache_hit": payor_cache_hit
        }
    )

    # update state with claim decision
    claim_status = claim_decision.get("claim_status")

    # normalize legacy "denied" to "rejected" for consistency
    if claim_status == "denied":
        claim_status = "rejected"
        claim_decision["claim_status"] = "rejected"

    state.medication_authorization.authorization_status = claim_status

    if claim_status == "rejected":
        state.claim_rejected = True
        state.medication_authorization.denial_reason = claim_decision.get("rejection_reason", claim_decision.get("denial_reason"))
    elif claim_status == "pended":
        state.claim_pended = True

    # STEP 3a: if claim REJECTED (formal denial), provider decides what to do
    if claim_status == "rejected":
        state = _handle_rejected_claim(
            sim, state, claim_decision, service_request, phase_2_evidence,
            pa_type, service_name, cost_ref, claim_date, provider_system_prompt, payor_system_prompt
        )

    # STEP 3b: if claim PENDED (RFI), handle pend resubmission loop
    elif claim_status == "pended":
        state = _handle_pended_claim(
            sim, state, claim_decision, service_request, phase_2_evidence,
            pa_type, cost_ref, provider_system_prompt, payor_system_prompt
        )

    return state


def _handle_rejected_claim(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    claim_decision: Dict[str, Any],
    service_request: Dict[str, Any],
    phase_2_evidence: Dict[str, Any],
    pa_type: str,
    service_name: str,
    cost_ref: Dict[str, Any],
    claim_date,
    provider_system_prompt: str,
    payor_system_prompt: str
) -> EncounterState:
    """handle rejected claim with appeal decision and loop"""
    denial_reason = claim_decision.get("denial_reason", "Claim denied")
    state.appeal_date = claim_date + timedelta(days=2)

    # provider decision: discrete action space (CONTINUE/APPEAL/ABANDON)
    provider_decision_prompt = create_provider_claim_appeal_decision_prompt(
        state, denial_reason, service_request, pa_type
    )

    messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_decision_prompt}")]
    response = sim.provider.llm.invoke(messages)
    provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

    try:
        response_text = response.content
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        provider_decision = json.loads(response_text)
    except Exception:
        provider_decision = {"action": "ABANDON", "rationale": "Unable to parse decision"}

    # log provider decision
    sim.audit_logger.log_interaction(
        phase="phase_3_claims",
        agent="provider",
        action="claim_denial_decision",
        system_prompt=provider_system_prompt,
        user_prompt=provider_decision_prompt,
        llm_response=response.content,
        parsed_output=provider_decision,
        metadata={"action": provider_decision.get("action"), "cache_hit": provider_cache_hit}
    )

    # STEP 4: appeal loop if provider chooses to appeal
    if provider_decision.get("action") == "APPEAL":
        state.appeal_filed = True
        appeal_iteration = 0
        claim_approved = False
        appeal_history = []

        while appeal_iteration < MAX_ITERATIONS and not claim_approved:
            appeal_iteration += 1

            # provider submits appeal (with history of previous attempts)
            provider_appeal_prompt = create_provider_claim_appeal_prompt(
                state, denial_reason, service_request, phase_2_evidence, pa_type, appeal_history
            )

            messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_appeal_prompt}")]
            response = sim.provider.llm.invoke(messages)
            provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

            try:
                response_text = response.content
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                appeal_letter = json.loads(response_text)
            except Exception:
                appeal_letter = {
                    "appeal_letter": {
                        "denial_addressed": "Addressing denial reason",
                        "requested_action": "full payment"
                    }
                }

            # log provider appeal submission
            sim.audit_logger.log_interaction(
                phase="phase_3_claims",
                agent="provider",
                action="claim_appeal_submission",
                system_prompt=provider_system_prompt,
                user_prompt=provider_appeal_prompt,
                llm_response=response.content,
                parsed_output=appeal_letter,
                metadata={
                    "appeal_iteration": appeal_iteration,
                    "service": service_name,
                    "cache_hit": provider_cache_hit
                }
            )

            # payor reviews appeal
            payor_appeal_prompt = create_payor_claim_appeal_review_prompt(
                state, appeal_letter.get("appeal_letter", appeal_letter),
                denial_reason, service_request, cost_ref, phase_2_evidence, pa_type
            )

            messages = [HumanMessage(content=f"{payor_system_prompt}\n\n{payor_appeal_prompt}")]
            response = sim.payor.llm.invoke(messages)
            payor_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

            try:
                response_text = response.content
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                appeal_decision = json.loads(response_text)
            except Exception:
                appeal_decision = {
                    "appeal_outcome": "denied",
                    "rationale": "Unable to parse appeal decision"
                }

            # log payor appeal review
            sim.audit_logger.log_interaction(
                phase="phase_3_claims",
                agent="payor",
                action="claim_appeal_review",
                system_prompt=payor_system_prompt,
                user_prompt=payor_appeal_prompt,
                llm_response=response.content,
                parsed_output=appeal_decision,
                metadata={
                    "appeal_iteration": appeal_iteration,
                    "appeal_outcome": appeal_decision.get("appeal_outcome"),
                    "cache_hit": payor_cache_hit
                }
            )

            # check appeal outcome
            if appeal_decision.get("appeal_outcome") == "approved":
                state.medication_authorization.authorization_status = "approved"
                state.appeal_successful = True
                claim_approved = True
            elif appeal_decision.get("appeal_outcome") == "partial":
                state.medication_authorization.authorization_status = "partial"
                state.appeal_successful = True
                claim_approved = True
            else:
                # appeal denied - record this attempt in history
                denial_reason = appeal_decision.get("denial_reason", "Appeal denied")

                appeal_summary = f"""Appeal #{appeal_iteration}:
Arguments Made: {json.dumps(appeal_letter.get('appeal_letter', appeal_letter), indent=2)}
Outcome: DENIED
Payor Reasoning: {denial_reason}
"""
                appeal_history.append(appeal_summary)

                # ask provider: continue or abandon
                provider_continue_prompt = f"""APPEAL DENIED - CHOOSE YOUR ACTION

Your appeal was denied with the following reason:
{denial_reason}

Appeals filed so far: {appeal_iteration}
Maximum appeals allowed: {MAX_ITERATIONS}

YOUR DISCRETE ACTION SPACE:
1. CONTINUE: Provide additional evidence at current review level
   - Same reviewer reconsiders with supplemented record

2. APPEAL: Escalate to next administrative authority
   - Triggers next procedural layer (e.g., independent review)

3. ABANDON: Exit the dispute
   - Accept the denial, stop contesting

Respond in JSON:
{{
    "action": "CONTINUE" | "APPEAL" | "ABANDON",
    "rationale": "<brief explanation>"
}}
"""

                messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_continue_prompt}")]
                response = sim.provider.llm.invoke(messages)

                try:
                    response_text = response.content
                    if "```json" in response_text:
                        response_text = response_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in response_text:
                        response_text = response_text.split("```")[1].split("```")[0].strip()
                    continue_decision = json.loads(response_text)
                except Exception:
                    continue_decision = {"action": "ABANDON", "rationale": "Parse error - default to ABANDON"}

                # log provider decision
                sim.audit_logger.log_interaction(
                    phase="phase_3_claims",
                    agent="provider",
                    action="appeal_continuation_decision",
                    system_prompt=provider_system_prompt,
                    user_prompt=provider_continue_prompt,
                    llm_response=response.content,
                    parsed_output=continue_decision,
                    metadata={
                        "appeal_iteration": appeal_iteration,
                        "action": continue_decision.get("action")
                    }
                )

                if continue_decision.get("action") == "ABANDON":
                    break

    return state


def _handle_pended_claim(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    claim_decision: Dict[str, Any],
    service_request: Dict[str, Any],
    phase_2_evidence: Dict[str, Any],
    pa_type: str,
    cost_ref: Dict[str, Any],
    provider_system_prompt: str,
    payor_system_prompt: str
) -> EncounterState:
    """handle pended claim with resubmission loop"""
    from src.utils.prompts import (
        create_provider_pend_response_prompt,
        create_provider_claim_resubmission_prompt,
        create_payor_claim_resubmission_review_prompt
    )

    pend_iteration = 0
    claim_resolved = False
    current_pend_decision = claim_decision

    while pend_iteration < MAX_REQUEST_INFO_PER_LEVEL and not claim_resolved:
        pend_iteration += 1
        state.pend_iterations = pend_iteration

        # provider decides: resubmit or abandon
        provider_pend_prompt = create_provider_pend_response_prompt(
            state, current_pend_decision, service_request, pend_iteration, pa_type
        )

        messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_pend_prompt}")]
        response = sim.provider.llm.invoke(messages)
        provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

        try:
            response_text = response.content
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            provider_pend_decision = json.loads(response_text)
        except Exception:
            provider_pend_decision = {"action": "ABANDON", "rationale": "Unable to parse decision"}

        # log provider pend response decision
        sim.audit_logger.log_interaction(
            phase="phase_3_claims",
            agent="provider",
            action="pend_response_decision",
            system_prompt=provider_system_prompt,
            user_prompt=provider_pend_prompt,
            llm_response=response.content,
            parsed_output=provider_pend_decision,
            metadata={
                "action": provider_pend_decision.get("action"),
                "pend_iteration": pend_iteration,
                "cache_hit": provider_cache_hit
            }
        )

        # if provider abandons, mark and exit
        if provider_pend_decision.get("action") == "ABANDON":
            state.claim_abandoned_via_pend = True
            state.medication_authorization.authorization_status = "pended"
            claim_resolved = True
            break

        # provider prepares resubmission packet
        provider_resubmit_prompt = create_provider_claim_resubmission_prompt(
            state, current_pend_decision, service_request, phase_2_evidence, pa_type
        )

        messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_resubmit_prompt}")]
        response = sim.provider.llm.invoke(messages)
        provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

        try:
            response_text = response.content
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            resubmission_packet = json.loads(response_text)
        except Exception:
            resubmission_packet = {"resubmission_packet": {"cover_letter": "Resubmitting with additional documentation"}}

        # log provider resubmission
        sim.audit_logger.log_interaction(
            phase="phase_3_claims",
            agent="provider",
            action="claim_resubmission",
            system_prompt=provider_system_prompt,
            user_prompt=provider_resubmit_prompt,
            llm_response=response.content,
            parsed_output=resubmission_packet,
            metadata={"pend_iteration": pend_iteration, "cache_hit": provider_cache_hit}
        )

        # payor reviews resubmission
        payor_resubmit_prompt = create_payor_claim_resubmission_review_prompt(
            state, resubmission_packet.get("resubmission_packet", resubmission_packet),
            current_pend_decision, service_request, cost_ref, pend_iteration, pa_type
        )

        messages = [HumanMessage(content=f"{payor_system_prompt}\n\n{payor_resubmit_prompt}")]
        response = sim.payor.llm.invoke(messages)
        payor_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

        try:
            response_text = response.content
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            resubmission_review = json.loads(response_text)
        except Exception:
            resubmission_review = {"claim_status": "approved", "approved_amount": cost_ref.get('procedure_cost', 7800)}

        # log payor resubmission review
        sim.audit_logger.log_interaction(
            phase="phase_3_claims",
            agent="payor",
            action="resubmission_review",
            system_prompt=payor_system_prompt,
            user_prompt=payor_resubmit_prompt,
            llm_response=response.content,
            parsed_output=resubmission_review,
            metadata={
                "pend_iteration": pend_iteration,
                "claim_status": resubmission_review.get("claim_status"),
                "cache_hit": payor_cache_hit
            }
        )

        # check resubmission outcome
        resubmission_status = resubmission_review.get("claim_status")

        if resubmission_status == "approved":
            state.medication_authorization.authorization_status = "approved"
            claim_resolved = True
        elif resubmission_status == "rejected":
            state.medication_authorization.authorization_status = "rejected"
            state.claim_rejected = True
            state.medication_authorization.denial_reason = resubmission_review.get("rejection_reason", "Claim rejected after resubmission")
            claim_resolved = True
        elif resubmission_status == "pended":
            current_pend_decision = resubmission_review
        else:
            state.medication_authorization.authorization_status = "approved"
            claim_resolved = True

    # if max pends reached and still pended, force rejection
    if pend_iteration >= MAX_REQUEST_INFO_PER_LEVEL and not claim_resolved:
        state.medication_authorization.authorization_status = "rejected"
        state.claim_rejected = True
        state.medication_authorization.denial_reason = "Maximum resubmission attempts exceeded"

    return state
