from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_core.messages.system import SystemMessage

from src.utils.json_parsing import extract_json_from_text


def _approx_tokens(text: str) -> int:
    """Cheap, deterministic proxy for 'how much was shown'."""
    return max(1, len(text.split()))


def summarize_draft_lines(draft_obj: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], Dict[int, Dict[str, Any]]]:
    """
    Build a line summary (all lines) and a line map (line_number -> full dict).
    Supports provider submission (insurer_request/requested_services) and payor response (line_adjudications).
    """
    if isinstance(draft_obj.get("insurer_request"), dict):
        req = draft_obj["insurer_request"]
        svcs = req.get("requested_services")
        svcs = svcs if isinstance(svcs, list) else []
        mode = "provider_submission"

        line_map: Dict[int, Dict[str, Any]] = {}
        summary: List[Dict[str, Any]] = []

        for svc in svcs:
            if not isinstance(svc, dict):
                continue
            ln = svc.get("line_number")
            if isinstance(ln, str) and ln.isdigit():
                ln = int(ln)
            if not isinstance(ln, int):
                raise ValueError(f"service line missing int line_number: {svc}")

            line_map[ln] = svc
            summary.append(
                {
                    "line_number": ln,
                    "request_type": svc.get("request_type"),
                    "procedure_code": svc.get("procedure_code"),
                    "code_type": svc.get("code_type"),
                    "service_name": svc.get("service_name"),
                    "service_description": svc.get("service_description"),
                    "site_of_service": svc.get("site_of_service"),
                    "charge_amount": svc.get("charge_amount"),
                    "requested_quantity": svc.get("requested_quantity"),
                }
            )

        return mode, summary, line_map

    if isinstance(draft_obj.get("line_adjudications"), list):
        adjs = draft_obj["line_adjudications"]
        mode = "payor_response"

        line_map: Dict[int, Dict[str, Any]] = {}
        summary: List[Dict[str, Any]] = []

        for adj in adjs:
            if not isinstance(adj, dict):
                continue
            ln = adj.get("line_number")
            if isinstance(ln, str) and ln.isdigit():
                ln = int(ln)
            if not isinstance(ln, int):
                raise ValueError(f"adjudication missing int line_number: {adj}")

            line_map[ln] = adj
            status = adj.get("authorization_status") or adj.get("adjudication_status")
            summary.append(
                {
                    "line_number": ln,
                    "status": status,
                    "decision_reason": adj.get("decision_reason"),
                    "requested_documents": adj.get("requested_documents"),
                    "approved_quantity": adj.get("approved_quantity"),
                    "modification_type": adj.get("modification_type"),
                }
            )

        return mode, summary, line_map

    # phase 3: claim_submission (provider) or claim_adjudication (payor)
    if isinstance(draft_obj.get("claim_submission"), dict):
        sub = draft_obj["claim_submission"]
        lines = sub.get("claim_lines") if isinstance(sub.get("claim_lines"), list) else []
        mode = "claim_submission"

        line_map: Dict[int, Dict[str, Any]] = {}
        summary: List[Dict[str, Any]] = []

        for ln_obj in lines:
            if not isinstance(ln_obj, dict):
                continue
            ln = ln_obj.get("line_number")
            if isinstance(ln, str) and ln.isdigit():
                ln = int(ln)
            if not isinstance(ln, int):
                continue
            line_map[ln] = ln_obj
            summary.append({
                "line_number": ln,
                "procedure_code": ln_obj.get("procedure_code"),
                "billed_amount": ln_obj.get("billed_amount"),
                "service_date": ln_obj.get("service_date"),
            })

        return mode, summary, line_map

    if isinstance(draft_obj.get("claim_adjudication"), dict):
        adj = draft_obj["claim_adjudication"]
        lines = adj.get("line_adjudications") if isinstance(adj.get("line_adjudications"), list) else []
        mode = "claim_adjudication"

        line_map: Dict[int, Dict[str, Any]] = {}
        summary: List[Dict[str, Any]] = []

        for ln_obj in lines:
            if not isinstance(ln_obj, dict):
                continue
            ln = ln_obj.get("line_number")
            if isinstance(ln, str) and ln.isdigit():
                ln = int(ln)
            if not isinstance(ln, int):
                continue
            line_map[ln] = ln_obj
            summary.append({
                "line_number": ln,
                "status": ln_obj.get("payment_status") or ln_obj.get("adjudication_status"),
                "allowed_amount": ln_obj.get("allowed_amount"),
                "paid_amount": ln_obj.get("paid_amount"),
            })

        return mode, summary, line_map

    raise ValueError("draft_obj not recognized: expected insurer_request, line_adjudications, claim_submission, or claim_adjudication")


def _invoke_messages(llm: Any, system_text: str, user_text: str) -> str:
    """Invoke via LangChain-style messages (works with CachedLLM too)."""
    resp = llm.invoke([SystemMessage(content=system_text), HumanMessage(content=user_text)])
    return getattr(resp, "content", "")


def choose_expand_lines_via_llm(
    *,
    llm: Any,
    role: str,
    line_summary: List[Dict[str, Any]],
    k: int,
) -> Tuple[List[int], Dict[str, Any]]:
    """
    Ask overseer to pick up to k line_numbers to expand.
    Strict: raises on invalid output; no fallback/guessing.
    """
    if k < 0:
        raise ValueError(f"review_expand_lines must be >= 0, got {k}")
    if k == 0:
        return [], {"selector_used": False, "reason": "k_zero"}

    if not isinstance(line_summary, list) or not line_summary:
        raise ValueError("cannot select expand lines: empty line_summary with k>0")

    valid = [row.get("line_number") for row in line_summary if isinstance(row.get("line_number"), int)]
    if not valid:
        raise ValueError("cannot select expand lines: no valid int line_number values")
    valid_set = set(valid)

    sys_txt = (
        f"You are the {role} overseer selecting which service lines to inspect in full detail.\n"
        "Return ONLY JSON with exactly one key: expand_lines.\n"
        "No extra text.\n"
    )

    user_txt = (
        "LINE SUMMARY (all lines):\n"
        f"{json.dumps(line_summary, ensure_ascii=False)}\n\n"
        f"Pick up to {k} line_numbers to expand.\n"
        f"Valid line_numbers: {sorted(valid)}\n\n"
        'STRICT RESPONSE (JSON ONLY):\n{"expand_lines":[1,2]}\n'
    )

    raw = _invoke_messages(llm, sys_txt, user_txt)
    obj = extract_json_from_text(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"selector output not JSON object: {raw}")

    exp = obj.get("expand_lines")
    if not isinstance(exp, list):
        raise ValueError(f"selector output missing expand_lines list: {obj}")

    picked: List[int] = []
    for x in exp:
        if isinstance(x, str) and x.isdigit():
            x = int(x)
        if isinstance(x, int) and x in valid_set and x not in picked:
            picked.append(x)
        if len(picked) >= k:
            break

    if not picked:
        raise ValueError(f"selector chose no valid lines: {obj}")

    meta: Dict[str, Any] = {
        "selector_used": True,
        "requested_k": k,
        "picked_lines": picked,
        "raw_selector_output": raw[:2000],
    }
    return picked, meta


def build_view_packet(
    *,
    mode: str,
    role: str,
    oversight_level: str,
    line_summary: List[Dict[str, Any]],
    line_map: Dict[int, Dict[str, Any]],
    expand_lines: List[int],
    evidence_packet: Optional[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """
    Build the view packet: summary for all lines + full dicts for expanded lines.
    No truncation; budget is enforced by expand_lines length upstream.
    """
    expanded: List[Dict[str, Any]] = []
    for ln in expand_lines:
        full = line_map.get(ln)
        if not isinstance(full, dict):
            raise ValueError(f"expand_lines includes unknown line_number: {ln}")
        expanded.append({"line_number": ln, "full": full})

    packet = {
        "role": role,
        "oversight_level": oversight_level,
        "draft_mode": mode,
        "line_summary_all": line_summary,
        "expanded_lines": expanded,
        "evidence_packet": evidence_packet or {},
        "instruction": "Return a JSON Patch array (RFC 6902) to correct the draft. If fine, return [].",
    }

    text = json.dumps(packet, ensure_ascii=False, indent=2)
    meta = {
        "draft_mode": mode,
        "expanded_line_numbers": expand_lines,
        "expanded_line_count": len(expand_lines),
        "view_packet_tokens_proxy": _approx_tokens(text),
        "view_packet_chars": len(text),
    }
    return text, meta
