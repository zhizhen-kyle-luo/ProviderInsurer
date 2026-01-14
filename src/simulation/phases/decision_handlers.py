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

    for adj in line_adjudications:
        if "line_number" not in adj:
            raise ValueError("line_adjudication missing required field 'line_number'")
        line_number = adj["line_number"]
        line = _find_service_line_by_number(state, line_number)
        if not line:
            raise ValueError(f"line_adjudication references unknown line_number {line_number}")
        _apply_line_adjudication(line, adj, phase)


def _all_service_lines_terminal(state: EncounterState, phase: str) -> bool:
    """
    check if all service lines have reached a terminal status.

    terminal rules come from PROVIDER_RESPONSE_MATRIX in config:
    - APPROVE: terminal for TREATMENT or LEVEL_OF_CARE, not terminal for DIAGNOSTIC
    - MODIFY/DENY/REQUEST_INFO: terminal only if provider_action is ABANDON
    """
    if not state.service_lines:
        return False

    for line in state.service_lines:
        if phase == "phase_2_utilization_review":
            status = line.authorization_status
            request_type = line.request_type
            if status is None:
                return False  # line not yet decided
            if status == "approved":
                if request_type is None:
                    raise ValueError("missing request_type for phase 2 terminal check")
                if request_type == "diagnostic_test":
                    return False  # approved diagnostic is non-terminal
                if request_type in {"treatment", "level_of_care"}:
                    continue
                raise ValueError(f"invalid request_type '{request_type}' for terminal check")
            if status in {"modified", "denied", "pending_info"}:
                if line.provider_action != "abandon":
                    return False
                continue
            raise ValueError(f"invalid authorization_status '{status}' for terminal check")
        else:
            status = line.adjudication_status
            if status is None:
                return False  # line not yet decided
            if status == "pending_info":
                if line.provider_action != "abandon":
                    return False
            elif status not in {"approved", "modified", "denied"}:
                raise ValueError(f"invalid adjudication_status '{status}' for terminal check")

    # all lines have a status = terminal
    return True


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

    Returns: (DecisionOutcome, approved_provider_request or None)
    """
    if phase == "phase_2_utilization_review" and not state.service_lines:
        create_service_lines_from_provider_request(state, provider_request, payor_decision)

    # TERMINAL SUCCESS: APPROVE of TREATMENT or LEVEL_OF_CARE
    if request_type in ["treatment", "level_of_care"]:
        # create/update service lines first, then apply payor adjudications
        create_or_update_service_line_from_approval(
            state=state,
            provider_request=provider_request,
            payor_decision=payor_decision,
            request_type=request_type
        )
        if phase == "phase_2_utilization_review":
            _apply_all_line_adjudications(state, payor_decision, phase)
            test_results = {}
            for line in state.service_lines:
                if line.request_type == "diagnostic_test" and line.authorization_status == "approved":
                    if not line.service_name:
                        raise ValueError("approved diagnostic line missing service_name")
                    test_result = sim._generate_test_result(line.service_name, case)
                    test_results[line.service_name] = test_result["value"]
            if test_results:
                iteration_record["test_results"] = test_results

        prior_iterations.append(iteration_record)

        # CRITICAL: only terminal if ALL service lines are decided
        # For MVP (single line): this line is now approved, so all lines terminal
        # For future multi-line: check if any lines still pending
        is_terminal = _all_service_lines_terminal(state, phase)

        return DecisionOutcome(False, False, is_terminal), provider_request

    # NON-TERMINAL: APPROVE of DIAGNOSTIC - provider must CONTINUE with result
    elif request_type == "diagnostic_test":
        # diagnostic test approved - generate result and provider will CONTINUE
        if phase == "phase_2_utilization_review":
            _apply_all_line_adjudications(state, payor_decision, phase)
            test_results = {}
            for line in state.service_lines:
                if line.request_type == "diagnostic_test" and line.authorization_status == "approved":
                    if not line.service_name:
                        raise ValueError("approved diagnostic line missing service_name")
                    test_result = sim._generate_test_result(line.service_name, case)
                    test_results[line.service_name] = test_result["value"]

            iteration_record["test_results"] = test_results

        # provider will automatically CONTINUE at same level (not an action choice)
        prior_iterations.append(iteration_record)
        return DecisionOutcome(True, False, False), None

    # APPROVE in Phase 3 claims (payment approved)
    elif phase == "phase_3_claims":
        state.claim_pended = False
        state.claim_rejected = False
        prior_iterations.append(iteration_record)

        if not state.service_lines:
            raise ValueError("phase 3 approval requires service_lines")
        if "line_adjudications" not in payor_decision:
            raise ValueError("phase 3 payor_decision missing required field 'line_adjudications'")
        _apply_all_line_adjudications(state, payor_decision, phase)

        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal), None

    # unknown scenario
    prior_iterations.append(iteration_record)
    return DecisionOutcome(False, False, True), None


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
