from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.messages.system import SystemMessage

from src.utils.prompts.phase2_prompts import (
    create_phase2_payor_system_prompt,
    create_phase2_payor_user_prompt,
    create_phase2_provider_system_prompt,
    create_phase2_provider_user_prompt,
)
from src.sim.line_items import ensure_phase2_service_lines
from src.sim.transitions import apply_phase2_insurer_line_adjudications, apply_phase2_provider_bundle_action
from src.utils.json_parsing import extract_json_from_text

Delta = Dict[str, Any]


def _provider_params(state, adapter_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if adapter_params is not None:
        return adapter_params
    sp = getattr(state, "provider_params", None)
    if sp is None:
        return {}
    if not isinstance(sp, dict):
        raise ValueError(f"state.provider_params must be dict, got {type(sp)}")
    return sp


def _payor_params(state, adapter_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if adapter_params is not None:
        return adapter_params
    sp = getattr(state, "payor_params", None)
    if sp is None:
        return {}
    if not isinstance(sp, dict):
        raise ValueError(f"state.payor_params must be dict, got {type(sp)}")
    return sp


def _invoke(llm, system_text: str, user_text: str) -> str:
    resp = llm.invoke([SystemMessage(content=system_text), HumanMessage(content=user_text)])
    return resp.content


def _parse_obj(text: str) -> Dict[str, Any]:
    obj = extract_json_from_text(text)
    if not isinstance(obj, dict):
        raise ValueError("expected JSON object")
    return obj


def _pvd_dict(state) -> Dict[str, Any]:
    pv = getattr(state, "patient_visible_data", None)
    if pv is None:
        raise ValueError("state.patient_visible_data is None")
    if isinstance(pv, dict):
        return pv
    if hasattr(pv, "model_dump"):
        return pv.model_dump()
    raise ValueError(f"state.patient_visible_data must be dict or have model_dump(), got {type(pv)}")


def _current_level(state) -> int:
    lines = state.service_lines
    if lines is None:
        raise ValueError("state.service_lines is None")
    if not lines:
        return 0  # No lines yet means we're at initial level
    return max(int(l.current_review_level) for l in lines)


def _pend_count_at_level(state, level: int) -> int:
    n = 0
    responses = state.phase2_responses
    if responses is None:
        return 0  # No responses yet means no pends
    for resp in responses:
        if not isinstance(resp, dict):
            raise ValueError(f"phase2_responses entry must be dict, got {type(resp)}")
        resp_level = resp.get("level")
        if resp_level is None:
            raise ValueError(f"phase2_responses entry missing level: {resp}")
        if int(resp_level) != level:
            continue
        pay = resp.get("payor_response")
        if not isinstance(pay, dict):
            raise ValueError(f"phase2_responses entry missing payor_response dict: {resp}")
        line_adjs = pay.get("line_adjudications")
        if not isinstance(line_adjs, list):
            raise ValueError(f"payor_response missing line_adjudications list: {pay}")
        for adj in line_adjs:
            if not isinstance(adj, dict):
                raise ValueError(f"line_adjudications entry must be dict, got {type(adj)}")
            st = adj.get("authorization_status")
            if st is None:
                raise ValueError(f"line_adjudications entry missing authorization_status: {adj}")
            if str(st).lower() == "pending_info":
                n += 1
                break
    return n


def _payor_encounter_history(state) -> List[Dict[str, Any]]:
    """
    Build encounter history for payor LLM context.
    Payor sees what was previously submitted and how they responded.
    This enables realistic adjudication that accounts for prior interactions.
    """
    history: List[Dict[str, Any]] = []
    submissions = state.phase2_submissions if state.phase2_submissions is not None else []
    responses = state.phase2_responses if state.phase2_responses is not None else []

    for sub, resp in zip(submissions, responses):
        if not isinstance(sub, dict):
            raise ValueError(f"phase2_submissions entry must be dict, got {type(sub)}")
        if not isinstance(resp, dict):
            raise ValueError(f"phase2_responses entry must be dict, got {type(resp)}")

        lvl = sub.get("level")
        if lvl is None:
            lvl = resp.get("level")
        if lvl is None:
            raise ValueError(f"neither submission nor response has level: sub={sub}, resp={resp}")
        lvl = int(lvl)

        # What provider submitted
        insurer_req = sub.get("insurer_request")
        if insurer_req is None:
            raise ValueError(f"phase2_submission missing insurer_request: {sub}")
        if not isinstance(insurer_req, dict):
            raise ValueError(f"insurer_request must be dict, got {type(insurer_req)}")

        submitted_services = []
        requested_services = insurer_req.get("requested_services")
        if requested_services is None:
            raise ValueError(f"insurer_request missing requested_services: {insurer_req}")
        if not isinstance(requested_services, list):
            raise ValueError(f"requested_services must be list, got {type(requested_services)}")
        for svc in requested_services:
            if not isinstance(svc, dict):
                raise ValueError(f"requested_services entry must be dict, got {type(svc)}")
            clinical_evidence = svc.get("clinical_evidence", "")
            submitted_services.append({
                "line_number": svc.get("line_number"),
                "procedure_code": svc.get("procedure_code"),
                "service_name": svc.get("service_name"),
                "clinical_evidence": clinical_evidence[:200] if clinical_evidence else "",
            })

        # How payor responded
        pay = resp.get("payor_response")
        if pay is None:
            raise ValueError(f"phase2_response missing payor_response: {resp}")
        if not isinstance(pay, dict):
            raise ValueError(f"payor_response must be dict, got {type(pay)}")

        line_adjs = pay.get("line_adjudications")
        if line_adjs is None:
            raise ValueError(f"payor_response missing line_adjudications: {pay}")
        if not isinstance(line_adjs, list):
            raise ValueError(f"line_adjudications must be list, got {type(line_adjs)}")

        my_decisions = []
        for adj in line_adjs:
            if not isinstance(adj, dict):
                raise ValueError(f"line_adjudications entry must be dict, got {type(adj)}")
            my_decisions.append({
                "line_number": adj.get("line_number"),
                "status": adj.get("authorization_status"),
                "decision_reason": adj.get("decision_reason"),
                "requested_documents": adj.get("requested_documents"),
            })

        history.append({
            "round": len(history) + 1,
            "level": lvl,
            "provider_submission": submitted_services,
            "my_prior_decision": my_decisions,
        })

    return history


def _prior_round_summaries(state) -> List[Dict[str, Any]]:
    """
    Build detailed summaries of prior rounds for provider LLM context.
    Includes service line details so provider remembers what was requested and why it was denied/pended.
    """
    summaries: List[Dict[str, Any]] = []
    submissions = state.phase2_submissions if state.phase2_submissions is not None else []
    responses = state.phase2_responses if state.phase2_responses is not None else []

    for sub, resp in zip(submissions, responses):
        if not isinstance(sub, dict):
            raise ValueError(f"phase2_submissions entry must be dict, got {type(sub)}")
        if not isinstance(resp, dict):
            raise ValueError(f"phase2_responses entry must be dict, got {type(resp)}")

        lvl = sub.get("level")
        if lvl is None:
            lvl = resp.get("level")
        if lvl is None:
            raise ValueError(f"neither submission nor response has level: sub={sub}, resp={resp}")
        lvl = int(lvl)

        # Extract what was requested
        insurer_req = sub.get("insurer_request")
        if insurer_req is None:
            raise ValueError(f"phase2_submission missing insurer_request: {sub}")
        if not isinstance(insurer_req, dict):
            raise ValueError(f"insurer_request must be dict, got {type(insurer_req)}")

        req_svcs = insurer_req.get("requested_services")
        if req_svcs is None:
            raise ValueError(f"insurer_request missing requested_services: {insurer_req}")
        if not isinstance(req_svcs, list):
            raise ValueError(f"requested_services must be list, got {type(req_svcs)}")

        requested_services = []
        for svc in req_svcs:
            if not isinstance(svc, dict):
                raise ValueError(f"requested_services entry must be dict, got {type(svc)}")
            requested_services.append({
                "line_number": svc.get("line_number"),
                "procedure_code": svc.get("procedure_code"),
                "service_name": svc.get("service_name"),
                "code_type": svc.get("code_type"),
            })

        # Extract payor response details
        pay = resp.get("payor_response")
        if pay is None:
            raise ValueError(f"phase2_response missing payor_response: {resp}")
        if not isinstance(pay, dict):
            raise ValueError(f"payor_response must be dict, got {type(pay)}")

        line_adjs = pay.get("line_adjudications")
        if line_adjs is None:
            raise ValueError(f"payor_response missing line_adjudications: {pay}")
        if not isinstance(line_adjs, list):
            raise ValueError(f"line_adjudications must be list, got {type(line_adjs)}")

        line_outcomes = []
        for adj in line_adjs:
            if not isinstance(adj, dict):
                raise ValueError(f"line_adjudications entry must be dict, got {type(adj)}")
            status = adj.get("authorization_status")
            if status is None:
                raise ValueError(f"line_adjudications entry missing authorization_status: {adj}")
            line_outcomes.append({
                "line_number": adj.get("line_number"),
                "status": status,
                "decision_reason": adj.get("decision_reason"),
                "requested_documents": adj.get("requested_documents"),
                "modification_type": adj.get("modification_type"),
            })

        summaries.append({
            "level": lvl,
            "requested_services": requested_services,
            "line_outcomes": line_outcomes,
        })

    return summaries


class Phase2Adapter:
    phase_name = "phase_2_utilization_review"

    def __init__(
        self,
        *,
        provider_llm,
        payor_llm,
        provider_params: Optional[Dict[str, Any]] = None,
        payor_params: Optional[Dict[str, Any]] = None,
        environment=None,
        audit_logger=None,
    ):
        self.provider_llm = provider_llm
        self.payor_llm = payor_llm
        self.provider_params = provider_params
        self.payor_params = payor_params
        self.environment = environment
        self.audit_logger = audit_logger

        if self.environment is not None and getattr(self.environment, "audit_logger", None) is None:
            try:
                self.environment.audit_logger = audit_logger
            except Exception:
                pass

    def is_terminal(self, state) -> bool:
        from src.sim.transitions import _all_lines_terminal_phase2
        return _all_lines_terminal_phase2(state)

    def append_submission(self, state, submission: Dict[str, Any]) -> None:
        if not hasattr(state, "phase2_submissions"):
            state.phase2_submissions = []
        state.phase2_submissions.append(submission)

    def append_response(self, state, response: Dict[str, Any]) -> None:
        if not hasattr(state, "phase2_responses"):
            state.phase2_responses = []
        state.phase2_responses.append(response)

    def build_submission(self, state) -> Dict[str, Any]:
        level = _current_level(state)
        prior_rounds = _prior_round_summaries(state)

        params = _provider_params(state, self.provider_params)
        sys_txt = create_phase2_provider_system_prompt(params)
        user_txt = create_phase2_provider_user_prompt(
            state, turn=state.turn, level=level, prior_rounds=prior_rounds
        )

        draft = _invoke(self.provider_llm, sys_txt, user_txt)
        parsed = _parse_obj(draft)

        insurer_req = parsed.get("insurer_request")
        if not isinstance(insurer_req, dict):
            raise ValueError("provider output missing insurer_request dict")

        ensure_phase2_service_lines(state, insurer_req)

        prompts = {"system_prompt": sys_txt, "user_prompt": user_txt}
        pv = _pvd_dict(state)
        context = {
            "patient_visible_data": pv,
            "service_lines_state": [
                {
                    "line_number": l.line_number,
                    "procedure_code": l.procedure_code,
                    "authorization_status": l.authorization_status,
                    "current_review_level": l.current_review_level,
                    "requested_documents": list(l.requested_documents) if l.requested_documents else [],
                }
                for l in state.service_lines
            ],
        }

        return {
            "insurer_request": insurer_req,
            "raw": draft,
            "level": level,
            "prompts": prompts,
            "context": context,
        }

    def build_response(self, state, submission: Dict[str, Any]) -> Dict[str, Any]:
        insurer_req = submission["insurer_request"]
        level = int(submission.get("level", 0))
        pend_count = _pend_count_at_level(state, level)
        encounter_history = _payor_encounter_history(state)

        params = _payor_params(state, self.payor_params)
        sys_txt = create_phase2_payor_system_prompt(params)
        user_txt = create_phase2_payor_user_prompt(
            state, insurer_req, turn=state.turn, level=level,
            pend_count_at_level=pend_count, encounter_history=encounter_history
        )

        draft = _invoke(self.payor_llm, sys_txt, user_txt)
        parsed = _parse_obj(draft)

        if not isinstance(parsed.get("line_adjudications"), list):
            raise ValueError("payor output missing line_adjudications list")

        prompts = {"system_prompt": sys_txt, "user_prompt": user_txt}
        pv = _pvd_dict(state)
        context = {
            "patient_summary": {
                "age": pv.get("age"),
                "sex": pv.get("sex"),
                "chief_complaint": pv.get("chief_complaint"),
            },
            "submission_received": insurer_req,
        }

        return {
            "payor_response": parsed,
            "raw": draft,
            "level": level,
            "prompts": prompts,
            "context": context,
        }

    def apply_response(self, state, response: Dict[str, Any]) -> List[Delta]:
        pay = response["payor_response"]
        level = int(response.get("level", 0))
        mapped: List[Dict[str, Any]] = []

        for adj in pay["line_adjudications"]:
            if not isinstance(adj, dict):
                raise ValueError("line_adjudications entries must be dict")
            if "line_number" not in adj:
                raise ValueError(f"bad line adjudication: {adj}")

            status = adj.get("authorization_status")
            if status is None:
                status = adj.get("adjudication_status")
            if status is None:
                raise ValueError(f"bad line adjudication (missing authorization_status): {adj}")

            if level >= 2 and str(status).lower() == "pending_info":
                raise ValueError(f"pending_info not allowed at level {level} (IRE/final review)")

            mapped.append(
                {
                    "line_number": int(adj["line_number"]),
                    "authorization_status": str(status).lower(),
                    "decision_reason": adj.get("decision_reason"),
                    "approved_quantity": adj.get("approved_quantity"),
                    "authorization_number": adj.get("authorization_number"),
                    "modification_type": adj.get("modification_type"),
                    "requested_documents": adj.get("requested_documents"),
                }
            )

        deltas = apply_phase2_insurer_line_adjudications(
            state=state,
            line_adjudications=mapped,
            reviewer_type=str(pay.get("reviewer_type") or ""),
        )

        if self.environment is not None:
            try:
                deltas.extend(self.environment.perform_approved_diagnostics(state=state))
            except Exception as e:
                if self.audit_logger is not None:
                    try:
                        self.audit_logger.log(
                            phase="phase_2_utilization_review",
                            turn=int(getattr(state, "turn", 0)),
                            kind="env_error",
                            actor="environment",
                            payload={"error": str(e)},
                        )
                    except Exception:
                        pass
                raise

        return deltas

    def choose_provider_action(self, state, _submission: Dict[str, Any], _response: Dict[str, Any]) -> Dict[str, Any]:
        """
        LLM-based provider action decision.
        Provider sees payor response and decides per-line actions or RESUBMIT.
        Note: _submission and _response kept for API compatibility.
        """
        from src.utils.prompts.schema_definitions import PROVIDER_ACTION_SCHEMA, PROVIDER_ACTION_JSON

        lines = state.service_lines
        if lines is None:
            raise ValueError("state.service_lines is None")
        level = _current_level(state)

        # Build line status summary for LLM - include valid actions per line
        line_statuses = []
        for l in lines:
            if l.authorization_status is None:
                raise ValueError(f"line {l.line_number} has no authorization_status")
            status = str(l.authorization_status).lower()
            line_level = int(l.current_review_level)
            valid_actions = []
            if status == "approved":
                valid_actions = ["(no action needed - already terminal)"]
            elif status == "modified":
                if line_level >= 2:
                    valid_actions = ["ACCEPT_MODIFY", "ABANDON (mode required)"]
                else:
                    valid_actions = ["ACCEPT_MODIFY", "APPEAL (to_level required)", "ABANDON (mode required)"]
            elif status == "pending_info":
                valid_actions = ["PROVIDE_DOCS", "ABANDON (mode required)"]
            elif status == "denied":
                if line_level >= 2:
                    valid_actions = ["ABANDON (mode required) - level 2 is final, cannot appeal further"]
                else:
                    valid_actions = ["APPEAL (to_level required)", "ABANDON (mode required)"]

            line_statuses.append({
                "line_number": l.line_number,
                "procedure_code": l.procedure_code,
                "service_name": l.service_name,
                "authorization_status": l.authorization_status,
                "decision_reason": l.decision_reason,
                "current_review_level": l.current_review_level,
                "requested_documents": list(l.requested_documents) if l.requested_documents else [],
                "modification_type": l.modification_type,
                "approved_quantity": l.approved_quantity,
                "requested_quantity": l.requested_quantity,
                "valid_actions": valid_actions,
            })

        params = _provider_params(state, self.provider_params)
        strategy = params.get("strategy", "")
        strategy_block = ""
        if strategy:
            from src.utils.prompts.config import PROVIDER_STRATEGY_GUIDANCE
            if strategy in PROVIDER_STRATEGY_GUIDANCE:
                strategy_block = f"\nSTRATEGY GUIDANCE:\n{PROVIDER_STRATEGY_GUIDANCE[strategy]}\n"

        system_prompt = (
            "PHASE 2 PROVIDER ACTION DECISION\n"
            "You are a hospital provider team deciding how to respond to the insurer's authorization decision.\n"
            f"{strategy_block}"
            f"{PROVIDER_ACTION_SCHEMA}\n"
            "Respond only with valid JSON matching the schema."
        )

        import json
        user_prompt = (
            f"Current Review Level: {level}\n"
            f"Max Appeal Level: 2 (IRE - final)\n\n"
            "CURRENT LINE STATUSES AFTER PAYOR RESPONSE:\n"
            f"{json.dumps(line_statuses, indent=2)}\n\n"
            "DECISION:\n"
            "Choose ONE of:\n\n"
            "1. RESUBMIT (bundle-level) - if YOUR submission had errors causing denials\n"
            "   Withdraws entire PA, starts fresh at level 0\n\n"
            "2. LINE_ACTIONS (per-line) - specify action for each non-approved line:\n"
            "   - approved lines: omit (already terminal)\n"
            "   - modified lines: ACCEPT_MODIFY | APPEAL | ABANDON\n"
            "   - pending_info lines: PROVIDE_DOCS | ABANDON\n"
            "   - denied lines: APPEAL | ABANDON\n\n"
            "ABANDON modes: NO_TREAT (patient doesn't get service) or TREAT_ANYWAY (deliver, absorb cost)\n"
            "APPEAL requires to_level (must be current_level + 1, max 2)\n\n"
            f"Return only valid JSON:\n{PROVIDER_ACTION_JSON}"
        )

        raw = _invoke(self.provider_llm, system_prompt, user_prompt)
        parsed = _parse_obj(raw)

        if self.audit_logger:
            self.audit_logger.log(
                phase="phase_2_utilization_review",
                turn=int(getattr(state, "turn", 0)),
                kind="provider_action_llm_call",
                payload={
                    "prompts": {"system_prompt": system_prompt, "user_prompt": user_prompt},
                    "raw_response": raw,
                    "parsed": parsed,
                },
            )

        return parsed

    def apply_provider_action(self, state, provider_action: Dict[str, Any]) -> Tuple[List[Delta], bool, Optional[str]]:
        return apply_phase2_provider_bundle_action(state=state, provider_action=provider_action)
