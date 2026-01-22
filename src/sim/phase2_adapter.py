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
from src.utils.oversight import apply_oversight_edit

Delta = Dict[str, Any]


def _provider_params(state, adapter_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if adapter_params is not None:
        return adapter_params
    sp = getattr(state, "provider_params", None)
    return sp if isinstance(sp, dict) else {}


def _payor_params(state, adapter_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if adapter_params is not None:
        return adapter_params
    sp = getattr(state, "payor_params", None)
    return sp if isinstance(sp, dict) else {}


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
        return {}
    if isinstance(pv, dict):
        return pv
    if hasattr(pv, "model_dump"):
        return pv.model_dump()
    return {}


def _current_level(state) -> int:
    lines = getattr(state, "service_lines", []) or []
    if not lines:
        return 0
    return max(int(getattr(l, "current_review_level", 0)) for l in lines)


def _pend_count_at_level(state, level: int) -> int:
    n = 0
    for resp in getattr(state, "phase2_responses", []) or []:
        if not isinstance(resp, dict) or int(resp.get("level", -1)) != level:
            continue
        pay = resp.get("payor_response")
        if not isinstance(pay, dict):
            continue
        line_adjs = pay.get("line_adjudications")
        if not isinstance(line_adjs, list):
            continue
        for adj in line_adjs:
            if not isinstance(adj, dict):
                continue
            st = (adj.get("authorization_status") or adj.get("adjudication_status") or "").lower()
            if st == "pending_info":
                n += 1
                break
    return n


def _prior_round_summaries(state) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    submissions = getattr(state, "phase2_submissions", []) or []
    responses = getattr(state, "phase2_responses", []) or []
    for sub, resp in zip(submissions, responses):
        if not isinstance(sub, dict) or not isinstance(resp, dict):
            continue
        lvl = int(sub.get("level", resp.get("level", 0)) or 0)
        pay = resp.get("payor_response") if isinstance(resp.get("payor_response"), dict) else {}
        line_adjs = pay.get("line_adjudications") if isinstance(pay, dict) else None
        payor_decision = ""
        if isinstance(line_adjs, list) and line_adjs and isinstance(line_adjs[0], dict):
            payor_decision = str(
                line_adjs[0].get("authorization_status") or line_adjs[0].get("adjudication_status") or ""
            )
        summaries.append(
            {
                "level": lvl,
                "payor_decision": payor_decision,
                "payor_decision_reason": str(pay.get("decision_reason") or ""),
            }
        )
    return summaries


class Phase2Adapter:
    phase_name = "phase_2_utilization_review"

    def __init__(
        self,
        *,
        provider_copilot_llm,
        payor_copilot_llm,
        provider_base_llm=None,
        payor_base_llm=None,
        provider_params: Optional[Dict[str, Any]] = None,
        payor_params: Optional[Dict[str, Any]] = None,
        environment=None,
        audit_logger=None,
    ):
        self.provider_copilot = provider_copilot_llm
        self.payor_copilot = payor_copilot_llm
        self.provider_base = provider_base_llm or provider_copilot_llm
        self.payor_base = payor_base_llm or payor_copilot_llm
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
        lines = getattr(state, "service_lines", []) or []
        if not lines:
            return False
        for l in lines:
            st = (l.authorization_status or "").lower()
            if st in {"approved"}:
                continue
            if st == "modified" and getattr(l, "accepted_modification", False):
                continue
            if st in {"denied", "modified"} and int(l.current_review_level) >= 2:
                continue
            return False
        return True

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
            state, turn=state.turn + 1, level=level, prior_rounds=prior_rounds
        )

        draft = _invoke(self.provider_copilot, sys_txt, user_txt)
        parsed = _parse_obj(draft)

        insurer_req = parsed.get("insurer_request")
        if not isinstance(insurer_req, dict):
            raise ValueError("provider output missing insurer_request dict")

        ensure_phase2_service_lines(state, insurer_req)

        if params.get("oversight_intensity") and self.provider_base is not None:
            ov = str(params["oversight_intensity"])
            pv = _pvd_dict(state)
            revised, meta, _, _ = apply_oversight_edit(
                role="provider",
                oversight_level=ov,
                draft_text=draft,
                evidence_packet={"vitals": pv.get("vital_signs", {}), "labs": pv.get("lab_results", {})},
                llm=self.provider_base,
            )
            try:
                parsed2 = _parse_obj(revised)
                if isinstance(parsed2.get("insurer_request"), dict):
                    parsed = parsed2
                    insurer_req = parsed["insurer_request"]
            except Exception:
                pass
            submission = {"insurer_request": insurer_req, "raw": draft, "oversight": meta, "level": level}
        else:
            submission = {"insurer_request": insurer_req, "raw": draft, "oversight": None, "level": level}

        return submission

    def build_response(self, state, submission: Dict[str, Any]) -> Dict[str, Any]:
        insurer_req = submission["insurer_request"]
        level = int(submission.get("level", 0))
        pend_count = _pend_count_at_level(state, level)

        params = _payor_params(state, self.payor_params)
        sys_txt = create_phase2_payor_system_prompt(params)
        user_txt = create_phase2_payor_user_prompt(
            state, insurer_req, turn=state.turn + 1, level=level, pend_count_at_level=pend_count
        )

        draft = _invoke(self.payor_copilot, sys_txt, user_txt)
        parsed = _parse_obj(draft)

        if not isinstance(parsed.get("line_adjudications"), list):
            raise ValueError("payor output missing line_adjudications list")

        if params.get("oversight_intensity") and self.payor_base is not None:
            ov = str(params["oversight_intensity"])
            pv = _pvd_dict(state)
            revised, meta, _, _ = apply_oversight_edit(
                role="payor",
                oversight_level=ov,
                draft_text=draft,
                evidence_packet={"vitals": pv.get("vital_signs", {}), "labs": pv.get("lab_results", {})},
                llm=self.payor_base,
            )
            try:
                parsed2 = _parse_obj(revised)
                if isinstance(parsed2.get("line_adjudications"), list):
                    parsed = parsed2
            except Exception:
                pass
            return {"payor_response": parsed, "raw": draft, "oversight": meta, "level": level}

        return {"payor_response": parsed, "raw": draft, "oversight": None, "level": level}

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

    def choose_provider_action(self, state, submission: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        lines = getattr(state, "service_lines", []) or []
        appeal = []
        accept_modify = []
        pending = []
        terminal_bad = []

        for l in lines:
            st = (l.authorization_status or "").lower()
            if st == "pending_info":
                pending.append(l)
            elif st == "modified" and int(l.current_review_level) < 2:
                mod_type = (l.modification_type or "").lower()
                if mod_type == "quantity_reduction" and l.approved_quantity and l.approved_quantity >= (l.requested_quantity or 0) * 0.5:
                    accept_modify.append(l)
                else:
                    appeal.append(l)
            elif st == "denied" and int(l.current_review_level) < 2:
                appeal.append(l)
            elif st in {"denied", "modified"} and int(l.current_review_level) >= 2:
                terminal_bad.append(l)

        if appeal:
            return {
                "action": "APPEAL",
                "lines": [{"line_number": l.line_number, "to_level": l.current_review_level + 1} for l in appeal],
            }

        if accept_modify:
            return {
                "action": "CONTINUE",
                "lines": [{"line_number": l.line_number, "intent": "ACCEPT_MODIFY"} for l in accept_modify],
            }

        if pending:
            return {
                "action": "CONTINUE",
                "lines": [{"line_number": l.line_number, "intent": "PROVIDE_REQUESTED_DOCS"} for l in pending],
            }

        if terminal_bad:
            return {"action": "ABANDON", "abandon_mode": "NO_TREAT", "treat_anyway_lines": [], "lines": []}

        return {"action": "CONTINUE", "lines": []}

    def apply_provider_action(self, state, provider_action: Dict[str, Any]) -> Tuple[List[Delta], bool, Optional[str]]:
        return apply_phase2_provider_bundle_action(state=state, provider_action=provider_action)
