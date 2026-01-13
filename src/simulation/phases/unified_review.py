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

from src.models import (
    EncounterState,
    AuthorizationRequest
)
from src.utils.prompts import (
    create_provider_prompt,
    create_payor_prompt,
    WORKFLOW_LEVELS,
    create_treatment_decision_after_phase2_denial_prompt,
    PROVIDER_ACTIONS_GUIDE,
    PROVIDER_RESPONSE_MATRIX,
    VALID_PROVIDER_ACTIONS,
    VALID_PAYOR_ACTIONS,
    VALID_REQUEST_TYPES,
    VALID_TREATMENT_DECISIONS,
)
from src.utils.oversight import apply_oversight_edit
from src.utils.json_parsing import extract_json_from_text

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def _get_provider_action_after_payor_decision(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    payor_decision: Dict[str, Any],
    request_type: str,
    phase: str,
    current_level: int
) -> str:
    """
    ask provider to choose action (CONTINUE/APPEAL/ABANDON) after payor decision.

    returns: "continue", "appeal", or "abandon"
    """
    if "action" not in payor_decision:
        raise ValueError("payor_decision missing required field 'action'")
    payor_action = payor_decision["action"]
    denial_reason = payor_decision.get("denial_reason", "")

    # build prompt explaining situation and asking for action
    prompt = f"""PROVIDER ACTION DECISION

You just received a payor decision. You must choose your next action.

PAYOR DECISION: {payor_action}
Request Type: {request_type}
Current Review Level: {current_level}
{f"Denial/Pend Reason: {denial_reason}" if denial_reason else ""}

{PROVIDER_RESPONSE_MATRIX}

{PROVIDER_ACTIONS_GUIDE}

IMPORTANT: Based on the payor decision and request type above, only certain actions are valid (see matrix).

TASK: Choose your action and explain your reasoning.

RESPONSE FORMAT (JSON):
{{
    "provider_action": "continue" or "appeal" or "abandon",
    "reasoning": "<brief explanation of why you chose this action>"
}}

Return ONLY valid JSON."""

    provider_system_prompt = create_provider_prompt(sim.provider_params)
    full_prompt = f"{provider_system_prompt}\n\n{prompt}"
    messages = [HumanMessage(content=full_prompt)]

    # use provider base LLM (this is a strategic decision, not a draft)
    response = sim.provider_base_llm.invoke(messages)
    response_text = response.content.strip()

    try:
        action_data = extract_json_from_text(response_text)

        # validate provider_action field exists
        if "provider_action" not in action_data:
            raise ValueError(
                f"provider action response missing required field 'provider_action'. "
                f"must be one of: {VALID_PROVIDER_ACTIONS}"
            )

        provider_action = action_data["provider_action"]
        reasoning = action_data.get("reasoning", "")

        # validate action is in allowed set
        if provider_action not in VALID_PROVIDER_ACTIONS:
            raise ValueError(
                f"invalid provider_action '{provider_action}'. "
                f"must be one of: {VALID_PROVIDER_ACTIONS}"
            )

        # log the action decision
        sim.audit_logger.log_interaction(
            phase=phase,
            agent="provider",
            action="action_decision",
            system_prompt=provider_system_prompt,
            user_prompt=prompt,
            llm_response=response_text,
            parsed_output={"provider_action": provider_action, "reasoning": reasoning},
            metadata={
                "payor_decision": payor_action,
                "request_type": request_type,
                "current_level": current_level
            }
        )

        return provider_action

    except ValueError as e:
        # validation error - re-raise (no defaults)
        raise
    except Exception as e:
        # JSON parsing failed - raise error to surface the bug
        raise ValueError(
            f"failed to parse provider action decision: {e}\n"
            f"Response: {response_text}"
        )


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
    provider_abandoned_after_denial = False
    approved_provider_request = None
    stage_map = {0: "initial_determination", 1: "internal_appeal", 2: "independent_review"}

    # separate level (authority: 0/1/2) from turn count
    current_level = 0
    turn_count = 0
    max_turns_per_simulation = max_iterations * 3  # safety limit to prevent infinite loops

    # track pend count per level to enforce MAX_REQUEST_INFO_PER_LEVEL
    pend_count_at_level = {0: 0, 1: 0, 2: 0}

    # verify policy views are loaded (critical for information asymmetry)
    if not state.provider_policy_view:
        print(f"[WARNING] {phase}: provider_policy_view is empty - LLM will guess clinical criteria")
    if not state.payor_policy_view:
        print(f"[WARNING] {phase}: payor_policy_view is empty - LLM will guess coverage criteria")

    while turn_count < max_turns_per_simulation:
        turn_count += 1
        stage = stage_map.get(current_level, "unknown")

        print(f"\n[{phase}] Turn {turn_count}, Level {current_level} ({stage})")

        provider_system_prompt = create_provider_prompt(sim.provider_params)
        # pass turn_count-1 as iteration for display (0-indexed)
        provider_user_prompt = provider_prompt_fn(
            state, case, turn_count - 1, prior_iterations, level=current_level,
            **provider_prompt_kwargs
        )

        full_prompt = f"{provider_system_prompt}\n\n{provider_user_prompt}"
        messages = [HumanMessage(content=full_prompt)]

        # copilot generates draft
        print(f"  provider copilot drafting request...")
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
                "iteration": current_level,
                "stage": stage,
                "level": current_level,
                "copilot_model": sim.provider_copilot_name,
                "cache_hit": draft_cache_hit
            }
        )

        # apply oversight editing
        print(f"  provider oversight editing (level={sim.provider_params.get('oversight_intensity', 'medium')})...")
        oversight_level = sim.provider_params.get('oversight_intensity', 'medium')
        evidence_packet = build_provider_evidence_packet(state, case, prior_iterations)
        provider_response_text, oversight_metadata, oversight_prompt, oversight_llm_response = apply_oversight_edit(
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
            user_prompt=oversight_prompt,
            llm_response=oversight_llm_response,
            parsed_output=oversight_metadata,
            metadata={
                "iteration": current_level,
                "stage": stage,
                "level": current_level,
                "oversight_level": oversight_level,
                "evidence_packet": evidence_packet
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
                    "iteration": current_level,
                    "stage": stage,
                    "error_type": "provider_response_parse_error",
                    "raw_response_snippet": error_snippet
                }
            )
            raise ValueError(f"failed to parse provider response at iteration {current_level}: {e}\nResponse snippet: {error_snippet}")

        # extract request_type from nested structure if not at top level
        request_type = provider_request.get("request_type")
        if not request_type and "insurer_request" in provider_response_full:
            request_type = provider_response_full.get("insurer_request", {}).get("request_type")

        # validate request_type is present and valid
        if not request_type:
            raise ValueError(
                f"provider response missing required field 'request_type' at turn {turn_count}. "
                f"must be one of: {VALID_REQUEST_TYPES}"
            )
        if request_type not in VALID_REQUEST_TYPES:
            raise ValueError(
                f"invalid request_type '{request_type}' at turn {turn_count}. "
                f"must be one of: {VALID_REQUEST_TYPES}"
            )

        print(f"  provider submitted {request_type} request")

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
                "iteration": current_level,
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
                state.friction_metrics.escalation_depth, current_level - 1
            )

        payor_system_prompt = create_payor_prompt(sim.payor_params)

        # call payor prompt function with kwargs
        # pass turn_count-1 as iteration for display (0-indexed)
        # pass pend_count_at_level for enforcing MAX_REQUEST_INFO_PER_LEVEL
        payor_user_prompt = payor_prompt_fn(
            state, provider_request, turn_count - 1, level=current_level,
            pend_count_at_level=pend_count_at_level[current_level],
            **payor_prompt_kwargs
        )

        full_prompt = f"{payor_system_prompt}\n\n{payor_user_prompt}"
        messages = [HumanMessage(content=full_prompt)]

        # check if copilot is active at this level (Level 2 = independent review, no copilot)
        level_config = WORKFLOW_LEVELS.get(current_level, WORKFLOW_LEVELS[0])
        copilot_active = level_config.get("copilot_active", True)

        if copilot_active:
            # STEP 1: payor copilot generates draft decision
            print(f"  payor copilot reviewing...")
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
                    "iteration": current_level,
                    "stage": stage,
                    "level": current_level,
                    "copilot_model": sim.payor_copilot_name,
                    "cache_hit": payor_draft_cache_hit
                }
            )

            # STEP 2: apply payor oversight editing
            payor_oversight_level = sim.payor_params.get('oversight_intensity', 'medium')
            payor_evidence_packet = build_payor_evidence_packet(state, provider_request)
            payor_response_text, payor_oversight_metadata, payor_oversight_prompt, payor_oversight_llm_response = apply_oversight_edit(
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
                user_prompt=payor_oversight_prompt,
                llm_response=payor_oversight_llm_response,
                parsed_output=payor_oversight_metadata,
                metadata={
                    "iteration": current_level,
                    "stage": stage,
                    "level": current_level,
                    "oversight_level": payor_oversight_level,
                    "evidence_packet": payor_evidence_packet
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
                    "iteration": current_level,
                    "stage": stage,
                    "level": current_level,
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
                    "iteration": current_level,
                    "stage": stage,
                    "error_type": "payor_decision_parse_error",
                    "raw_response_snippet": error_snippet
                }
            )
            raise ValueError(f"failed to parse payor decision at iteration {current_level}: {e}\nResponse snippet: {error_snippet}")

        # level 2 enforcement: independent review must issue final decision (no endless pend)
        if current_level == 2:
            state.independent_review_reached = True
            action = payor_decision.get("action", "")
            if action == "pending_info":
                payor_decision["action"] = "denied"
                payor_decision["denial_reason"] = (
                    payor_decision.get("denial_reason", "") +
                    " [COERCED: independent review cannot pend - insufficient objective documentation]"
                )
                payor_decision["level_2_coerced"] = True

        # enforce level-consistent reviewer types using WORKFLOW_LEVELS
        payor_decision["reviewer_type"] = level_config.get("role_label", "Unknown Reviewer")
        payor_decision["level"] = current_level

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
                "iteration": current_level,
                "stage": stage,
                "level": current_level,
                "request_type": request_type,
                "copilot_active": copilot_active,
                "cache_hit": payor_cache_hit
            }
        )

        # friction counting: payor action
        if state.friction_metrics:
            state.friction_metrics.payor_actions += 1

        # validate action is present and valid
        if "action" not in payor_decision:
            raise ValueError(
                f"payor response missing required field 'action' at turn {turn_count}. "
                f"must be one of: {VALID_PAYOR_ACTIONS}"
            )

        payor_action = payor_decision["action"]
        if payor_action not in VALID_PAYOR_ACTIONS:
            raise ValueError(
                f"invalid action '{payor_action}' at turn {turn_count}. "
                f"must be one of: {VALID_PAYOR_ACTIONS}"
            )

        # track iteration for next round
        iteration_record = {
            "provider_request_type": request_type,
            "payor_decision": payor_action,
            "payor_denial_reason": payor_decision.get("denial_reason")
        }

        #important!
        state.current_level = current_level

        # handle decision outcomes based on PROVIDER_RESPONSE_MATRIX
        print(f"  payor decision: {payor_action}")

        # TERMINAL SUCCESS: APPROVE of TREATMENT or LEVEL_OF_CARE
        if payor_action == "approved" and request_type in ["treatment", "level_of_care"]:
            treatment_approved = True
            approved_provider_request = provider_request

            # extract service details from provider_request
            requested_service = provider_request.get("requested_service", {})
            service_name = requested_service.get("service_name", "")
            clinical_rationale = requested_service.get(
                "clinical_evidence",
                requested_service.get("severity_indicators", "")
            )

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

            prior_iterations.append(iteration_record)
            break  # TERMINAL - simulation ends

        # NON-TERMINAL: APPROVE of DIAGNOSTIC - provider must CONTINUE with result
        elif payor_action == "approved" and request_type == "diagnostic_test":
            # diagnostic test approved - generate result and provider will CONTINUE
            if phase == "phase_2_utilization_review":
                test_name = provider_request.get("requested_service", {}).get("service_name")
                if not test_name:
                    test_name = provider_request.get("request_details", {}).get("test_name")

                if test_name:
                    test_result = sim._generate_test_result(test_name, case)
                    iteration_record["test_results"] = {test_name: test_result["value"]}
                else:
                    iteration_record["test_results"] = {}

            # provider will automatically CONTINUE at same level (not an action choice)
            prior_iterations.append(iteration_record)
            continue  # stay at same level, provider submits next request

        # APPROVE in Phase 3 claims (payment approved)
        elif payor_action == "approved" and phase == "phase_3_claims":
            state.claim_pended = False
            state.claim_rejected = False
            prior_iterations.append(iteration_record)
            break  # claim approved, done

        # DOWNGRADE: grey zone - provider must choose APPEAL or ABANDON
        elif payor_action == "downgrade":
            state.denial_occurred = False  # not a full denial

            # ask provider: APPEAL (fight for higher level) or ABANDON (accept downgrade)?
            if current_level >= 2:
                # at Level 2 (IRE): final decision, cannot appeal further
                prior_iterations.append(iteration_record)
                break

            provider_action = _get_provider_action_after_payor_decision(
                sim=sim,
                state=state,
                payor_decision=payor_decision,
                request_type=request_type,
                phase=phase,
                current_level=current_level
            )

            if provider_action == "appeal":
                current_level += 1  # escalate to next authority
                prior_iterations.append(iteration_record)
                continue  # next iteration at higher level
            else:  # abandon
                # accept downgrade, exit simulation
                prior_iterations.append(iteration_record)
                break

        # DENY: provider must choose APPEAL or ABANDON
        elif payor_action == "denied":
            state.denial_occurred = True
            if phase == "phase_3_claims":
                state.claim_pended = False
                state.claim_rejected = True

            # at Level 2 (IRE): final decision, cannot appeal
            if current_level >= 2:
                prior_iterations.append(iteration_record)
                break

            provider_action = _get_provider_action_after_payor_decision(
                sim=sim,
                state=state,
                payor_decision=payor_decision,
                request_type=request_type,
                phase=phase,
                current_level=current_level
            )

            if provider_action == "appeal":
                current_level += 1  # escalate to next authority
                prior_iterations.append(iteration_record)
                continue  # next iteration at higher level
            else:  # abandon
                if phase == "phase_2_utilization_review":
                    provider_abandoned_after_denial = True
                prior_iterations.append(iteration_record)
                break

        # REQUEST_INFO (pend): provider should CONTINUE or ABANDON (cannot APPEAL a pend)
        elif payor_action == "pending_info":
            if phase == "phase_3_claims":
                state.claim_pended = True

            # increment pend count for current level (for next iteration's prompt)
            pend_count_at_level[current_level] += 1

            # provider decides to continue or abandon
            provider_action = _get_provider_action_after_payor_decision(
                sim=sim,
                state=state,
                payor_decision=payor_decision,
                request_type=request_type,
                phase=phase,
                current_level=current_level
            )

            if provider_action == "continue":
                # stay at same level, provider will address pend
                prior_iterations.append(iteration_record)
                continue
            else:  # abandon
                prior_iterations.append(iteration_record)
                break

        else:
            # unknown status - treat as denial and break
            prior_iterations.append(iteration_record)
            break

    # if treatment never approved, determine final authorization status (Phase 2 only)
    if phase == "phase_2_utilization_review" and not treatment_approved:
        # determine what the final status should be based on last payor decision
        if not prior_iterations:
            raise ValueError(f"{phase}: treatment not approved but no prior iterations recorded")

        last_iteration = prior_iterations[-1]
        if "payor_decision" not in last_iteration:
            raise ValueError(f"{phase}: last iteration missing payor_decision")
        last_payor_action = last_iteration["payor_decision"]

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
            last_clinical_rationale = requested_service.get(
                "clinical_evidence",
                requested_service.get("severity_indicators", "")
            )
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

        # set authorization status based on last payor decision
        state.authorization_request.authorization_status = last_payor_action
        if last_payor_action == "denied":
            state.authorization_request.denial_reason = f"{phase}: max iterations reached without approval"
            state.denial_occurred = True
        elif last_payor_action == "pending_info":
            state.authorization_request.denial_reason = f"{phase}: provider abandoned after pend"
            state.denial_occurred = False
        else:
            # downgrade or other terminal status
            state.authorization_request.denial_reason = f"{phase}: provider abandoned after {last_payor_action}"
            state.denial_occurred = (last_payor_action == "denied")

        state.authorization_request.reviewer_type = level_config.get("role_label", "Unknown Reviewer")
        state.authorization_request.review_level = current_level

        # CRITICAL: Phase 2 denied and provider abandoned - decide whether to treat patient anyway
        # this captures the financial-legal tension: risk nonpayment vs medical abandonment
        if last_payor_action == "denied" and provider_abandoned_after_denial:
            treatment_decision = _provider_treatment_decision_after_phase2_denial(sim, state, case)
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


def _provider_treatment_decision_after_phase2_denial(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any]
) -> str:
    """
    After Phase 2 denial, provider decides whether to treat patient anyway.

    Returns: "treat_anyway" or "no_treat"

    This captures the financial-legal tension documented in utilization review literature:
    - Treat anyway = risk nonpayment (OOP/charity/hope for retro approval)
    - No treat = risk medical abandonment (legal liability)

    This is a conditional branch after ABANDON action, not a new action in action space.
    """
    import json
    from langchain_core.messages import HumanMessage
    denial_reason = state.authorization_request.denial_reason if state.authorization_request else "Phase 2 exhausted without approval"
    prompt = create_treatment_decision_after_phase2_denial_prompt(
        state=state,
        denial_reason=denial_reason,
    )

    response = sim.provider.llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content.strip()

    # parse decision
    try:
        decision_data = extract_json_from_text(response_text)

        # validate decision field exists
        if "decision" not in decision_data:
            raise ValueError(
                f"treatment decision response missing required field 'decision'. "
                f"must be one of: {VALID_TREATMENT_DECISIONS}"
            )

        decision = decision_data["decision"]

        # validate decision is valid
        if decision not in VALID_TREATMENT_DECISIONS:
            raise ValueError(
                f"invalid treatment decision '{decision}'. "
                f"must be one of: {VALID_TREATMENT_DECISIONS}"
            )

        return decision

    except ValueError as e:
        # validation error - re-raise (no defaults)
        raise
    except Exception as e:
        # JSON parsing failed - raise error to surface the bug
        raise ValueError(f"failed to parse provider treatment decision after Phase 2 denial: {e}\nResponse: {response_text}")
