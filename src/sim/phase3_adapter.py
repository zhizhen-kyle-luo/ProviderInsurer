from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.messages.system import SystemMessage

from src.utils.prompts.phase3_prompts import (
    create_phase3_payor_system_prompt,
    create_phase3_payor_user_prompt,
    create_phase3_provider_system_prompt,
    create_phase3_provider_user_prompt,
)
from src.sim.transitions import apply_phase3_insurer_line_adjudications, apply_phase3_provider_bundle_action
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
    for resp in getattr(state, "phase3_responses", []) or []:
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
            st = (adj.get("adjudication_status") or "").lower()
            if st == "pending_info":
                n += 1
                break
    return n


def _prior_round_summaries(state) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    submissions = getattr(state, "phase3_submissions", []) or []
    responses = getattr(state, "phase3_responses", []) or []
    for sub, resp in zip(submissions, responses):
        if not isinstance(sub, dict) or not isinstance(resp, dict):
            continue
        lvl = int(sub.get("level", resp.get("level", 0)) or 0)
        pay = resp.get("payor_response") if isinstance(resp.get("payor_response"), dict) else {}
        line_adjs = pay.get("line_adjudications") if isinstance(pay, dict) else None
        # summarize all line statuses
        line_status_counts: Dict[str, int] = {}
        if isinstance(line_adjs, list):
            for adj in line_adjs:
                if isinstance(adj, dict):
                    st = str(adj.get("adjudication_status") or "unknown")
                    line_status_counts[st] = line_status_counts.get(st, 0) + 1
        payor_decision = ", ".join(f"{k}:{v}" for k, v in line_status_counts.items()) if line_status_counts else ""
        summaries.append(
            {
                "level": lvl,
                "payor_decision": payor_decision,
                "payor_decision_reason": str(pay.get("decision_reason") or ""),
            }
        )
    return summaries


class Phase3Adapter:
    phase_name = "phase_3_claims"

    def __init__(
        self,
        *,
        provider_copilot_llm,
        payor_copilot_llm,
        provider_base_llm=None,
        payor_base_llm=None,
        provider_params: Optional[Dict[str, Any]] = None,
        payor_params: Optional[Dict[str, Any]] = None,
        audit_logger=None,
    ):
        self.provider_copilot = provider_copilot_llm
        self.payor_copilot = payor_copilot_llm
        self.provider_base = provider_base_llm or provider_copilot_llm
        self.payor_base = payor_base_llm or payor_copilot_llm
        self.provider_params = provider_params
        self.payor_params = payor_params
        self.audit_logger = audit_logger

    def is_terminal(self, state) -> bool:
        lines = getattr(state, "service_lines", []) or []
        if not lines:
            return True

        for l in lines:
            if not getattr(l, "delivered", False):
                continue

            st = (l.adjudication_status or "").lower()
            if st in {"approved"}:
                continue
            if st in {"denied", "modified"} and int(l.current_review_level) >= 2:
                continue
            return False
        return True

    def append_submission(self, state, submission: Dict[str, Any]) -> None:
        if not hasattr(state, "phase3_submissions"):
            state.phase3_submissions = []
        state.phase3_submissions.append(submission)

    def append_response(self, state, response: Dict[str, Any]) -> None:
        if not hasattr(state, "phase3_responses"):
            state.phase3_responses = []
        state.phase3_responses.append(response)

    def build_submission(self, state) -> Dict[str, Any]:
        level = _current_level(state)
        prior_rounds = _prior_round_summaries(state)

        params = _provider_params(state, self.provider_params)
        sys_txt = create_phase3_provider_system_prompt(params)
        user_txt = create_phase3_provider_user_prompt(
            state, turn=state.turn + 1, level=level, prior_rounds=prior_rounds
        )

        draft = _invoke(self.provider_copilot, sys_txt, user_txt)
        parsed = _parse_obj(draft)

        claim_submission = parsed.get("claim_submission")
        if not isinstance(claim_submission, dict):
            raise ValueError("provider output missing claim_submission dict")

        prompts = {"system_prompt": sys_txt, "user_prompt": user_txt}

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
                if isinstance(parsed2.get("claim_submission"), dict):
                    parsed = parsed2
                    claim_submission = parsed["claim_submission"]
            except Exception:
                pass
            submission = {"claim_submission": claim_submission, "raw": draft, "oversight": meta, "level": level, "prompts": prompts}
        else:
            submission = {"claim_submission": claim_submission, "raw": draft, "oversight": None, "level": level, "prompts": prompts}

        return submission

    def build_response(self, state, submission: Dict[str, Any]) -> Dict[str, Any]:
        claim_submission = submission["claim_submission"]
        level = int(submission.get("level", 0))
        pend_count = _pend_count_at_level(state, level)

        params = _payor_params(state, self.payor_params)
        sys_txt = create_phase3_payor_system_prompt(params)
        user_txt = create_phase3_payor_user_prompt(
            state, claim_submission, turn=state.turn + 1, level=level, pend_count_at_level=pend_count
        )

        draft = _invoke(self.payor_copilot, sys_txt, user_txt)
        parsed = _parse_obj(draft)

        if not isinstance(parsed.get("line_adjudications"), list):
            raise ValueError("payor output missing line_adjudications list")

        prompts = {"system_prompt": sys_txt, "user_prompt": user_txt}

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
            return {"payor_response": parsed, "raw": draft, "oversight": meta, "level": level, "prompts": prompts}

        return {"payor_response": parsed, "raw": draft, "oversight": None, "level": level, "prompts": prompts}

    def apply_response(self, state, response: Dict[str, Any]) -> List[Delta]:
        pay = response["payor_response"]
        level = int(response.get("level", 0))
        mapped: List[Dict[str, Any]] = []

        for adj in pay["line_adjudications"]:
            if not isinstance(adj, dict):
                raise ValueError("line_adjudications entries must be dict")
            if "line_number" not in adj:
                raise ValueError(f"bad line adjudication: {adj}")

            status = adj.get("adjudication_status")
            if status is None:
                raise ValueError(f"bad line adjudication (missing adjudication_status): {adj}")

            if level >= 2 and str(status).lower() == "pending_info":
                raise ValueError(f"pending_info not allowed at level {level} (IRE/final review)")

            mapped.append(
                {
                    "line_number": int(adj["line_number"]),
                    "adjudication_status": str(status).lower(),
                    "decision_reason": adj.get("decision_reason"),
                    "allowed_amount": adj.get("allowed_amount"),
                    "paid_amount": adj.get("paid_amount"),
                    "adjustment_group_code": adj.get("adjustment_group_code"),
                    "adjustment_amount": adj.get("adjustment_amount"),
                    "requested_documents": adj.get("requested_documents"),
                }
            )

        deltas = apply_phase3_insurer_line_adjudications(
            state=state,
            line_adjudications=mapped,
            reviewer_type=str(pay.get("reviewer_type") or ""),
        )

        return deltas

    def choose_provider_action(self, state, submission: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        lines = getattr(state, "service_lines", []) or []
        appeal = []
        pending = []
        terminal_bad = []

        for l in lines:
            if not getattr(l, "delivered", False):
                continue

            st = (l.adjudication_status or "").lower()
            if st == "pending_info":
                pending.append(l)
            if st in {"denied", "modified"} and int(l.current_review_level) < 2:
                appeal.append(l)
            if st in {"denied", "modified"} and int(l.current_review_level) >= 2:
                terminal_bad.append(l)

        if appeal:
            return {
                "action": "APPEAL",
                "lines": [{"line_number": l.line_number, "to_level": l.current_review_level + 1} for l in appeal],
            }

        if pending:
            return {
                "action": "CONTINUE",
                "lines": [{"line_number": l.line_number, "intent": "PROVIDE_REQUESTED_DOCS"} for l in pending],
            }

        if terminal_bad:
            return {"action": "ABANDON", "abandon_mode": "WRITE_OFF", "lines": []}

        return {"action": "CONTINUE", "lines": []}

    def apply_provider_action(self, state, provider_action: Dict[str, Any]) -> Tuple[List[Delta], bool, Optional[str]]:
        return apply_phase3_provider_bundle_action(state=state, provider_action=provider_action)
