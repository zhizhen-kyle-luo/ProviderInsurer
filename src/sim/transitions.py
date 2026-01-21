from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


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
    level: Optional[int] = None,
) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []

    for adj in line_adjudications:
        if "line_number" not in adj:
            raise ValueError(f"bad line_adjudication (need line_number): {adj}")
        if "authorization_status" not in adj:
            raise ValueError(f"bad line_adjudication (need authorization_status): {adj}")

        ln = int(adj["line_number"])
        status = str(adj["authorization_status"]).lower()
        if status not in {"approved", "modified", "denied", "pending_info"}:
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
        if level is not None:
            line.current_review_level = int(level)

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


def apply_phase2_provider_bundle_action(
    *,
    state,
    provider_action: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    deltas: List[Dict[str, Any]] = []

    if "action" not in provider_action:
        raise ValueError("provider_action missing action")

    action = str(provider_action["action"]).upper()
    lines = provider_action.get("lines") or []
    if not isinstance(lines, list):
        raise ValueError("provider_action.lines must be a list")

    if action == "ABANDON":
        mode = str(provider_action.get("abandon_mode", "NO_TREAT")).upper()
        treat_anyway = provider_action.get("treat_anyway_lines") or []
        if not isinstance(treat_anyway, list):
            raise ValueError("treat_anyway_lines must be a list")

        treat_anyway = [int(x) for x in treat_anyway]

        for line in state.service_lines:
            line.treat_anyway = False
            if mode == "NO_TREAT":
                line.delivered = False

        if mode == "TREAT_ANYWAY":
            for ln in treat_anyway:
                line = _find_line(state, ln)
                line.treat_anyway = True
                line.delivered = True

        deltas.append({"kind": "phase2_provider_abandon", "mode": mode, "treat_anyway_lines": treat_anyway})
        return deltas, True, f"ABANDON_{mode}"

    if action == "CONTINUE":
        for ins in lines:
            if "line_number" not in ins or "intent" not in ins:
                raise ValueError(f"CONTINUE needs line_number + intent: {ins}")

            ln = int(ins["line_number"])
            intent = str(ins["intent"]).upper()
            line = _find_line(state, ln)

            if intent == "ACCEPT_MODIFY":
                if (line.authorization_status or "").lower() != "modified":
                    raise ValueError("ACCEPT_MODIFY requires current status == modified")
                line.accepted_modification = True
                deltas.append({"kind": "phase2_accept_modify", "line_number": ln})
                continue

            if intent == "RESUBMIT_AMENDED":
                amended_fields = ins.get("amended_fields")
                if not isinstance(amended_fields, dict):
                    raise ValueError("RESUBMIT_AMENDED needs amended_fields dict")

                from src.models.financial import ServiceLineRequest
                model_fields = set(ServiceLineRequest.model_fields.keys())
                immutable_fields = {"line_number", "superseded_by_line", "request_revision"}

                for k in amended_fields.keys():
                    if k not in model_fields:
                        raise ValueError(f"amended_fields key not on ServiceLineRequest: {k}")
                    if k in immutable_fields:
                        raise ValueError(f"cannot amend immutable field: {k}")

                new_line = deepcopy(line)
                new_line.line_number = _next_line_number(state)

                new_line.request_revision = int(line.request_revision) + 1
                new_line.current_review_level = 0
                new_line.reviewer_type = None
                new_line.pend_round = 0
                new_line.pend_total = 0

                _clear_phase2_decision_outputs(new_line)

                for k, v in amended_fields.items():
                    setattr(new_line, k, v)

                line.superseded_by_line = new_line.line_number
                state.service_lines.append(new_line)

                deltas.append(
                    {
                        "kind": "phase2_resubmit_amended",
                        "from_line": ln,
                        "to_line": new_line.line_number,
                        "amended_fields": deepcopy(amended_fields),
                    }
                )
                continue

            deltas.append({"kind": "phase2_provider_continue", "line_number": ln, "intent": intent})

        return deltas, False, None

    if action == "APPEAL":
        for ins in lines:
            if "line_number" not in ins or "to_level" not in ins:
                raise ValueError(f"APPEAL needs line_number + to_level: {ins}")

            ln = int(ins["line_number"])
            to_level = int(ins["to_level"])
            if to_level not in (1, 2):
                raise ValueError(f"to_level must be 1 or 2, got {to_level}")

            line = _find_line(state, ln)
            status = (line.authorization_status or "").lower()

            if status not in {"denied", "modified"}:
                raise ValueError(
                    f"line {ln} has status={status}; only denied/modified can be appealed"
                )

            cur = int(line.current_review_level)
            if to_level != cur + 1:
                raise ValueError(f"appeal must advance by +1: line={ln} cur={cur} to={to_level}")

            line.current_review_level = to_level
            line.pend_round = 0
            deltas.append({"kind": "phase2_appeal_advanced", "line_number": ln, "from_level": cur, "to_level": to_level})

        return deltas, False, None

    raise ValueError(f"unknown provider bundle action: {action}")


def apply_phase3_insurer_line_adjudications(
    *,
    state,
    line_adjudications: List[Dict[str, Any]],
    reviewer_type: Optional[str] = None,
    level: Optional[int] = None,
) -> List[Dict[str, Any]]:
    deltas: List[Dict[str, Any]] = []

    for adj in line_adjudications:
        if "line_number" not in adj:
            raise ValueError(f"bad line_adjudication (need line_number): {adj}")
        if "adjudication_status" not in adj:
            raise ValueError(f"bad line_adjudication (need adjudication_status): {adj}")

        ln = int(adj["line_number"])
        status = str(adj["adjudication_status"]).lower()
        if status not in {"approved", "modified", "denied", "pending_info"}:
            raise ValueError(f"bad adjudication_status={status} for line_number={ln}")

        line = _find_line(state, ln)

        old = {
            "adjudication_status": line.adjudication_status,
            "allowed_amount": line.allowed_amount,
            "paid_amount": line.paid_amount,
            "adjustment_group_code": line.adjustment_group_code,
            "adjustment_amount": line.adjustment_amount,
            "decision_reason": line.decision_reason,
            "requested_documents": list(line.requested_documents),
            "reviewer_type": line.reviewer_type,
            "current_review_level": line.current_review_level,
            "pend_round": line.pend_round,
            "pend_total": line.pend_total,
        }

        line.adjudication_status = None
        line.allowed_amount = None
        line.paid_amount = None
        line.adjustment_group_code = None
        line.adjustment_amount = None
        line.decision_reason = None
        line.requested_documents = []

        line.adjudication_status = status
        line.decision_reason = adj.get("decision_reason")

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
            if adj.get("allowed_amount") is not None:
                line.allowed_amount = float(adj["allowed_amount"])
            if adj.get("paid_amount") is not None:
                line.paid_amount = float(adj["paid_amount"])

        if status == "modified":
            if adj.get("adjustment_group_code") is not None:
                line.adjustment_group_code = str(adj["adjustment_group_code"])
            if adj.get("adjustment_amount") is not None:
                line.adjustment_amount = float(adj["adjustment_amount"])

        if reviewer_type is not None:
            line.reviewer_type = reviewer_type
        if level is not None:
            line.current_review_level = int(level)

        new = {
            "adjudication_status": line.adjudication_status,
            "allowed_amount": line.allowed_amount,
            "paid_amount": line.paid_amount,
            "adjustment_group_code": line.adjustment_group_code,
            "adjustment_amount": line.adjustment_amount,
            "decision_reason": line.decision_reason,
            "requested_documents": list(line.requested_documents),
            "reviewer_type": line.reviewer_type,
            "current_review_level": line.current_review_level,
            "pend_round": line.pend_round,
            "pend_total": line.pend_total,
        }

        deltas.append({"kind": "phase3_line_adjudicated", "line_number": ln, "old": old, "new": new})

    return deltas


def apply_phase3_provider_bundle_action(
    *,
    state,
    provider_action: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    deltas: List[Dict[str, Any]] = []

    if "action" not in provider_action:
        raise ValueError("provider_action missing action")

    action = str(provider_action["action"]).upper()
    lines = provider_action.get("lines") or []
    if not isinstance(lines, list):
        raise ValueError("provider_action.lines must be a list")

    if action == "ABANDON":
        mode = str(provider_action.get("abandon_mode", "WRITE_OFF")).upper()

        deltas.append({"kind": "phase3_provider_abandon", "mode": mode})
        return deltas, True, f"ABANDON_{mode}"

    if action == "CONTINUE":
        for ins in lines:
            if "line_number" not in ins or "intent" not in ins:
                raise ValueError(f"CONTINUE needs line_number + intent: {ins}")

            ln = int(ins["line_number"])
            intent = str(ins["intent"]).upper()
            line = _find_line(state, ln)

            if intent == "ACCEPT_MODIFY":
                if (line.adjudication_status or "").lower() != "modified":
                    raise ValueError("ACCEPT_MODIFY requires current adjudication_status == modified")
                line.accepted_modification = True
                deltas.append({"kind": "phase3_accept_modify", "line_number": ln})
                continue

            deltas.append({"kind": "phase3_provider_continue", "line_number": ln, "intent": intent})

        return deltas, False, None

    if action == "APPEAL":
        for ins in lines:
            if "line_number" not in ins or "to_level" not in ins:
                raise ValueError(f"APPEAL needs line_number + to_level: {ins}")

            ln = int(ins["line_number"])
            to_level = int(ins["to_level"])
            if to_level not in (1, 2):
                raise ValueError(f"to_level must be 1 or 2, got {to_level}")

            line = _find_line(state, ln)
            status = (line.adjudication_status or "").lower()

            if status not in {"denied", "modified"}:
                raise ValueError(
                    f"line {ln} has adjudication_status={status}; only denied/modified can be appealed"
                )

            cur = int(line.current_review_level)
            if to_level != cur + 1:
                raise ValueError(f"appeal must advance by +1: line={ln} cur={cur} to={to_level}")

            line.current_review_level = to_level
            line.pend_round = 0
            deltas.append({"kind": "phase3_appeal_advanced", "line_number": ln, "from_level": cur, "to_level": to_level})

        return deltas, False, None

    raise ValueError(f"unknown provider bundle action: {action}")
