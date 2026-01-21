from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from src.utils.json_parsing import extract_json_from_text
from src.utils.prompts.config import OVERSIGHT_BUDGETS, OVERSIGHT_CONSTRAINTS, OVERSIGHT_GUIDANCE
from src.utils.oversight_patch import apply_json_patch, enforce_patch_budgets
from src.utils.oversight_review import build_view_packet, choose_expand_lines_via_llm, summarize_draft_lines


def _require_dict(obj: Any, msg: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(msg)
    return obj


def _invoke_langchain(llm, system_text: str, user_text: str) -> str:
    # same message pattern use in Phase2Adapter
    from langchain_core.messages import HumanMessage
    from langchain_core.messages.system import SystemMessage

    resp = llm.invoke([SystemMessage(content=system_text), HumanMessage(content=user_text)])
    return resp.content


def _system_prompt(role: str, oversight_level: str) -> str:
    guide = OVERSIGHT_GUIDANCE.get(oversight_level, {}).get("instruction", "")
    constraints = OVERSIGHT_CONSTRAINTS.get(role, "")
    return (
        f"You are the {role} overseer.\n"
        f"Oversight level: {oversight_level}. {guide}\n"
        f"{constraints}\n"
        "Return ONLY a JSON Patch array (RFC 6902). Example: [{\"op\":\"replace\",\"path\":\"/x\",\"value\":1}]\n"
        'Allowed ops: "add", "remove", "replace".\n'
        "Be concise. Keep string values short. No extra text.\n"
    )


def _user_prompt(view_packet_json: str, max_patch_ops: int, max_paths_touched: int) -> str:
    return (
        "VIEW PACKET:\n"
        f"{view_packet_json}\n\n"
        "TASK:\n"
        f"- Return JSON Patch array. Budgets: max_patch_ops={max_patch_ops}, max_paths_touched={max_paths_touched}\n"
        "- If no changes needed, return []\n"
        "- Keep values concise (max 100 chars per string value)\n"
    )


def apply_oversight_edit(
    *,
    role: str,
    oversight_level: str,
    draft_text: str,
    evidence_packet: Optional[Dict[str, Any]],
    llm,
    seed: Optional[int] = None,
) -> Tuple[str, Dict[str, Any], Optional[str], Optional[str]]:
    """
    Enforced oversight:
    - review effort: overseer expands <=K lines (chosen by LLM, clamped by code)
    - edit effort: JSON Patch ops + paths clamped by code
    Returns: revised_json_text, meta, error_code, error_msg
    """
    budgets = OVERSIGHT_BUDGETS.get(role, {}).get(oversight_level)
    if budgets is None:
        raise ValueError(f"unknown oversight budgets: role={role} level={oversight_level}")

    draft_obj = _require_dict(extract_json_from_text(draft_text), "expected draft JSON object")

    mode, line_summary, line_map = summarize_draft_lines(draft_obj)
    k = int(budgets["review_expand_lines"])

    expand_lines, selector_meta = choose_expand_lines_via_llm(
        llm=llm,
        role=role,
        line_summary=line_summary,
        k=k,
    )

    view_packet, view_meta = build_view_packet(
        mode=mode,
        role=role,
        oversight_level=oversight_level,
        line_map=line_map,
        expand_lines=expand_lines,
        evidence_packet=evidence_packet,
    )

    sys_txt = _system_prompt(role, oversight_level)
    user_txt = _user_prompt(
        view_packet_json=view_packet,
        max_patch_ops=int(budgets["max_patch_ops"]),
        max_paths_touched=int(budgets["max_paths_touched"]),
    )

    raw_patch_text = _invoke_langchain(llm, sys_txt, user_txt)

    meta: Dict[str, Any] = {
        "role": role,
        "oversight_level": oversight_level,
        "review": {"selector": selector_meta, "view": view_meta},
        "edit": {},
    }

    try:
        patch_obj = extract_json_from_text(raw_patch_text)
    except Exception as e:
        meta["edit"]["error"] = "patch_parse_failed"
        meta["edit"]["raw_patch_text"] = str(raw_patch_text)[:2000]
        meta["edit"]["exception"] = str(e)
        return json.dumps(draft_obj, ensure_ascii=False), meta, "patch_parse_failed", str(e)

    # handle single object instead of array
    if isinstance(patch_obj, dict):
        patch_obj = [patch_obj]

    if not isinstance(patch_obj, list):
        meta["edit"]["error"] = "patch_not_array"
        meta["edit"]["raw_patch_text"] = str(raw_patch_text)[:2000]
        return json.dumps(draft_obj, ensure_ascii=False), meta, "patch_not_array", "patch must be JSON array"

    patch_ops, budget_meta = enforce_patch_budgets(
        patch_obj,
        max_patch_ops=int(budgets["max_patch_ops"]),
        max_paths_touched=int(budgets["max_paths_touched"]),
    )

    try:
        revised_obj = apply_json_patch(draft_obj, patch_ops)
    except Exception as e:
        meta["edit"]["error"] = "patch_apply_failed"
        meta["edit"]["exception"] = str(e)
        meta["edit"]["budget"] = budget_meta
        meta["edit"]["patch_ops"] = patch_ops
        return json.dumps(draft_obj, ensure_ascii=False), meta, "patch_apply_failed", str(e)

    meta["edit"]["budget"] = budget_meta
    meta["edit"]["patch_ops"] = patch_ops
    meta["edit"]["raw_patch_text"] = str(raw_patch_text)[:2000]

    return json.dumps(revised_obj, ensure_ascii=False), meta, None, None
