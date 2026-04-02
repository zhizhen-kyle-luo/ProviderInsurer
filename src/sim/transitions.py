from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

VALID_STATUSES = {"approved", "modified", "denied", "pending_info"}

# normalize common LLM status variants
_STATUS_ALIASES = {
    "pended": "pending_info",
    "pending": "pending_info",
    "pend": "pending_info",
    "approve": "approved",
    "deny": "denied",
    "modify": "modified",
}


def _normalize_status(status: str) -> str:
    s = status.lower().strip()
    return _STATUS_ALIASES.get(s, s)


def _find_line(state, line_number: int):
    for line in state.service_lines:
        if line.line_number == line_number:
            return line
    raise ValueError(f"unknown line_number={line_number}")


def _next_line_number(state) -> int:
    if not state.service_lines:
        return 1
    return max(l.line_number for l in state.service_lines) + 1


def _clear_phase2_decision_outputs(line) -> None:
    line.authorization_status = None
    line.approved_quantity = None
    line.authorization_number = None
    line.modification_type = None
    line.decision_reason = None
    line.requested_documents = []
    line.accepted_modification = False


def apply_phase2_insurer_line_adjudications(
    *,
    state,
    line_adjudications: List[Dict[str, Any]],
    reviewer_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []

    for adj in line_adjudications:
        if "line_number" not in adj:
            raise ValueError(f"bad line_adjudication (need line_number): {adj}")
        if "authorization_status" not in adj:
            raise ValueError(f"bad line_adjudication (need authorization_status): {adj}")

        ln = int(adj["line_number"])
        status = _normalize_status(str(adj["authorization_status"]))
        if status not in VALID_STATUSES:
            raise ValueError(f"bad authorization_status={status} for line_number={ln}")

        line = _find_line(state, ln)

        old = {
            "authorization_status": line.authorization_status,
            "approved_quantity": line.approved_quantity,
            "authorization_number": line.authorization_number,
            "modification_type": line.modification_type,
            "decision_reason": line.decision_reason,
            "requested_documents": list(line.requested_documents),
            "reviewer_type": line.reviewer_type,
            "current_review_level": line.current_review_level,
            "pend_round": line.pend_round,
            "pend_total": line.pend_total,
        }

        _clear_phase2_decision_outputs(line)

        line.authorization_status = status
        line.decision_reason = adj.get("decision_reason")
        line.awaiting_response_at_level = None  # insurer has responded

        if status == "pending_info":
            from src.utils.prompts.config import MAX_REQUEST_INFO_PER_LEVEL

            if line.pend_round >= MAX_REQUEST_INFO_PER_LEVEL:
                raise ValueError(
                    f"line {ln} already pended {line.pend_round} times at level {line.current_review_level}; "
                    f"max={MAX_REQUEST_INFO_PER_LEVEL}"
                )

            req = adj.get("requested_documents")
            if not isinstance(req, list):
                raise ValueError(f"requested_documents must be list for pending_info: {adj}")
            req = [str(x) for x in req if str(x).strip()]
            if not req:
                raise ValueError("pending_info must include at least one requested_document")
            line.requested_documents = req
            line.pend_round += 1
            line.pend_total += 1
        else:
            line.pend_round = 0

        if status in {"approved", "modified"}:
            if adj.get("approved_quantity") is not None:
                line.approved_quantity = int(adj["approved_quantity"])
            if adj.get("authorization_number") is not None:
                line.authorization_number = str(adj["authorization_number"])

        if status == "modified":
            mt = adj.get("modification_type")
            if mt is None:
                raise ValueError("modified requires modification_type")
            line.modification_type = str(mt)

        if reviewer_type is not None:
            line.reviewer_type = reviewer_type

        new = {
            "authorization_status": line.authorization_status,
            "approved_quantity": line.approved_quantity,
            "authorization_number": line.authorization_number,
            "modification_type": line.modification_type,
            "decision_reason": line.decision_reason,
            "requested_documents": list(line.requested_documents),
            "reviewer_type": line.reviewer_type,
            "current_review_level": line.current_review_level,
            "pend_round": line.pend_round,
            "pend_total": line.pend_total,
        }

        deltas.append({"kind": "phase2_line_adjudicated", "line_number": ln, "old": old, "new": new})

    return deltas


def _is_line_terminal_phase2(line) -> bool:
    """Check if a line has reached terminal state in Phase 2."""
    # if awaiting insurer response at a level (appeal filed but not yet adjudicated), not terminal
    if getattr(line, "awaiting_response_at_level", None) is not None:
        return False

    auth_status = getattr(line, "authorization_status", None)
    if auth_status is None:
        # Not yet reviewed by payor - need to get response first
        return False
    status = str(auth_status).lower()

    if status == "approved":
        return True

    if status == "modified":
        if getattr(line, "accepted_modification", False):
            return True  # accepted the modification
        if getattr(line, "abandoned", False):
            return True  # gave up fighting
        # provider must still choose to accept modification or abandon (even at level 2)
        return False

    if status == "denied":
        if getattr(line, "abandoned", False):
            return True  # gave up
        # provider must still choose abandon mode (NO_TREAT or TREAT_ANYWAY), even at level 2
        return False

    # pending_info or no status yet
    return False


def _all_lines_terminal_phase2(state) -> bool:
    """Check if all lines have reached terminal state."""
    lines = state.service_lines
    if lines is None:
        raise ValueError("state.service_lines is None")
    if not lines:
        # No lines yet means we haven't submitted - not terminal, need to build first submission
        return False
    return all(_is_line_terminal_phase2(l) for l in lines)


def apply_phase2_provider_bundle_action(
    *,
    state,
    provider_action: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    deltas: List[Dict[str, Any]] = []

    if "action" not in provider_action:
        raise ValueError("provider_action missing action")

    action = str(provider_action["action"]).upper()

    # =========================================================================
    # RESUBMIT: Bundle-level action - withdraw entire PA, start fresh
    # =========================================================================
    if action == "RESUBMIT":
        resubmit_reason = provider_action.get("resubmit_reason", "")

        # Record withdrawn lines for audit trail
        withdrawn_lines = [
            {
                "line_number": l.line_number,
                "procedure_code": l.procedure_code,
                "service_name": l.service_name,
                "authorization_status": l.authorization_status,
                "decision_reason": l.decision_reason,
            }
            for l in state.service_lines
        ]

        # Clear service lines - next build_submission creates new ones
        state.service_lines = []
        state.current_level = 0

        deltas.append({
            "kind": "phase2_provider_resubmit",
            "resubmit_reason": resubmit_reason,
            "withdrawn_lines": withdrawn_lines,
        })

        # Not terminated - simulation continues with fresh submission
        return deltas, False, "RESUBMIT"

    # =========================================================================
    # LINE_ACTIONS: Per-line actions
    # =========================================================================
    if action == "LINE_ACTIONS":
        if "line_actions" not in provider_action:
            raise ValueError("LINE_ACTIONS requires line_actions field")
        line_actions = provider_action["line_actions"]
        if not isinstance(line_actions, list):
            raise ValueError("LINE_ACTIONS requires line_actions array")
        if not line_actions:
            raise ValueError("LINE_ACTIONS requires at least one line action")

        for la in line_actions:
            if not isinstance(la, dict):
                raise ValueError(f"line_action must be dict: {la}")
            if "line_number" not in la or "action" not in la:
                raise ValueError(f"line_action needs line_number and action: {la}")

            ln = int(la["line_number"])
            line_action = str(la["action"]).upper()
            line = _find_line(state, ln)
            if line.authorization_status is None:
                raise ValueError(f"line {ln} has no authorization_status - cannot process action")
            status = str(line.authorization_status).lower()

            # Validate action is appropriate for line status
            if status == "approved":
                raise ValueError(f"Line {ln} is approved - no action needed, omit from line_actions")

            if line_action == "ACCEPT_MODIFY":
                if status != "modified":
                    raise ValueError(f"ACCEPT_MODIFY only valid for modified lines, line {ln} is {status}")
                line.accepted_modification = True
                deltas.append({"kind": "phase2_accept_modify", "line_number": ln})

            elif line_action == "PROVIDE_DOCS":
                if status != "pending_info":
                    raise ValueError(f"PROVIDE_DOCS only valid for pending_info lines, line {ln} is {status}")
                deltas.append({"kind": "phase2_provide_docs", "line_number": ln})

            elif line_action == "APPEAL":
                if status not in {"denied", "modified"}:
                    raise ValueError(f"APPEAL only valid for denied/modified lines, line {ln} is {status}")
                if "to_level" not in la:
                    raise ValueError(f"APPEAL requires to_level for line {ln}")
                to_level = int(la["to_level"])
                if to_level not in (1, 2):
                    raise ValueError(f"to_level must be 1 or 2, got {to_level}")
                cur = int(line.current_review_level)
                if to_level != cur + 1:
                    raise ValueError(f"appeal must advance by +1: line={ln} cur={cur} to={to_level}")
                line.current_review_level = to_level
                line.pend_round = 0
                line.awaiting_response_at_level = to_level  # mark waiting for insurer response
                deltas.append({"kind": "phase2_appeal_advanced", "line_number": ln, "from_level": cur, "to_level": to_level})

            elif line_action == "ABANDON":
                if status not in {"denied", "modified", "pending_info"}:
                    raise ValueError(f"ABANDON only valid for denied/modified/pending_info lines, line {ln} is {status}")
                if "mode" not in la:
                    raise ValueError(f"ABANDON requires mode (NO_TREAT or TREAT_ANYWAY) for line {ln}")
                mode = str(la["mode"]).upper()
                if mode not in {"NO_TREAT", "TREAT_ANYWAY"}:
                    raise ValueError(f"ABANDON mode must be NO_TREAT or TREAT_ANYWAY, got {mode}")
                line.abandoned = True
                if mode == "TREAT_ANYWAY":
                    line.treat_anyway = True
                    line.delivered = True
                    deltas.append({"kind": "phase2_abandon_treat_anyway", "line_number": ln})
                else:
                    line.delivered = False
                    deltas.append({"kind": "phase2_abandon_no_treat", "line_number": ln})

            else:
                raise ValueError(f"Unknown line action: {line_action}")

        # Check if all lines are now terminal
        all_terminal = _all_lines_terminal_phase2(state)
        return deltas, all_terminal, "ALL_TERMINAL" if all_terminal else None

    raise ValueError(f"unknown provider action: {action}. Must be RESUBMIT or LINE_ACTIONS")


def apply_phase3_insurer_line_adjudications(
    *,
    state,
    line_adjudications: List[Dict[str, Any]],
    reviewer_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []

    for adj in line_adjudications:
        if "line_number" not in adj:
            raise ValueError(f"bad line_adjudication (need line_number): {adj}")
        if "adjudication_status" not in adj:
            raise ValueError(f"bad line_adjudication (need adjudication_status): {adj}")

        ln = int(adj["line_number"])
        line = _find_line(state, ln)

        status = _normalize_status(str(adj["adjudication_status"]))
        if status not in VALID_STATUSES:
            raise ValueError(f"bad adjudication_status={status} for line_number={ln}")

        old = {
            "adjudication_status": line.adjudication_status,
            # "allowed_amount": line.allowed_amount,
            # "paid_amount": line.paid_amount,
            "adjustment_group_code": line.adjustment_group_code,
            # "adjustment_amount": line.adjustment_amount,
            "decision_reason": line.decision_reason,
            "requested_documents": list(line.requested_documents),
            "reviewer_type": line.reviewer_type,
            "claims_review_level": line.current_review_level,
            "pend_round": line.pend_round,
            "pend_total": line.pend_total,
        }

        line.adjudication_status = None
        # line.allowed_amount = None
        # line.paid_amount = None
        line.adjustment_group_code = None
        # line.adjustment_amount = None
        line.decision_reason = None
        line.requested_documents = []

        line.adjudication_status = status
        line.decision_reason = adj.get("decision_reason")
        line.awaiting_response_at_level = None  # insurer has responded

        if status == "pending_info":
            from src.utils.prompts.config import MAX_REQUEST_INFO_PER_LEVEL

            if line.pend_round >= MAX_REQUEST_INFO_PER_LEVEL:
                raise ValueError(
                    f"line {ln} already pended {line.pend_round} times at level {line.current_review_level}; "
                    f"max={MAX_REQUEST_INFO_PER_LEVEL}"
                )

            req = adj.get("requested_documents")
            if not isinstance(req, list):
                raise ValueError(f"requested_documents must be list for pending_info: {adj}")
            req = [str(x) for x in req if str(x).strip()]
            if not req:
                raise ValueError("pending_info must include at least one requested_document")
            line.requested_documents = req
            line.pend_round += 1
            line.pend_total += 1
        else:
            line.pend_round = 0

        # if status in {"approved", "modified"}:
        #     if adj.get("allowed_amount") is not None:
        #         line.allowed_amount = float(adj["allowed_amount"])
        #     if adj.get("paid_amount") is not None:
        #         line.paid_amount = float(adj["paid_amount"])

        if status == "modified":
            if adj.get("adjustment_group_code") is not None:
                line.adjustment_group_code = str(adj["adjustment_group_code"])
            # if adj.get("adjustment_amount") is not None:
            #     line.adjustment_amount = float(adj["adjustment_amount"])

        if reviewer_type is not None:
            line.reviewer_type = reviewer_type

        new = {
            "adjudication_status": line.adjudication_status,
            # "allowed_amount": line.allowed_amount,
            # "paid_amount": line.paid_amount,
            "adjustment_group_code": line.adjustment_group_code,
            # "adjustment_amount": line.adjustment_amount,
            "decision_reason": line.decision_reason,
            "requested_documents": list(line.requested_documents),
            "reviewer_type": line.reviewer_type,
            "claims_review_level": line.current_review_level,
            "pend_round": line.pend_round,
            "pend_total": line.pend_total,
        }

        deltas.append({"kind": "phase3_line_adjudicated", "line_number": ln, "old": old, "new": new})

    return deltas


def _is_line_terminal_phase3(line) -> bool:
    """Check if a delivered line has reached terminal state in Phase 3."""
    if not getattr(line, "delivered", False):
        return True  # non-delivered lines are terminal (nothing to claim)

    if getattr(line, "awaiting_response_at_level", None) is not None:
        return False

    adj_status = getattr(line, "adjudication_status", None)
    if adj_status is None:
        return False
    status = str(adj_status).lower()

    if status == "approved":
        return True

    if status == "modified":
        if getattr(line, "accepted_modification", False):
            return True
        if getattr(line, "abandoned", False):
            return True
        # provider must still choose (even at level 2)
        return False

    if status == "denied":
        if getattr(line, "abandoned", False):
            return True
        # provider must still choose WRITE_OFF (even at level 2)
        return False

    # pending_info or no status yet
    return False


def _all_lines_terminal_phase3(state) -> bool:
    """Check if all delivered lines have reached terminal state."""
    lines = state.service_lines
    if lines is None:
        raise ValueError("state.service_lines is None")
    delivered_lines = [l for l in lines if getattr(l, "delivered", False)]
    if not delivered_lines:
        raise ValueError("No delivered lines found - cannot check Phase 3 terminal status")
    return all(_is_line_terminal_phase3(l) for l in delivered_lines)


def apply_phase3_provider_bundle_action(
    *,
    state,
    provider_action: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    deltas: List[Dict[str, Any]] = []

    if "action" not in provider_action:
        raise ValueError("provider_action missing action")

    action = str(provider_action["action"]).upper()

    # =========================================================================
    # RESUBMIT: Bundle-level action - withdraw all claims, start fresh
    # =========================================================================
    if action == "RESUBMIT":
        resubmit_reason = provider_action.get("resubmit_reason", "")

        withdrawn_lines = [
            {
                "line_number": l.line_number,
                "procedure_code": l.procedure_code,
                "service_name": l.service_name,
                "adjudication_status": l.adjudication_status,
                "decision_reason": l.decision_reason,
            }
            for l in state.service_lines
            if getattr(l, "delivered", False)
        ]

        state.service_lines = []
        state.current_level = 0

        deltas.append({
            "kind": "phase3_provider_resubmit",
            "resubmit_reason": resubmit_reason,
            "withdrawn_lines": withdrawn_lines,
        })

        return deltas, False, "RESUBMIT"

    # =========================================================================
    # LINE_ACTIONS: Per-line actions (Phase 3 uses same model as Phase 2)
    # =========================================================================
    if action == "LINE_ACTIONS":
        if "line_actions" not in provider_action:
            raise ValueError("LINE_ACTIONS requires line_actions field")
        line_actions = provider_action["line_actions"]
        if not isinstance(line_actions, list):
            raise ValueError("LINE_ACTIONS requires line_actions array")
        if not line_actions:
            raise ValueError("LINE_ACTIONS requires at least one line action")

        for la in line_actions:
            if not isinstance(la, dict):
                raise ValueError(f"line_action must be dict: {la}")
            if "line_number" not in la or "action" not in la:
                raise ValueError(f"line_action needs line_number and action: {la}")

            ln = int(la["line_number"])
            line_action = str(la["action"]).upper()
            line = _find_line(state, ln)

            if not getattr(line, "delivered", False):
                raise ValueError(f"Line {ln} was not delivered - cannot take action in Phase 3")

            if line.adjudication_status is None:
                raise ValueError(f"line {ln} has no adjudication_status - cannot process action")
            status = str(line.adjudication_status).lower()

            if status == "approved":
                raise ValueError(f"Line {ln} is approved - no action needed, omit from line_actions")

            if line_action == "ACCEPT_MODIFY":
                if status != "modified":
                    raise ValueError(f"ACCEPT_MODIFY only valid for modified lines, line {ln} is {status}")
                line.accepted_modification = True
                deltas.append({"kind": "phase3_accept_modify", "line_number": ln})

            elif line_action == "PROVIDE_DOCS":
                if status != "pending_info":
                    raise ValueError(f"PROVIDE_DOCS only valid for pending_info lines, line {ln} is {status}")
                deltas.append({"kind": "phase3_provide_docs", "line_number": ln})

            elif line_action == "APPEAL":
                if status not in {"denied", "modified"}:
                    raise ValueError(f"APPEAL only valid for denied/modified lines, line {ln} is {status}")
                if "to_level" not in la:
                    raise ValueError(f"APPEAL requires to_level for line {ln}")
                to_level = int(la["to_level"])
                if to_level not in (1, 2):
                    raise ValueError(f"to_level must be 1 or 2, got {to_level}")
                cur = int(line.current_review_level)
                if to_level != cur + 1:
                    raise ValueError(f"appeal must advance by +1: line={ln} cur={cur} to={to_level}")
                line.current_review_level = to_level
                line.pend_round = 0
                line.awaiting_response_at_level = to_level
                deltas.append({"kind": "phase3_appeal_advanced", "line_number": ln, "from_level": cur, "to_level": to_level})

            elif line_action == "ABANDON":
                if status not in {"denied", "modified", "pending_info"}:
                    raise ValueError(f"ABANDON only valid for denied/modified/pending_info lines, line {ln} is {status}")
                if "mode" not in la:
                    raise ValueError(f"ABANDON requires mode (WRITE_OFF) for line {ln}")
                mode = str(la["mode"]).upper()
                if mode != "WRITE_OFF":
                    raise ValueError(f"Phase 3 ABANDON mode must be WRITE_OFF, got {mode}")
                line.abandoned = True
                deltas.append({"kind": "phase3_abandon_write_off", "line_number": ln})

            else:
                raise ValueError(f"Unknown line action: {line_action}")

        # Check if all delivered lines are now terminal
        all_terminal = _all_lines_terminal_phase3(state)
        return deltas, all_terminal, "ALL_TERMINAL" if all_terminal else None

    raise ValueError(f"unknown provider action: {action}. Must be RESUBMIT or LINE_ACTIONS")
