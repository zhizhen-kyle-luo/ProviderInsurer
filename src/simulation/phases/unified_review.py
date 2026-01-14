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

from src.models import (
    EncounterState,
    AuthorizationRequest,
    ClaimLineItem
)
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


def process_phase3_provider_claim_lines(
    state: EncounterState,
    provider_request: Dict[str, Any],
    iteration_num: int
) -> None:
    """
    convert provider's procedure_codes array into ClaimLineItem objects
    only process on first iteration or when provider submits new/modified lines
    """
    procedure_codes = provider_request.get("procedure_codes", [])
    if not procedure_codes:
        return

    # on first submission (iteration 0), create all claim lines
    if iteration_num == 0:
        state.claim_lines = []
        for idx, proc in enumerate(procedure_codes, 1):
            line = ClaimLineItem(
                line_number=idx,
                procedure_code=proc.get("code", ""),
                code_type=proc.get("code_type", "CPT"),
                service_description=proc.get("description", ""),
                quantity=proc.get("quantity", 1),
                billed_amount=proc.get("amount_billed", 0.0),
                current_review_level=0
            )
            state.claim_lines.append(line)
    # on subsequent iterations, update existing lines (provider may add documentation but not change billing)
    # note: provider cannot change procedure codes after initial submission


def process_phase3_payor_adjudications(
    state: EncounterState,
    payor_decision: Dict[str, Any],
    iteration_num: int
) -> None:
    """
    process payor's line-level adjudications and update ClaimLineItem objects
    """
    line_adjudications = payor_decision.get("line_adjudications", [])
    if not line_adjudications:
        return

    # match payor adjudications to claim lines by line_number
    for adj in line_adjudications:
        line_num = adj.get("line_number")
        if not line_num:
            continue

        # find corresponding claim line (1-indexed)
        if line_num <= len(state.claim_lines):
            line = state.claim_lines[line_num - 1]

            # update adjudication fields
            line.adjudication_status = adj.get("adjudication_status")
            line.allowed_amount = adj.get("allowed_amount")
            line.paid_amount = adj.get("paid_amount")
            line.adjustment_reason = adj.get("adjustment_reason")
            line.current_review_level = iteration_num
            line.reviewer_type = payor_decision.get("reviewer_type")


def check_phase3_all_lines_finalized(state: EncounterState) -> bool:
    """
    check if all claim lines have been finalized (either approved or provider gave up)
    used for early termination to minimize API calls
    """
    if not state.claim_lines:
        return False

    for line in state.claim_lines:
        # line is NOT finalized if:
        # 1. it's denied but provider hasn't made a decision yet (provider_action is None)
        # 2. provider decided to appeal it (provider_action == "appeal")
        if line.adjudication_status == "denied":
            if line.provider_action is None or line.provider_action == "appeal":
                return False
        # pending lines are also not finalized
        elif line.adjudication_status == "pending":
            return False

    # all lines are either approved or denied+accepted
    return True


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
            # count probing tests
            svc = provider_request.get("requested_service", {}) or {}
            tests = svc.get("tests_requested")
            if isinstance(tests, list) and tests:
                state.friction_metrics.probing_tests_count += len(tests)
            elif request_type == "diagnostic_test":
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
        request_type = provider_request.get("request_type")

        # PHASE 3 ONLY: process line-level claim submission
        if phase == "phase_3_claims":
            process_phase3_provider_claim_lines(state, provider_request, iteration_num)

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

        # PHASE 3 ONLY: process line-level adjudications
        if phase == "phase_3_claims":
            process_phase3_payor_adjudications(state, payor_decision, iteration_num)

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
            sim, state, payor_decision, request_type, phase, current_level,
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
            sim, state, payor_decision, request_type, phase, current_level,
            iteration_record, prior_iterations
        )
        return {
            "terminal": outcome.is_terminal,
            "escalate": outcome.should_escalate,
            "treatment_approved": False,
            "approved_request": None,
            "provider_abandoned": provider_abandoned
        }

        # PHASE 3 ONLY: check for early termination (all lines finalized)
        if phase == "phase_3_claims" and check_phase3_all_lines_finalized(state):
            # all claim lines are either approved or provider accepted the denial
            # no need to continue iterating - early exit to save API calls
            break

    # if treatment never approved, mark as denied
    if not treatment_approved:
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
