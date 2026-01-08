"""
unified_review.py: core 3-level review workflow for both Phase 2 and Phase 3

The key distinction:
- Phase 2 = pre-adjudication utilization review (prospective PA / concurrent review)
  - Record is EVOLVING: provider can order tests, add documentation
  - Payor can PEND: request additional clinical info
  - Decision: whether to AUTHORIZE care to proceed

- Phase 3 = retrospective review / claims adjudication
  - Record is FIXED: clinical events already happened
  - Payor can REQUEST_INFO: only for existing documentation (discharge summary, etc)
  - Decision: whether to PAY for care already rendered

Both phases use the same 3-level WORKFLOW_LEVELS structure:
- Level 0: initial_determination (automated/checklist review)
- Level 1: internal_appeal (medical director review)
- Level 2: independent_review (final clinical review, no pend)
"""

import json
from typing import Dict, Any, List, Callable, TYPE_CHECKING
from langchain_core.messages import HumanMessage

from src.models.schemas import (
    EncounterState,
    AuthorizationRequest
)
from src.utils.prompts import (
    create_provider_prompt,
    create_payor_prompt,
    WORKFLOW_LEVELS,
    create_treatment_decision_after_pa_denial_prompt,
)
from src.utils.oversight import apply_oversight_edit
from src.utils.json_parsing import extract_json_from_text

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


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
            it.get("payor_denial_reason")
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
        "missing_items": provider_request.get("missing_documentation", []),
        "provider_diagnosis_codes": [
            d.get("icd10") for d in provider_request.get("diagnosis_codes", [])
        ],
        "provider_clinical_notes": provider_request.get("clinical_notes", "")
    }


def run_unified_multi_level_review(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any],
    phase: str,  # "phase_2" or "phase_3"
    provider_prompt_fn: Callable,  # function to create provider request prompt
    payor_prompt_fn: Callable,  # function to create payor review prompt
    provider_prompt_kwargs: Dict[str, Any],  # additional kwargs for provider prompt
    payor_prompt_kwargs: Dict[str, Any],  # additional kwargs for payor prompt
    max_iterations: int = 3
) -> EncounterState:
    """
    unified 3-level review process for both pre-adjudication (Phase 2)
    and post-service (Phase 3) reviews.

    Only difference: prompts emphasize different operational contexts
    - Phase 2: record EVOLVING, can order tests, decision is AUTHORIZATION
    - Phase 3: record FIXED, can only clarify documentation, decision is PAYMENT

    Args:
        sim: simulation instance
        state: encounter state
        case: case data
        phase: "phase_2" or "phase_3"
        provider_prompt_fn: function(state, case, iteration, prior_iterations, stage, **kwargs) -> str
        payor_prompt_fn: function(state, provider_request, iteration, stage, level, **kwargs) -> str
        provider_prompt_kwargs: additional kwargs to pass to provider prompt function
        payor_prompt_kwargs: additional kwargs to pass to payor prompt function
        max_iterations: maximum number of review levels (default 3)

    Returns:
        Updated EncounterState with review results
    """

    prior_iterations = []
    treatment_approved = False
    approved_provider_request = None
    stage_map = {0: "initial_determination", 1: "internal_appeal", 2: "independent_review"}

    # verify policy views are loaded (critical for information asymmetry)
    if not state.provider_policy_view:
        print(f"[WARNING] {phase}: provider_policy_view is empty - LLM will guess clinical criteria")
    if not state.payor_policy_view:
        print(f"[WARNING] {phase}: payor_policy_view is empty - LLM will guess coverage criteria")

    for iteration_num in range(max_iterations):
        stage = stage_map.get(iteration_num, "unknown")

        provider_system_prompt = create_provider_prompt(sim.provider_params)
        provider_user_prompt = provider_prompt_fn(
            state, case, iteration_num, prior_iterations, stage=stage,
            **provider_prompt_kwargs
        )

        full_prompt = f"{provider_system_prompt}\n\n{provider_user_prompt}"
        messages = [HumanMessage(content=full_prompt)]

        # copilot generates draft
        draft_response = sim.provider_copilot.invoke(messages)
        draft_text = draft_response.content
        draft_cache_hit = draft_response.additional_kwargs.get('cache_hit', False) if hasattr(draft_response, 'additional_kwargs') else False

        # log copilot draft
        sim.audit_logger.log_interaction(
            phase=phase,
            agent="provider",
            action="copilot_draft",
            system_prompt=provider_system_prompt,
            user_prompt=provider_user_prompt,
            llm_response=draft_text,
            parsed_output={},
            metadata={
                "iteration": iteration_num,
                "stage": stage,
                "level": iteration_num,
                "copilot_model": sim.provider_copilot_name,
                "cache_hit": draft_cache_hit
            }
        )

        # apply oversight editing
        oversight_level = sim.provider_params.get('oversight_intensity', 'medium')
        evidence_packet = build_provider_evidence_packet(state, case, prior_iterations)
        provider_response_text, oversight_metadata = apply_oversight_edit(
            role="provider",
            oversight_level=oversight_level,
            draft_text=draft_text,
            evidence_packet=evidence_packet,
            llm=sim.provider_base_llm,
            rng_seed=sim.master_seed
        )

        # log oversight edit
        sim.audit_logger.log_interaction(
            phase=phase,
            agent="provider",
            action="oversight_edit",
            system_prompt="",
            user_prompt="",
            llm_response=provider_response_text,
            parsed_output=oversight_metadata,
            metadata={
                "iteration": iteration_num,
                "stage": stage,
                "level": iteration_num,
                "oversight_level": oversight_level
            }
        )

        # parse provider response
        try:
            provider_response_full = extract_json_from_text(provider_response_text)

            if not isinstance(provider_response_full, dict):
                raise ValueError("expected dict, got {}".format(type(provider_response_full)))

            # extract insurer request (what payor sees)
            provider_request = provider_response_full.get("insurer_request", {})

        except Exception as e:
            # log parse error to audit for debugging
            error_snippet = provider_response_text[:200] + "..." if len(provider_response_text) > 200 else provider_response_text
            sim.audit_logger.log_interaction(
                phase=phase,
                agent="provider",
                action="parse_error",
                system_prompt="",
                user_prompt="",
                llm_response=provider_response_text,
                parsed_output={"error": "json_parse_failed", "exception": str(e)},
                metadata={
                    "iteration": iteration_num,
                    "stage": stage,
                    "error_type": "provider_response_parse_error",
                    "raw_response_snippet": error_snippet
                }
            )
            raise ValueError(f"failed to parse provider response at iteration {iteration_num}: {e}\nResponse snippet: {error_snippet}")

        # extract request_type from nested structure if not at top level
        request_type = provider_request.get("request_type")
        if not request_type and "insurer_request" in provider_response_full:
            request_type = provider_response_full.get("insurer_request", {}).get("request_type")

        # log provider request
        sim.audit_logger.log_interaction(
            phase=phase,
            agent="provider",
            action=f"{request_type}_request",
            system_prompt=provider_system_prompt,
            user_prompt=provider_user_prompt,
            llm_response=provider_response_text,
            parsed_output=provider_request,
            metadata={
                "iteration": iteration_num,
                "stage": stage,
                "request_type": request_type,
                "cache_hit": draft_cache_hit
            }
        )

        # friction counting: provider action
        if state.friction_metrics:
            state.friction_metrics.provider_actions += 1
            # count probing tests: robust extraction
            svc = provider_request.get("requested_service", {}) or {}
            tests = svc.get("tests_requested")
            if isinstance(tests, list) and tests:
                state.friction_metrics.probing_tests_count += len(tests)
            elif request_type == "diagnostic_test":
                state.friction_metrics.probing_tests_count += 1
            # escalation depth tracks iteration
            state.friction_metrics.escalation_depth = max(
                state.friction_metrics.escalation_depth, iteration_num - 1
            )

        payor_system_prompt = create_payor_prompt(sim.payor_params)

        # call payor prompt function with kwargs
        payor_user_prompt = payor_prompt_fn(
            state, provider_request, iteration_num, stage=stage, level=iteration_num,
            **payor_prompt_kwargs
        )

        full_prompt = f"{payor_system_prompt}\n\n{payor_user_prompt}"
        messages = [HumanMessage(content=full_prompt)]

        # check if copilot is active at this level (Level 2 = independent review, no copilot)
        level_config = WORKFLOW_LEVELS.get(iteration_num, WORKFLOW_LEVELS[0])
        copilot_active = level_config.get("copilot_active", True)

        if copilot_active:
            # STEP 1: payor copilot generates draft decision
            payor_draft_response = sim.payor_copilot.invoke(messages)
            payor_draft_text = payor_draft_response.content
            payor_draft_cache_hit = payor_draft_response.additional_kwargs.get('cache_hit', False) if hasattr(payor_draft_response, 'additional_kwargs') else False

            # log payor copilot draft
            sim.audit_logger.log_interaction(
                phase=phase,
                agent="payor",
                action="copilot_draft",
                system_prompt=payor_system_prompt,
                user_prompt=payor_user_prompt,
                llm_response=payor_draft_text,
                parsed_output={},
                metadata={
                    "iteration": iteration_num,
                    "stage": stage,
                    "level": iteration_num,
                    "copilot_model": sim.payor_copilot_name,
                    "cache_hit": payor_draft_cache_hit
                }
            )

            # STEP 2: apply payor oversight editing
            payor_oversight_level = sim.payor_params.get('oversight_intensity', 'medium')
            payor_evidence_packet = build_payor_evidence_packet(state, provider_request)
            payor_response_text, payor_oversight_metadata = apply_oversight_edit(
                role="payor",
                oversight_level=payor_oversight_level,
                draft_text=payor_draft_text,
                evidence_packet=payor_evidence_packet,
                llm=sim.payor_base_llm,
                rng_seed=sim.master_seed
            )

            # log payor oversight edit
            sim.audit_logger.log_interaction(
                phase=phase,
                agent="payor",
                action="oversight_edit",
                system_prompt="",
                user_prompt="",
                llm_response=payor_response_text,
                parsed_output=payor_oversight_metadata,
                metadata={
                    "iteration": iteration_num,
                    "stage": stage,
                    "level": iteration_num,
                    "oversight_level": payor_oversight_level
                }
            )

            payor_cache_hit = payor_draft_cache_hit
        else:
            # Level 2 (independent review): no copilot, base LLM only
            payor_direct_response = sim.payor_base_llm.invoke(messages)
            payor_response_text = payor_direct_response.content
            payor_cache_hit = payor_direct_response.additional_kwargs.get('cache_hit', False) if hasattr(payor_direct_response, 'additional_kwargs') else False

            # log independent review (no copilot, no oversight edit)
            sim.audit_logger.log_interaction(
                phase=phase,
                agent="payor",
                action="independent_review",
                system_prompt=payor_system_prompt,
                user_prompt=payor_user_prompt,
                llm_response=payor_response_text,
                parsed_output={},
                metadata={
                    "iteration": iteration_num,
                    "stage": stage,
                    "level": iteration_num,
                    "copilot_active": False,
                    "reviewer_type": level_config.get("role_label", "Independent Review Entity (IRE)"),
                    "cache_hit": payor_cache_hit
                }
            )

        # parse payor decision
        try:
            payor_decision = extract_json_from_text(payor_response_text)
        except Exception as e:
            # log parse error to audit for debugging
            error_snippet = payor_response_text[:200] + "..." if len(payor_response_text) > 200 else payor_response_text
            sim.audit_logger.log_interaction(
                phase=phase,
                agent="payor",
                action="parse_error",
                system_prompt="",
                user_prompt="",
                llm_response=payor_response_text,
                parsed_output={"error": "json_parse_failed", "exception": str(e)},
                metadata={
                    "iteration": iteration_num,
                    "stage": stage,
                    "error_type": "payor_decision_parse_error",
                    "raw_response_snippet": error_snippet
                }
            )
            raise ValueError(f"failed to parse payor decision at iteration {iteration_num}: {e}\nResponse snippet: {error_snippet}")

        # level 2 enforcement: independent review must issue final decision (no endless pend)
        if iteration_num == 2:
            state.independent_review_reached = True
            status = (payor_decision.get("authorization_status") or "").lower()
            if status in {"pending_info", "pending", "pended", "request_info"}:
                payor_decision["authorization_status"] = "denied"
                payor_decision["denial_reason"] = (
                    payor_decision.get("denial_reason", "") +
                    " [COERCED: independent review cannot pend - insufficient objective documentation]"
                )
                payor_decision["level_2_coerced"] = True

        # enforce level-consistent reviewer types using WORKFLOW_LEVELS
        payor_decision["reviewer_type"] = level_config.get("role_label", "Unknown Reviewer")
        payor_decision["level"] = iteration_num

        # log payor decision
        sim.audit_logger.log_interaction(
            phase=phase,
            agent="payor",
            action=f"{request_type}_review",
            system_prompt=payor_system_prompt,
            user_prompt=payor_user_prompt,
            llm_response=payor_response_text,
            parsed_output=payor_decision,
            metadata={
                "iteration": iteration_num,
                "stage": stage,
                "level": iteration_num,
                "request_type": request_type,
                "copilot_active": copilot_active,
                "cache_hit": payor_cache_hit
            }
        )

        # friction counting: payor action
        if state.friction_metrics:
            state.friction_metrics.payor_actions += 1

        # track iteration for next round
        iteration_record = {
            "provider_request_type": request_type,
            "payor_decision": payor_decision["authorization_status"],
            "payor_denial_reason": payor_decision.get("denial_reason")
        }

        #important!
        state.current_level = iteration_num

        # handle decision outcomes
        if payor_decision["authorization_status"] == "approved":
            if request_type == "treatment":
                # treatment approved - DONE (provider can continue for more pre-approvals or treat)
                treatment_approved = True
                approved_provider_request = provider_request

                # extract service details from provider_request
                requested_service = provider_request.get("requested_service", {})
                service_name = requested_service.get("service_name", "")
                clinical_rationale = requested_service.get("clinical_justification",
                                                          requested_service.get("treatment_justification", ""))

                # extract diagnosis codes
                diagnosis_codes = []
                for diag in provider_request.get("diagnosis_codes", []):
                    if isinstance(diag, dict):
                        diagnosis_codes.append(diag.get("icd10", ""))
                    elif isinstance(diag, str):
                        diagnosis_codes.append(diag)

                # set decision on authorization_request (create if needed)
                if not state.authorization_request:
                    state.authorization_request = AuthorizationRequest(
                        request_type=request_type,
                        service_name=service_name,
                        clinical_rationale=clinical_rationale,
                        diagnosis_codes=diagnosis_codes
                    )
                else:
                    # update existing authorization_request
                    state.authorization_request.request_type = request_type
                    state.authorization_request.service_name = service_name
                    state.authorization_request.clinical_rationale = clinical_rationale
                    state.authorization_request.diagnosis_codes = diagnosis_codes

                # extract coding information (CPT, NDC, J-code)
                state.authorization_request.cpt_code = requested_service.get("procedure_code",
                                                                            requested_service.get("cpt_code"))
                state.authorization_request.ndc_code = requested_service.get("ndc_code")
                state.authorization_request.j_code = requested_service.get("j_code")

                # extract service details (dosage, frequency, etc.)
                state.authorization_request.dosage = requested_service.get("dosage")
                state.authorization_request.frequency = requested_service.get("frequency")
                state.authorization_request.duration = requested_service.get("duration")

                # set payor decision fields
                state.authorization_request.authorization_status = "approved"
                state.authorization_request.denial_reason = None
                state.authorization_request.missing_documentation = []
                approved_quantity = payor_decision.get("approved_quantity_amount")
                if approved_quantity is None:
                    approved_quantity = payor_decision.get("approved_quantity")
                state.authorization_request.approved_quantity_amount = approved_quantity
                state.authorization_request.reviewer_type = payor_decision.get("reviewer_type")
                state.authorization_request.review_level = payor_decision.get("level")
                break
            elif request_type == "diagnostic_test":
                # diagnostic test approved - continue to next iteration (get more pre-approvals)
                # generate test result (only in Phase 2)
                if phase == "phase_2_utilization_review":
                    test_name = provider_request.get("requested_service", {}).get("service_name")
                    if not test_name:
                        test_name = provider_request.get("request_details", {}).get("test_name")

                    if test_name:
                        test_result = sim._generate_test_result(test_name, case)
                        iteration_record["test_results"] = {test_name: test_result["value"]}
                    else:
                        iteration_record["test_results"] = {}
            elif phase == "phase_3_claims":
                state.claim_pended = False
                state.claim_rejected = False
                break

        elif payor_decision["authorization_status"] == "denied":
            # provider must decide: appeal to next level or abandon
            state.denial_occurred = True
            if phase == "phase_3_claims":
                state.claim_pended = False
                state.claim_rejected = True
                break
            # continue loop to next iteration (provider appeals) unless at Level 2
            if iteration_num >= 2:
                # at Level 2 (independent review): final decision, no appeal possible
                break

        elif payor_decision["authorization_status"] == "pending_info":
            # provider must decide: resubmit with more info or abandon
            # continue loop to iterate at same level - provider will try to address pend
            if phase == "phase_3_claims":
                state.claim_pended = True
            pass

        prior_iterations.append(iteration_record)

    # if treatment never approved, mark as denied (Phase 2 only)
    if phase == "phase_2_utilization_review" and not treatment_approved:
        # try to populate from last provider request if available
        last_request_type = "medication"
        last_service_name = ""
        last_clinical_rationale = ""
        last_diagnosis_codes = []

        if approved_provider_request:
            # use the last approved request (even if it was diagnostic test)
            last_request_type = approved_provider_request.get("request_type", "medication")
            requested_service = approved_provider_request.get("requested_service", {})
            last_service_name = requested_service.get("service_name", "")
            last_clinical_rationale = requested_service.get("clinical_justification",
                                                           requested_service.get("treatment_justification", ""))
            for diag in approved_provider_request.get("diagnosis_codes", []):
                if isinstance(diag, dict):
                    last_diagnosis_codes.append(diag.get("icd10", ""))
                elif isinstance(diag, str):
                    last_diagnosis_codes.append(diag)

        if not state.authorization_request:
            state.authorization_request = AuthorizationRequest(
                request_type=last_request_type,
                service_name=last_service_name,
                clinical_rationale=last_clinical_rationale,
                diagnosis_codes=last_diagnosis_codes
            )
        state.authorization_request.authorization_status = "denied"
        state.authorization_request.denial_reason = f"{phase}: max iterations reached without approval"
        state.authorization_request.reviewer_type = level_config.get("role_label", "Unknown Reviewer")
        state.authorization_request.review_level = iteration_num
        state.denial_occurred = True

        # CRITICAL: PA denied - provider decides whether to treat patient anyway
        # this captures the financial-legal tension: risk nonpayment vs medical abandonment
        if phase == "phase_2_utilization_review":
            treatment_decision = _provider_treatment_decision_after_pa_denial(sim, state, case)
            state.provider_treated_despite_denial = (treatment_decision == "treat_anyway")

            if treatment_decision == "no_treat":
                # provider chose not to treat - patient abandons care
                # Phase 3 will not run (no services rendered, no claim to submit)
                state.care_abandoned = True

    # collect all evidence for downstream use
    accumulated_test_results = {}
    for iteration in prior_iterations:
        if "test_results" in iteration:
            accumulated_test_results.update(iteration["test_results"])

    # store evidence on state (phase-specific attribute)
    evidence_attr = f"_{phase}_evidence"
    setattr(state, evidence_attr, {
        "approved_request": approved_provider_request,
        "test_results": accumulated_test_results,
        "iterations": prior_iterations
    })

    return state


def _provider_treatment_decision_after_pa_denial(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any]
) -> str:
    """
    After PA denial, provider decides whether to treat patient anyway.

    Returns: "treat_anyway" or "no_treat"

    This captures the financial-legal tension documented in utilization review literature:
    - Treat anyway = risk nonpayment (OOP/charity/hope for retro approval)
    - No treat = risk medical abandonment (legal liability)

    This is a conditional branch after ABANDON action, not a new action in action space.
    """
    import json
    from langchain_core.messages import HumanMessage
    denial_reason = state.authorization_request.denial_reason if state.authorization_request else "PA exhausted without approval"
    prompt = create_treatment_decision_after_pa_denial_prompt(
        state=state,
        denial_reason=denial_reason,
    )

    response = sim.provider.llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content.strip()

    # parse decision
    try:
        decision_data = extract_json_from_text(response_text)
        decision = decision_data.get("decision", "no_treat")
        rationale = decision_data.get("rationale", "")

        # log decision
        sim.audit_logger.log_provider_action(
            phase="phase_2_utilization_review",
            action_type="treatment_decision_after_pa_denial",
            description=f"provider decided to {decision} after PA exhausted",
            outcome={
                "decision": decision,
                "rationale": rationale,
                "pa_status": "denied",

            }
        )

        return decision if decision in ["treat_anyway", "no_treat"] else "no_treat"

    except Exception as e:
        # parsing failed - raise error to surface the bug
        sim.audit_logger.log_provider_action(
            phase="phase_2_utilization_review",
            action_type="treatment_decision_parse_error",
            description=f"failed to parse provider treatment decision: {str(e)}",
            outcome={"error": str(e), "raw_response": response_text}
        )
        raise ValueError(f"failed to parse provider treatment decision after PA denial: {e}\nResponse: {response_text}")
