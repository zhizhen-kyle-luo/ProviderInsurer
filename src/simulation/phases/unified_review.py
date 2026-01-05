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
    WORKFLOW_LEVELS
)
from src.utils.oversight import apply_oversight_edit

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
        "stage": state.provider_policy_view.get("policy_name", "") if state.provider_policy_view else ""
    }


def build_payor_evidence_packet(
    state: EncounterState,
    provider_request: Dict[str, Any]
) -> Dict[str, Any]:
    """build evidence packet for payor oversight editing"""
    policy_view = state.payor_policy_view or {}
    inpatient = policy_view.get("inpatient_criteria", {})

    return {
        "policy_criteria": inpatient.get("must_meet_one_of", []),
        "prerequisites": inpatient.get("prerequisites", []),
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

    # stage mapping for iteration semantics (0-indexed)
    stage_map = {0: "initial_determination", 1: "internal_appeal", 2: "independent_review"}

    # verify policy views are loaded (critical for information asymmetry)
    if not state.provider_policy_view:
        print(f"[WARNING] {phase}: provider_policy_view is empty - LLM will guess clinical criteria")
    if not state.payor_policy_view:
        print(f"[WARNING] {phase}: payor_policy_view is empty - LLM will guess coverage criteria")

    for iteration_num in range(max_iterations):
        stage = stage_map.get(iteration_num, "unknown")

        # ===== PROVIDER GENERATES REQUEST =====
        provider_system_prompt = create_provider_prompt(sim.provider_params)

        # call provider prompt function with kwargs
        provider_user_prompt = provider_prompt_fn(
            state, case, iteration_num, prior_iterations, stage=stage,
            **provider_prompt_kwargs
        )

        full_prompt = f"{provider_system_prompt}\n\n{provider_user_prompt}"
        messages = [HumanMessage(content=full_prompt)]

        # STEP 1: copilot generates draft
        draft_response = sim.provider_copilot.invoke(messages)
        draft_text = draft_response.content
        draft_cache_hit = draft_response.additional_kwargs.get('cache_hit', False) if hasattr(draft_response, 'additional_kwargs') else False

        # update current level tracking
        state.current_level = iteration_num

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

        # STEP 2: apply oversight editing
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
            clean_response = provider_response_text
            if "```json" in clean_response:
                clean_response = clean_response.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_response:
                clean_response = clean_response.split("```")[1].split("```")[0].strip()
            provider_response_full = json.loads(clean_response)

            if not isinstance(provider_response_full, dict):
                raise ValueError("expected dict, got {}".format(type(provider_response_full)))

            # extract insurer request (what payor sees)
            provider_request = provider_response_full.get("insurer_request", {})

        except Exception:
            provider_response_full = {
                "insurer_request": {
                    "request_type": "diagnostic_test",
                    "requested_service": {}
                }
            }
            provider_request = {
                "request_type": "diagnostic_test",
                "requested_service": {}
            }

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

        # ===== PAYOR REVIEWS REQUEST =====
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
            clean_response = payor_response_text
            if "```json" in clean_response:
                clean_response = clean_response.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_response:
                clean_response = clean_response.split("```")[1].split("```")[0].strip()
            payor_decision = json.loads(clean_response)
        except Exception:
            payor_decision = {
                "authorization_status": "denied",
                "denial_reason": "unable to parse response",
                "criteria_used": "unknown",
                "reviewer_type": "AI algorithm"
            }

        # level 2 enforcement: independent review must issue final decision (no endless pend)
        if iteration_num == 2:
            state.independent_review_reached = True
            if payor_decision.get("authorization_status") == "pending_info":
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

        # handle decision outcomes
        if payor_decision["authorization_status"] == "approved":
            if request_type == "treatment":
                # treatment approved - DONE
                treatment_approved = True
                approved_provider_request = provider_request
                # set decision on authorization_request (create if needed)
                if not state.authorization_request:
                    state.authorization_request = AuthorizationRequest(
                        request_type="medication",
                        service_name="",
                        clinical_rationale=""
                    )
                state.authorization_request.authorization_status = "approved"
                state.authorization_request.denial_reason = None
                state.authorization_request.missing_documentation = []
                state.authorization_request.approved_quantity = payor_decision.get("approved_quantity")
                state.authorization_request.reviewer_type = payor_decision.get("reviewer_type")
                state.authorization_request.review_level = payor_decision.get("level")
                break
            elif request_type == "diagnostic_test":
                # diagnostic test approved - generate test result (only in Phase 2)
                if phase == "phase_2_utilization_review":
                    test_name = provider_request.get("requested_service", {}).get("service_name")
                    if not test_name:
                        test_name = provider_request.get("request_details", {}).get("test_name")

                    if test_name:
                        test_result = sim._generate_test_result(test_name, case)
                        iteration_record["test_results"] = {test_name: test_result["value"]}
                    else:
                        iteration_record["test_results"] = {}

        elif payor_decision["authorization_status"] == "denied":
            state.denial_occurred = True

        prior_iterations.append(iteration_record)

    # if treatment never approved, mark as denied
    if not treatment_approved:
        if not state.authorization_request:
            state.authorization_request = AuthorizationRequest(
                request_type="medication",
                service_name="",
                clinical_rationale=""
            )
        state.authorization_request.authorization_status = "denied"
        state.authorization_request.denial_reason = f"{phase}: max iterations reached without approval"
        state.authorization_request.reviewer_type = level_config.get("role_label", "Unknown Reviewer")
        state.authorization_request.review_level = iteration_num
        state.denial_occurred = True

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
