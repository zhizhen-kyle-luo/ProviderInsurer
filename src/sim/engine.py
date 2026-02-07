"""
one phase interaction loop (provider↔insurer)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.sim.adapter_base import SimAdapter, Delta
from src.utils.audit_events import make_event
from src.utils.audit_logger import AuditLogger
from src.utils.prompts.config import MAX_TURNS_SAFETY_LIMIT


def _delta_to_event(state, delta: Delta):
    d = dict(delta)
    kind = str(d.pop("kind", "delta"))
    return make_event(phase=state.phase, turn=state.turn, kind=kind, payload=d)


def run(
    *,
    state,
    adapter: SimAdapter,
    audit_logger: Optional[AuditLogger] = None,
) -> Any:
    state.phase = adapter.phase_name
    state.turn = 0

    if audit_logger is not None:
        audit_logger.log(phase=state.phase, turn=state.turn, kind="phase_start", payload={})

    t = 0
    while t < MAX_TURNS_SAFETY_LIMIT:
        state.turn = t

        if adapter.is_terminal(state):
            break

        submission = adapter.build_submission(state)
        adapter.append_submission(state, submission)

        if audit_logger is not None:
            audit_logger.log(phase=state.phase, turn=state.turn, kind="submission_built", payload={"submission": submission})

        response = adapter.build_response(state, submission)
        adapter.append_response(state, response)

        if audit_logger is not None:
            audit_logger.log(phase=state.phase, turn=state.turn, kind="response_built", payload={"response": response})

        deltas1 = adapter.apply_response(state, response)

        if audit_logger is not None:
            for d in deltas1:
                audit_logger.add(_delta_to_event(state, d))

        # Check if terminal after applying response - skip provider action if nothing left to do
        if adapter.is_terminal(state):
            if audit_logger is not None:
                audit_logger.log(phase=state.phase, turn=state.turn, kind="phase_terminated", payload={"reason": "all_lines_terminal_after_response"})
            break

        provider_action = adapter.choose_provider_action(state, submission, response)

        # Store provider_action in the response for history tracking
        response["provider_action"] = provider_action

        if audit_logger is not None:
            audit_logger.log(phase=state.phase, turn=state.turn, kind="provider_action_chosen", payload={"provider_action": provider_action})

        deltas2, terminated, term_reason = adapter.apply_provider_action(state, provider_action)

        if audit_logger is not None:
            for d in deltas2:
                audit_logger.add(_delta_to_event(state, d))

        if terminated:
            if audit_logger is not None:
                audit_logger.log(phase=state.phase, turn=state.turn, kind="phase_terminated", payload={"reason": term_reason})
            break

        t += 1

    if audit_logger is not None:
        audit_logger.log(phase=state.phase, turn=state.turn, kind="phase_end", payload={})

    return state
