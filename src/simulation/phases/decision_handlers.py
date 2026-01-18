"""handle different payor decision outcomes"""
from typing import Dict, Any, List, Tuple, Optional, TYPE_CHECKING

from src.models import EncounterState, ServiceLineRequest
from .provider_actions import get_provider_action_after_payor_decision
from .service_line_builder import (
    create_or_update_service_line_from_approval,
    create_service_lines_from_provider_request
)

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


class DecisionOutcome:
    """return type for decision handlers"""
    def __init__(self, should_continue: bool, should_escalate: bool, is_terminal: bool):
        self.should_continue = should_continue  # continue at same level
        self.should_escalate = should_escalate  # escalate to next level
        self.is_terminal = is_terminal  # end simulation


def _find_service_line_by_number(state: EncounterState, line_number: int) -> Optional[ServiceLineRequest]:
    """find service line by line_number, returns None if not found"""
    for line in state.service_lines:
        if line.line_number == line_number:
            return line
    return None


def _apply_line_adjudication(line: ServiceLineRequest, adjudication: Dict[str, Any], phase: str) -> None:
    """apply a single line adjudication from payor response to a service line"""
    if "adjudication_status" not in adjudication:
        raise ValueError("line_adjudication missing required field 'adjudication_status'")
    status = adjudication["adjudication_status"]

    if phase == "phase_2_utilization_review":
        line.authorization_status = status
        if status == "modified":
            line.approved_quantity = adjudication.get("approved_quantity")
            line.modification_type = adjudication.get("modification_type")
    else:
        line.adjudication_status = status
        line.allowed_amount = adjudication.get("allowed_amount")
        line.paid_amount = adjudication.get("paid_amount")
        if status == "modified":
            line.adjustment_amount = adjudication.get("adjustment_amount")

    if adjudication.get("decision_reason"):
        line.decision_reason = adjudication["decision_reason"]
    if adjudication.get("requested_documents"):
        requested_docs = adjudication["requested_documents"]
        if not isinstance(requested_docs, list):
            raise ValueError("line_adjudication.requested_documents must be a list")
        line.requested_documents = requested_docs


def _apply_all_line_adjudications(state: EncounterState, payor_decision: Dict[str, Any], phase: str) -> None:
    """apply line_adjudications array from payor response to all matching service lines"""
    if not state.service_lines:
        raise ValueError("cannot apply line_adjudications without service_lines")
    if "line_adjudications" not in payor_decision:
        raise ValueError("payor_decision missing required field 'line_adjudications'")

    line_adjudications = payor_decision["line_adjudications"]
    if not isinstance(line_adjudications, list):
        raise ValueError("payor_decision.line_adjudications must be a list")

    valid_line_numbers = {line.line_number for line in state.service_lines}

    for adj in line_adjudications:
        if "line_number" not in adj:
            raise ValueError("line_adjudication missing required field 'line_number'")
        line_number = adj["line_number"]
        line = _find_service_line_by_number(state, line_number)
        if not line:
            # LLM hallucinated a line number - try to recover
            if len(state.service_lines) == 1:
                # single line case: apply to the only line we have
                print(f"  warning: payor returned line_number {line_number}, mapping to line {state.service_lines[0].line_number}")
                line = state.service_lines[0]
            else:
                print(f"  warning: skipping unknown line_number {line_number} (valid: {valid_line_numbers})")
                continue
        _apply_line_adjudication(line, adj, phase)


def _is_line_terminal(line: ServiceLineRequest, phase: str) -> bool:
    """
    check if a single service line has reached terminal status.

    terminal rules per line (from PROVIDER_RESPONSE_MATRIX):
    - APPROVE of TREATMENT or LEVEL_OF_CARE: terminal (success)
    - APPROVE of DIAGNOSTIC: terminal if post_diagnostic_decision="no_treatment_needed"
                             non-terminal if decision pending or "request_treatment"
    - MODIFY/DENY/PENDING_INFO with provider_action=ABANDON: terminal
    - MODIFY/DENY/PENDING_INFO without ABANDON: NOT terminal (can appeal/continue)
    """
    if phase == "phase_2_utilization_review":
        status = line.authorization_status
        request_type = line.request_type

        if status is None:
            return False  # not yet decided

        if status == "approved":
            if request_type is None:
                raise ValueError("missing request_type for terminal check")
            if request_type == "diagnostic_test":
                # approved diagnostic: terminal if provider decides no treatment needed
                # uses post_diagnostic_decision field (not provider_action)
                return line.post_diagnostic_decision == "no_treatment_needed"
            if request_type in {"treatment", "level_of_care"}:
                return True  # approved treatment/level_of_care is terminal
            raise ValueError(f"invalid request_type '{request_type}'")

        if status in {"modified", "denied", "pending_info"}:
            return line.provider_action == "abandon"

        raise ValueError(f"invalid authorization_status '{status}'")
    else:
        # phase 3 claims
        status = line.adjudication_status
        if status is None:
            return False
        if status == "pending_info":
            return line.provider_action == "abandon"
        if status in {"approved", "modified", "denied"}:
            return True
        raise ValueError(f"invalid adjudication_status '{status}'")


def _all_service_lines_terminal(state: EncounterState, phase: str) -> bool:
    """
    check if ALL service lines have reached terminal status.

    each line is evaluated independently - one line being non-terminal
    doesn't affect other lines' terminal status.
    """
    if not state.service_lines:
        return False

    for line in state.service_lines:
        if not _is_line_terminal(line, phase):
            return False

    return True


def _is_approved_diagnostic_needing_result(line: ServiceLineRequest) -> bool:
    """check if line is an approved diagnostic test awaiting result"""
    return (
        line.request_type == "diagnostic_test" and
        line.authorization_status == "approved" and
        line.post_diagnostic_decision is None and
        line.service_name is not None
    )


def _generate_and_log_test_result(
    sim: "UtilizationReviewSimulation",
    line: ServiceLineRequest,
    case: Dict[str, Any],
    phase: str
) -> Dict[str, Any]:
    """generate test result and log environment action"""
    test_result = sim._generate_test_result(line.service_name, case)
    # ASSUMPTION: when insurer approves a diagnostic test, it is always performed
    sim.audit_logger.log_environment_action(
        phase=phase,
        action_type="generate_test_result",
        description=f"generated result for {line.service_name}",
        outcome={
            "test_name": line.service_name,
            "test_result": test_result["value"],
            "generated_by_llm": test_result.get("generated", True),
            "source": "template" if not test_result.get("generated", True) else "llm"
        },
        metadata={
            "case_id": case.get("case_id"),
            "service_line": line.line_number
        }
    )
    return test_result


def _handle_phase3_approval(
    state: EncounterState,
    payor_decision: Dict[str, Any],
    phase: str,
    iteration_record: Dict[str, Any],
    prior_iterations: List[Dict]
) -> Tuple["DecisionOutcome", None]:
    """handle approval for phase 3 claims"""
    state.claim_pended = False
    state.claim_rejected = False
    if not state.service_lines:
        raise ValueError("phase 3 approval requires service_lines")
    if "line_adjudications" not in payor_decision:
        raise ValueError("phase 3 payor_decision missing required field 'line_adjudications'")
    _apply_all_line_adjudications(state, payor_decision, phase)
    prior_iterations.append(iteration_record)
    is_terminal = _all_service_lines_terminal(state, phase)
    return DecisionOutcome(False, False, is_terminal), None


def _generate_test_results_for_diagnostics(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any],
    phase: str,
    iteration_record: Dict[str, Any]
) -> Dict[str, str]:
    """generate test results for approved diagnostic lines and get post-diagnostic decisions"""
    test_results = {}
    for line in state.service_lines:
        if _is_approved_diagnostic_needing_result(line):
            test_result = _generate_and_log_test_result(sim, line, case, phase)
            test_results[line.service_name] = test_result["value"]
    if test_results:
        iteration_record["test_results"] = test_results
    # get post-diagnostic decisions
    for line in state.service_lines:
        if _is_approved_diagnostic_needing_result(line):
            test_result_value = test_results.get(line.service_name, "result unavailable")
            line.post_diagnostic_decision = sim._get_post_diagnostic_decision(state, line, test_result_value)
    return test_results


def _has_pending_treatment_request(state: EncounterState) -> bool:
    """check if any diagnostic line has request_treatment decision pending continuation"""
    return any(
        line.request_type == "diagnostic_test" and
        line.authorization_status == "approved" and
        line.post_diagnostic_decision == "request_treatment"
        for line in state.service_lines
    )


def handle_approval(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any],
    request_type: str,
    phase: str,
    iteration_record: Dict[str, Any],
    prior_iterations: List[Dict],
    case: Dict[str, Any]
) -> Tuple[DecisionOutcome, Dict[str, Any]]:
    """
    handle APPROVED decision.

    supports mixed request types - each line evaluated by its own request_type.
    terminal logic delegated to _all_service_lines_terminal().

    Returns: (DecisionOutcome, approved_provider_request or None)
    """
    if phase == "phase_3_claims":
        return _handle_phase3_approval(state, payor_decision, phase, iteration_record, prior_iterations)

    # phase 2 utilization review
    if not state.service_lines:
        create_service_lines_from_provider_request(state, provider_request, payor_decision)

    create_or_update_service_line_from_approval(
        state=state,
        provider_request=provider_request,
        payor_decision=payor_decision,
        request_type=request_type
    )
    _apply_all_line_adjudications(state, payor_decision, phase)
    _generate_test_results_for_diagnostics(sim, state, case, phase, iteration_record)

    prior_iterations.append(iteration_record)
    is_terminal = _all_service_lines_terminal(state, phase)
    should_continue = _has_pending_treatment_request(state) and not is_terminal

    return DecisionOutcome(should_continue, False, is_terminal), provider_request if is_terminal else None


def handle_modification(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any],
    request_type: str,
    phase: str,
    current_level: int,
    iteration_record: Dict[str, Any],
    prior_iterations: List[Dict]
) -> DecisionOutcome:
    """
    handle MODIFIED decision (partial approval or downgrade).

    provider must choose APPEAL or ABANDON.
    """
    state.denial_occurred = False  # not a full denial

    # at Level 2 (IRE): final decision, cannot appeal further
    if current_level >= 2:
        prior_iterations.append(iteration_record)
        if phase == "phase_2_utilization_review" and not state.service_lines:
            create_service_lines_from_provider_request(state, provider_request, payor_decision)
        _apply_all_line_adjudications(state, payor_decision, phase)
        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal)

    provider_action = get_provider_action_after_payor_decision(
        sim=sim,
        state=state,
        payor_decision=payor_decision,
        request_type=request_type,
        phase=phase,
        current_level=current_level
    )
    for line in state.service_lines:
        line.provider_action = provider_action

    if provider_action == "appeal":
        prior_iterations.append(iteration_record)
        return DecisionOutcome(False, True, False)  # escalate to next authority

    # abandon: mark lines as modified and terminal
    if phase == "phase_2_utilization_review" and not state.service_lines:
        create_service_lines_from_provider_request(state, provider_request, payor_decision)
    _apply_all_line_adjudications(state, payor_decision, phase)
    prior_iterations.append(iteration_record)
    is_terminal = _all_service_lines_terminal(state, phase)
    return DecisionOutcome(False, False, is_terminal)  # accept modification, exit


def handle_denial(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any],
    request_type: str,
    phase: str,
    current_level: int,
    iteration_record: Dict[str, Any],
    prior_iterations: List[Dict]
) -> Tuple[DecisionOutcome, bool]:
    """
    handle DENIED decision.

    provider must choose APPEAL or ABANDON.

    Returns: (DecisionOutcome, provider_abandoned_after_denial)
    """
    state.denial_occurred = True
    if phase == "phase_3_claims":
        state.claim_pended = False
        state.claim_rejected = True

    # at Level 2 (IRE): final decision, cannot appeal
    if current_level >= 2:
        prior_iterations.append(iteration_record)
        if phase == "phase_2_utilization_review" and not state.service_lines:
            create_service_lines_from_provider_request(state, provider_request, payor_decision)
        _apply_all_line_adjudications(state, payor_decision, phase)
        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal), False

    provider_action = get_provider_action_after_payor_decision(
        sim=sim,
        state=state,
        payor_decision=payor_decision,
        request_type=request_type,
        phase=phase,
        current_level=current_level
    )
    for line in state.service_lines:
        line.provider_action = provider_action

    if provider_action == "appeal":
        prior_iterations.append(iteration_record)
        return DecisionOutcome(False, True, False), False  # escalate to next authority

    # abandon: mark lines as denied and terminal
    if phase == "phase_2_utilization_review" and not state.service_lines:
        create_service_lines_from_provider_request(state, provider_request, payor_decision)
    _apply_all_line_adjudications(state, payor_decision, phase)
    provider_abandoned = (phase == "phase_2_utilization_review")
    prior_iterations.append(iteration_record)
    is_terminal = _all_service_lines_terminal(state, phase)
    return DecisionOutcome(False, False, is_terminal), provider_abandoned


def handle_pend(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    provider_request: Dict[str, Any],
    payor_decision: Dict[str, Any],
    request_type: str,
    phase: str,
    current_level: int,
    iteration_record: Dict[str, Any],
    prior_iterations: List[Dict],
    pend_count_at_level: Dict[int, int]
) -> DecisionOutcome:
    """
    handle PENDING_INFO decision (pend).

    provider should CONTINUE or ABANDON (cannot APPEAL a pend).
    """
    if phase == "phase_3_claims":
        state.claim_pended = True

    # increment pend count for current level (for next iteration's prompt)
    pend_count_at_level[current_level] += 1

    # provider decides to continue or abandon
    provider_action = get_provider_action_after_payor_decision(
        sim=sim,
        state=state,
        payor_decision=payor_decision,
        request_type=request_type,
        phase=phase,
        current_level=current_level
    )
    for line in state.service_lines:
        line.provider_action = provider_action

    if provider_action == "continue":
        # stay at same level, provider will address pend
        prior_iterations.append(iteration_record)
        return DecisionOutcome(True, False, False)

    # abandon: mark lines as pending_info and terminal
    if phase == "phase_2_utilization_review" and not state.service_lines:
        create_service_lines_from_provider_request(state, provider_request, payor_decision)
    _apply_all_line_adjudications(state, payor_decision, phase)
    prior_iterations.append(iteration_record)
    is_terminal = _all_service_lines_terminal(state, phase)
    return DecisionOutcome(False, False, is_terminal)
