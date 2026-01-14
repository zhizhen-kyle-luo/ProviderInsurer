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

from typing import Dict, Any, List, Callable, TYPE_CHECKING
from langchain_core.messages import HumanMessage

from src.models import EncounterState
from src.utils.prompts import (
    create_provider_prompt,
    create_payor_prompt,
    WORKFLOW_LEVELS,
    VALID_PROVIDER_ACTIONS,
    VALID_PAYOR_ACTIONS,
    VALID_REQUEST_TYPES,
)
from src.utils.oversight import apply_oversight_edit
from src.utils.json_parsing import extract_json_from_text

from .evidence_builders import build_provider_evidence_packet, build_payor_evidence_packet
from .service_line_builder import finalize_service_line_after_non_approval
from .provider_actions import provider_treatment_decision_after_phase2_denial
from .decision_handlers import (
    handle_approval,
    handle_modification,
    handle_denial,
    handle_pend
)

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def run_unified_multi_level_review(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any],
    phase: str,  # "phase_2_utilization_review" or "phase_3_claims"
    provider_prompt_fn: Callable,
    payor_prompt_fn: Callable,
    provider_prompt_kwargs: Dict[str, Any],
    payor_prompt_kwargs: Dict[str, Any],
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
        phase: "phase_2_utilization_review" or "phase_3_claims"
        provider_prompt_fn: function(state, case, iteration, prior_iterations, level, **kwargs) -> str
        payor_prompt_fn: function(state, provider_request, iteration, level, pend_count_at_level, **kwargs) -> str
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
    max_turns_per_simulation = max_iterations * 3  # safety limit

    # track pend count per level
    pend_count_at_level = {0: 0, 1: 0, 2: 0}

    # verify policy views are loaded
    if not state.provider_policy_view:
        print(f"[WARNING] {phase}: provider_policy_view is empty - LLM will guess clinical criteria")
    if not state.payor_policy_view:
        print(f"[WARNING] {phase}: payor_policy_view is empty - LLM will guess coverage criteria")

    while turn_count < max_turns_per_simulation:
        turn_count += 1
        if current_level not in stage_map:
            raise ValueError(f"invalid review level: {current_level}")
        stage = stage_map[current_level]
        print(f"\n[{phase}] Turn {turn_count}, Level {current_level} ({stage})")

        # === PROVIDER REQUEST ===
        provider_request, request_type, draft_cache_hit = _get_provider_request(
            sim, state, case, phase, current_level, prior_iterations,
            provider_prompt_fn, provider_prompt_kwargs, stage
        )

        # update state tracking
        state.current_level = current_level

        # === PAYOR REVIEW ===
        payor_decision, payor_cache_hit = _get_payor_decision(
            sim, state, provider_request, phase, current_level, pend_count_at_level,
            payor_prompt_fn, payor_prompt_kwargs, stage, request_type
        )

        # validate and log
        payor_action = _validate_and_log_payor_decision(
            sim, payor_decision, state, provider_request, phase, current_level,
            stage, request_type, payor_cache_hit
        )

        # friction counting
        if state.friction_metrics:
            state.friction_metrics.provider_actions += 1
            state.friction_metrics.payor_actions += 1
            # count probing tests from all requested services
            requested_services = provider_request.get("requested_services", [])
            for svc in requested_services:
                if svc.get("request_type") == "diagnostic_test":
                    state.friction_metrics.probing_tests_count += 1
            state.friction_metrics.escalation_depth = max(
                state.friction_metrics.escalation_depth, current_level
            )

        # create iteration record
        iteration_record = {
            "provider_request_type": request_type,
            "payor_decision": payor_action,
            "payor_decision_reason": payor_decision.get("decision_reason")
        }

        # === HANDLE DECISION OUTCOME ===
        outcome = _handle_payor_decision_outcome(
            sim, state, case, provider_request, payor_decision, payor_action,
            request_type, phase, current_level, iteration_record,
            prior_iterations, pend_count_at_level
        )

        if outcome["terminal"]:
            treatment_approved = outcome["treatment_approved"]
            approved_provider_request = outcome["approved_request"]
            provider_abandoned_after_denial = outcome["provider_abandoned"]
            break

        if outcome["escalate"]:
            current_level += 1
            continue

        # continue at same level (diagnostic test approved or pend addressed)
        continue

    # === FINALIZATION ===
    _finalize_review(
        sim, state, case, phase, treatment_approved, provider_abandoned_after_denial,
        approved_provider_request, prior_iterations, current_level, stage_map
    )

    return state


def _get_provider_request(
    sim, state, case, phase, current_level, prior_iterations,
    provider_prompt_fn, provider_prompt_kwargs, stage
):
    """get provider request with copilot + oversight"""
    provider_system_prompt = create_provider_prompt(sim.provider_params)
    provider_user_prompt = provider_prompt_fn(
        state, case, current_level, prior_iterations, level=current_level,
        **provider_prompt_kwargs
    )

    full_prompt = f"{provider_system_prompt}\n\n{provider_user_prompt}"
    messages = [HumanMessage(content=full_prompt)]

    # copilot draft
    print(f"  provider copilot drafting request...")
    draft_response = sim.provider_copilot.invoke(messages)
    draft_text = draft_response.content
    draft_cache_hit = draft_response.additional_kwargs.get('cache_hit', False) if hasattr(draft_response, 'additional_kwargs') else False

    # log copilot draft
    sim.audit_logger.log_interaction(
        phase=phase, agent="provider", action="copilot_draft",
        system_prompt=provider_system_prompt, user_prompt=provider_user_prompt,
        llm_response=draft_text, parsed_output={},
        metadata={"iteration": current_level, "stage": stage, "level": current_level,
                  "copilot_model": sim.provider_copilot_name, "cache_hit": draft_cache_hit}
    )

    # oversight editing
    print(f"  provider oversight editing (level={sim.provider_params.get('oversight_intensity', 'medium')})...")
    oversight_level = sim.provider_params.get('oversight_intensity', 'medium')
    evidence_packet = build_provider_evidence_packet(state, case, prior_iterations)
    provider_response_text, oversight_metadata, oversight_prompt, oversight_llm_response = apply_oversight_edit(
        role="provider", oversight_level=oversight_level, draft_text=draft_text,
        evidence_packet=evidence_packet, llm=sim.provider_base_llm, rng_seed=sim.master_seed
    )

    # log oversight
    sim.audit_logger.log_interaction(
        phase=phase, agent="provider", action="oversight_edit",
        system_prompt="", user_prompt=oversight_prompt,
        llm_response=oversight_llm_response, parsed_output=oversight_metadata,
        metadata={"iteration": current_level, "stage": stage, "level": current_level,
                  "oversight_level": oversight_level, "evidence_packet": evidence_packet}
    )

    # parse response
    try:
        provider_response_full = extract_json_from_text(provider_response_text)
        if not isinstance(provider_response_full, dict):
            raise ValueError("expected dict, got {}".format(type(provider_response_full)))

        provider_request = provider_response_full.get("insurer_request", {})

        # extract request_type from requested_services array
        requested_services = provider_request.get("requested_services", [])
        if not requested_services or not isinstance(requested_services, list):
            raise ValueError("provider_request missing required field 'requested_services'")
        request_type = requested_services[0].get("request_type")
        for svc in requested_services:
            svc_type = svc.get("request_type")
            if not svc_type:
                raise ValueError("requested_services entry missing required field 'request_type'")
            if svc_type not in VALID_REQUEST_TYPES:
                raise ValueError(
                    f"invalid request_type '{svc_type}'. must be one of: {VALID_REQUEST_TYPES}"
                )

        if not request_type:
            raise ValueError(
                f"provider response missing required field 'request_type'. "
                f"must be one of: {VALID_REQUEST_TYPES}"
            )
        if request_type not in VALID_REQUEST_TYPES:
            raise ValueError(
                f"invalid request_type '{request_type}'. must be one of: {VALID_REQUEST_TYPES}"
            )

        print(f"  provider submitted {request_type} request")

        # log provider request
        sim.audit_logger.log_interaction(
            phase=phase, agent="provider", action=f"{request_type}_request",
            system_prompt=provider_system_prompt, user_prompt=provider_user_prompt,
            llm_response=provider_response_text, parsed_output=provider_request,
            metadata={"iteration": current_level, "stage": stage, "request_type": request_type,
                      "cache_hit": draft_cache_hit}
        )

        return provider_request, request_type, draft_cache_hit

    except Exception as e:
        error_snippet = provider_response_text[:200] + "..." if len(provider_response_text) > 200 else provider_response_text
        sim.audit_logger.log_interaction(
            phase=phase, agent="provider", action="parse_error",
            system_prompt="", user_prompt="", llm_response=provider_response_text,
            parsed_output={"error": "json_parse_failed", "exception": str(e)},
            metadata={"iteration": current_level, "stage": stage,
                      "error_type": "provider_response_parse_error",
                      "raw_response_snippet": error_snippet}
        )
        raise ValueError(f"failed to parse provider response at iteration {current_level}: {e}\nResponse snippet: {error_snippet}")


def _get_payor_decision(
    sim, state, provider_request, phase, current_level, pend_count_at_level,
    payor_prompt_fn, payor_prompt_kwargs, stage, request_type
):
    """get payor decision with copilot + oversight (or direct for L2)"""
    if current_level not in WORKFLOW_LEVELS:
        raise ValueError(f"invalid review level: {current_level}")
    level_config = WORKFLOW_LEVELS[current_level]
    copilot_active = level_config.get("copilot_active", True)

    payor_system_prompt = create_payor_prompt(sim.payor_params)
    payor_user_prompt = payor_prompt_fn(
        state, provider_request, current_level, level=current_level,
        pend_count_at_level=pend_count_at_level[current_level],
        **payor_prompt_kwargs
    )

    full_prompt = f"{payor_system_prompt}\n\n{payor_user_prompt}"
    messages = [HumanMessage(content=full_prompt)]

    if copilot_active:
        # copilot + oversight
        print(f"  payor copilot reviewing...")
        payor_draft_response = sim.payor_copilot.invoke(messages)
        payor_draft_text = payor_draft_response.content
        payor_cache_hit = payor_draft_response.additional_kwargs.get('cache_hit', False) if hasattr(payor_draft_response, 'additional_kwargs') else False

        sim.audit_logger.log_interaction(
            phase=phase, agent="payor", action="copilot_draft",
            system_prompt=payor_system_prompt, user_prompt=payor_user_prompt,
            llm_response=payor_draft_text, parsed_output={},
            metadata={"iteration": current_level, "stage": stage, "level": current_level,
                      "copilot_model": sim.payor_copilot_name, "cache_hit": payor_cache_hit}
        )

        payor_oversight_level = sim.payor_params.get('oversight_intensity', 'medium')
        payor_evidence_packet = build_payor_evidence_packet(state, provider_request)
        payor_response_text, payor_oversight_metadata, payor_oversight_prompt, payor_oversight_llm_response = apply_oversight_edit(
            role="payor", oversight_level=payor_oversight_level, draft_text=payor_draft_text,
            evidence_packet=payor_evidence_packet, llm=sim.payor_base_llm, rng_seed=sim.master_seed
        )

        sim.audit_logger.log_interaction(
            phase=phase, agent="payor", action="oversight_edit",
            system_prompt="", user_prompt=payor_oversight_prompt,
            llm_response=payor_oversight_llm_response, parsed_output=payor_oversight_metadata,
            metadata={"iteration": current_level, "stage": stage, "level": current_level,
                      "oversight_level": payor_oversight_level, "evidence_packet": payor_evidence_packet}
        )
    else:
        # Level 2: independent review, no copilot
        payor_direct_response = sim.payor_base_llm.invoke(messages)
        payor_response_text = payor_direct_response.content
        payor_cache_hit = payor_direct_response.additional_kwargs.get('cache_hit', False) if hasattr(payor_direct_response, 'additional_kwargs') else False

        sim.audit_logger.log_interaction(
            phase=phase, agent="payor", action="independent_review",
            system_prompt=payor_system_prompt, user_prompt=payor_user_prompt,
            llm_response=payor_response_text, parsed_output={},
            metadata={"iteration": current_level, "stage": stage, "level": current_level,
                      "copilot_active": False,
                      "reviewer_type": level_config.get("role_label", "Independent Review Entity (IRE)"),
                      "cache_hit": payor_cache_hit}
        )

    # parse decision
    try:
        payor_decision = extract_json_from_text(payor_response_text)
        return payor_decision, payor_cache_hit
    except Exception as e:
        error_snippet = payor_response_text[:200] + "..." if len(payor_response_text) > 200 else payor_response_text
        sim.audit_logger.log_interaction(
            phase=phase, agent="payor", action="parse_error",
            system_prompt="", user_prompt="", llm_response=payor_response_text,
            parsed_output={"error": "json_parse_failed", "exception": str(e)},
            metadata={"iteration": current_level, "stage": stage,
                      "error_type": "payor_decision_parse_error",
                      "raw_response_snippet": error_snippet}
        )
        raise ValueError(f"failed to parse payor decision at iteration {current_level}: {e}\nResponse snippet: {error_snippet}")


def _validate_and_log_payor_decision(
    sim, payor_decision, state, provider_request, phase, current_level,
    stage, request_type, payor_cache_hit
):
    """validate payor decision and handle L2 enforcement"""
    if current_level not in WORKFLOW_LEVELS:
        raise ValueError(f"invalid review level: {current_level}")
    level_config = WORKFLOW_LEVELS[current_level]

    # L2 enforcement: no pend allowed
    if current_level == 2:
        state.independent_review_reached = True
        action = payor_decision.get("action", "")
        if action == "pending_info":
            payor_decision["action"] = "denied"
            payor_decision["decision_reason"] = (
                payor_decision.get("decision_reason", "") +
                " [COERCED: independent review cannot pend - insufficient objective documentation]"
            )
            payor_decision["level_2_coerced"] = True

    # enforce reviewer type
    payor_decision["reviewer_type"] = level_config.get("role_label", "Unknown Reviewer")
    payor_decision["level"] = current_level

    # validate action
    if "action" not in payor_decision:
        raise ValueError(
            f"payor response missing required field 'action'. must be one of: {VALID_PAYOR_ACTIONS}"
        )

    payor_action = payor_decision["action"]
    if payor_action not in VALID_PAYOR_ACTIONS:
        raise ValueError(
            f"invalid action '{payor_action}'. must be one of: {VALID_PAYOR_ACTIONS}"
        )

    print(f"  payor decision: {payor_action}")

    # log decision
    copilot_active = level_config.get("copilot_active", True)
    sim.audit_logger.log_interaction(
        phase=phase, agent="payor", action=f"{request_type}_review",
        system_prompt="", user_prompt="",  # already logged in _get_payor_decision
        llm_response="", parsed_output=payor_decision,
        metadata={"iteration": current_level, "stage": stage, "level": current_level,
                  "request_type": request_type, "copilot_active": copilot_active,
                  "cache_hit": payor_cache_hit}
    )

    return payor_action


def _handle_payor_decision_outcome(
    sim, state, case, provider_request, payor_decision, payor_action,
    request_type, phase, current_level, iteration_record,
    prior_iterations, pend_count_at_level
):
    """route to appropriate decision handler"""
    if payor_action == "approved":
        outcome, approved_request = handle_approval(
            sim, state, provider_request, payor_decision, request_type, phase,
            iteration_record, prior_iterations, case
        )
        return {
            "terminal": outcome.is_terminal,
            "escalate": outcome.should_escalate,
            "treatment_approved": outcome.is_terminal and request_type in ["treatment", "level_of_care"],
            "approved_request": approved_request,
            "provider_abandoned": False
        }

    elif payor_action == "modified":
        outcome = handle_modification(
            sim, state, provider_request, payor_decision, request_type, phase, current_level,
            iteration_record, prior_iterations
        )
        return {
            "terminal": outcome.is_terminal,
            "escalate": outcome.should_escalate,
            "treatment_approved": False,
            "approved_request": None,
            "provider_abandoned": False
        }

    elif payor_action == "denied":
        outcome, provider_abandoned = handle_denial(
            sim, state, provider_request, payor_decision, request_type, phase, current_level,
            iteration_record, prior_iterations
        )
        return {
            "terminal": outcome.is_terminal,
            "escalate": outcome.should_escalate,
            "treatment_approved": False,
            "approved_request": None,
            "provider_abandoned": provider_abandoned
        }

    elif payor_action == "pending_info":
        outcome = handle_pend(
            sim, state, provider_request, payor_decision, request_type, phase, current_level,
            iteration_record, prior_iterations, pend_count_at_level
        )
        return {
            "terminal": outcome.is_terminal,
            "escalate": outcome.should_escalate,
            "treatment_approved": False,
            "approved_request": None,
            "provider_abandoned": False
        }

    else:
        # unknown action - treat as terminal
        prior_iterations.append(iteration_record)
        return {
            "terminal": True,
            "escalate": False,
            "treatment_approved": False,
            "approved_request": None,
            "provider_abandoned": False
        }


def _finalize_review(
    sim, state, case, phase, treatment_approved, provider_abandoned_after_denial,
    approved_provider_request, prior_iterations, current_level, stage_map
):
    """finalize service lines and handle post-denial treatment decision"""
    if current_level not in WORKFLOW_LEVELS:
        raise ValueError(f"invalid review level: {current_level}")
    level_config = WORKFLOW_LEVELS[current_level]

    # if Phase 2 and not approved, finalize service line
    if phase == "phase_2_utilization_review" and not treatment_approved:
        if not prior_iterations:
            raise ValueError(f"{phase}: treatment not approved but no prior iterations recorded")

        last_iteration = prior_iterations[-1]
        if "payor_decision" not in last_iteration:
            raise ValueError(f"{phase}: missing payor_decision in last iteration")
        last_payor_action = last_iteration["payor_decision"]

        finalize_service_line_after_non_approval(
            state=state,
            provider_request=approved_provider_request,
            last_payor_action=last_payor_action,
            phase=phase,
            current_level=current_level,
            level_config=level_config
        )

        # update state flags
        state.denial_occurred = (last_payor_action == "denied")

        # CRITICAL: Phase 2 denied and provider abandoned - decide whether to treat anyway
        if last_payor_action == "denied" and provider_abandoned_after_denial:
            treatment_decision = provider_treatment_decision_after_phase2_denial(sim, state, case)
            state.provider_treated_despite_denial = (treatment_decision == "treat_anyway")

            if treatment_decision == "no_treat":
                state.care_abandoned = True

    # collect test results
    accumulated_test_results = {}
    for iteration in prior_iterations:
        if "test_results" in iteration:
            accumulated_test_results.update(iteration["test_results"])

    # store evidence
    evidence_attr = f"_{phase}_evidence"
    setattr(state, evidence_attr, {
        "approved_request": approved_provider_request,
        "test_results": accumulated_test_results,
        "iterations": prior_iterations
    })
