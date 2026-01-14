"""handle different payor decision outcomes"""
from typing import Dict, Any, List, Tuple, TYPE_CHECKING

from src.models import EncounterState
from .provider_actions import get_provider_action_after_payor_decision
from .service_line_builder import create_or_update_service_line_from_approval

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


class DecisionOutcome:
    """return type for decision handlers"""
    def __init__(self, should_continue: bool, should_escalate: bool, is_terminal: bool):
        self.should_continue = should_continue  # continue at same level
        self.should_escalate = should_escalate  # escalate to next level
        self.is_terminal = is_terminal  # end simulation


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
    # TERMINAL SUCCESS: APPROVE of TREATMENT or LEVEL_OF_CARE
    if request_type in ["treatment", "level_of_care"]:
        # create/update service line with approval
        create_or_update_service_line_from_approval(
            state=state,
            provider_request=provider_request,
            payor_decision=payor_decision,
            request_type=request_type
        )

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
        return DecisionOutcome(True, False, False), None

    # APPROVE in Phase 3 claims (payment approved)
    elif phase == "phase_3_claims":
        state.claim_pended = False
        state.claim_rejected = False
        prior_iterations.append(iteration_record)

        # mark this line as approved (update first line for MVP)
        if state.service_lines:
            state.service_lines[0].adjudication_status = "approved"
            state.service_lines[0].paid_amount = payor_decision.get("paid_amount")
            state.service_lines[0].allowed_amount = payor_decision.get("allowed_amount")

        # check if all lines terminal
        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal), None

    # unknown scenario
    prior_iterations.append(iteration_record)
    return DecisionOutcome(False, False, True), None


def handle_modification(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
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

        # mark line as modified (for MVP: first line)
        if state.service_lines:
            if phase == "phase_2_utilization_review":
                state.service_lines[0].authorization_status = "modified"
                state.service_lines[0].approved_quantity = payor_decision.get("approved_quantity")
                state.service_lines[0].modification_type = payor_decision.get("modification_type")
            else:
                state.service_lines[0].adjudication_status = "modified"
                state.service_lines[0].allowed_amount = payor_decision.get("allowed_amount")

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
    if state.service_lines:
        state.service_lines[0].provider_action = provider_action

    if provider_action == "appeal":
        prior_iterations.append(iteration_record)
        return DecisionOutcome(False, True, False)  # escalate to next authority
    else:  # abandon
        # mark line as modified and terminal
        if state.service_lines:
            if phase == "phase_2_utilization_review":
                state.service_lines[0].authorization_status = "modified"
                state.service_lines[0].approved_quantity = payor_decision.get("approved_quantity")
                state.service_lines[0].modification_type = payor_decision.get("modification_type")
            else:
                state.service_lines[0].adjudication_status = "modified"
                state.service_lines[0].allowed_amount = payor_decision.get("allowed_amount")

        prior_iterations.append(iteration_record)
        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal)  # accept modification, exit


def handle_denial(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
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
        # mark line as denied (for MVP: first line)
        if state.service_lines:
            if phase == "phase_2_utilization_review":
                state.service_lines[0].authorization_status = "denied"
            else:
                state.service_lines[0].adjudication_status = "denied"
            if "decision_reason" in payor_decision and payor_decision["decision_reason"]:
                state.service_lines[0].decision_reason = payor_decision["decision_reason"]

        prior_iterations.append(iteration_record)
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
    if state.service_lines:
        state.service_lines[0].provider_action = provider_action

    if provider_action == "appeal":
        prior_iterations.append(iteration_record)
        return DecisionOutcome(False, True, False), False  # escalate to next authority
    else:  # abandon
        # mark line as denied and terminal
        if state.service_lines:
            if phase == "phase_2_utilization_review":
                state.service_lines[0].authorization_status = "denied"
            else:
                state.service_lines[0].adjudication_status = "denied"
            if "decision_reason" in payor_decision and payor_decision["decision_reason"]:
                state.service_lines[0].decision_reason = payor_decision["decision_reason"]

        provider_abandoned = (phase == "phase_2_utilization_review")
        prior_iterations.append(iteration_record)
        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal), provider_abandoned


def handle_pend(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
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
    if state.service_lines:
        state.service_lines[0].provider_action = provider_action

    if provider_action == "continue":
        # stay at same level, provider will address pend
        prior_iterations.append(iteration_record)
        return DecisionOutcome(True, False, False)
    else:  # abandon
        # mark line as pending_info and terminal (abandoned pend)
        if state.service_lines:
            if phase == "phase_2_utilization_review":
                state.service_lines[0].authorization_status = "pending_info"
            else:
                state.service_lines[0].adjudication_status = "pending_info"
            if "decision_reason" in payor_decision and payor_decision["decision_reason"]:
                state.service_lines[0].decision_reason = payor_decision["decision_reason"]
            if "requested_documents" in payor_decision:
                requested_docs = payor_decision["requested_documents"]
                if not isinstance(requested_docs, list):
                    raise ValueError("payor_decision.requested_documents must be a list for pending_info")
                state.service_lines[0].requested_documents = requested_docs

        prior_iterations.append(iteration_record)
        is_terminal = _all_service_lines_terminal(state, phase)
        return DecisionOutcome(False, False, is_terminal)
