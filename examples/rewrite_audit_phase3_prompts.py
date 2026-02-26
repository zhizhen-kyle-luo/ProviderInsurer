"""
Rewrite Phase 2 and Phase 3 system/user prompts in existing audit JSONs to the
current prompt version. Writes to a matching-name folder under outputs (e.g.
experiments_1 -> new_experiments_1). Run from MASH repo root.

usage:
  python examples/rewrite_audit_phase3_prompts.py outputs/experiments_1
  python examples/rewrite_audit_phase3_prompts.py outputs/experiments_1/*_audit.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.policies.infliximab_policies import InfliximabCrohnsPolicies
from src.utils.prompts.phase2_prompts import (
    create_phase2_provider_system_prompt,
    create_phase2_provider_user_prompt,
    create_phase2_payor_system_prompt,
    create_phase2_payor_user_prompt,
)
from src.utils.prompts.phase3_prompts import (
    create_phase3_provider_system_prompt,
    create_phase3_provider_user_prompt,
    create_phase3_payor_system_prompt,
    create_phase3_payor_user_prompt,
)
from src.utils.prompts.schema_definitions import PROVIDER_ACTION_SCHEMA, PROVIDER_ACTION_JSON
from src.utils.prompts.config import PROVIDER_STRATEGY_GUIDANCE
from src.sim.phase3_adapter import build_phase3_provider_action_prompts

CONFIGS = {
    "CP_CI": {"provider_strategy": "cooperate", "payor_strategy": "cooperate"},
    "CP_DI": {"provider_strategy": "cooperate", "payor_strategy": "defect"},
    "CP_NI": {"provider_strategy": "cooperate", "payor_strategy": "default"},
    "DP_CI": {"provider_strategy": "defect", "payor_strategy": "cooperate"},
    "DP_DI": {"provider_strategy": "defect", "payor_strategy": "defect"},
    "DP_NI": {"provider_strategy": "defect", "payor_strategy": "default"},
    "NP_CI": {"provider_strategy": "default", "payor_strategy": "cooperate"},
    "NP_DI": {"provider_strategy": "default", "payor_strategy": "defect"},
    "NP_NI": {"provider_strategy": "default", "payor_strategy": "default"},
}
PROVIDER_POLICY = InfliximabCrohnsPolicies.PROVIDER_GUIDELINES["aga_2021"]
PAYOR_POLICY = InfliximabCrohnsPolicies.PAYOR_POLICIES["cigna_ip0660_2026"]


def _parse_condition(run_id: str) -> str | None:
    for cond in CONFIGS:
        if f"_{cond}_" in run_id:
            return cond
    return None


# ── Phase 2 helpers ──────────────────────────────────────────────────────────

def _p2_prior_round_summaries(submissions, responses):
    summaries = []
    for sub, resp in zip(submissions, responses):
        lvl = int(sub.get("level", 0) or resp.get("level", 0))
        insurer_req = sub.get("insurer_request") or {}
        requested_services = [
            {"line_number": s.get("line_number"), "procedure_code": s.get("procedure_code"),
             "service_name": s.get("service_name"), "code_type": s.get("code_type")}
            for s in (insurer_req.get("requested_services") or []) if isinstance(s, dict)
        ]
        pay = resp.get("payor_response") or {}
        line_outcomes = [
            {"line_number": a.get("line_number"), "status": a.get("authorization_status"),
             "decision_reason": a.get("decision_reason"),
             "requested_documents": a.get("requested_documents"),
             "modification_type": a.get("modification_type")}
            for a in (pay.get("line_adjudications") or []) if isinstance(a, dict)
        ]
        summaries.append({"level": lvl, "requested_services": requested_services, "line_outcomes": line_outcomes})
    return summaries


def _p2_encounter_history(submissions, responses):
    history = []
    for sub, resp in zip(submissions, responses):
        lvl = int(sub.get("level", 0) or resp.get("level", 0))
        insurer_req = sub.get("insurer_request") or {}
        submitted = [
            {"line_number": s.get("line_number"), "procedure_code": s.get("procedure_code"),
             "service_name": s.get("service_name"),
             "clinical_evidence": (s.get("clinical_evidence") or "")[:200]}
            for s in (insurer_req.get("requested_services") or []) if isinstance(s, dict)
        ]
        pay = resp.get("payor_response") or {}
        decisions = [
            {"line_number": a.get("line_number"), "status": a.get("authorization_status"),
             "decision_reason": a.get("decision_reason"),
             "requested_documents": a.get("requested_documents")}
            for a in (pay.get("line_adjudications") or []) if isinstance(a, dict)
        ]
        history.append({"round": len(history) + 1, "level": lvl,
                        "provider_submission": submitted, "my_prior_decision": decisions})
    return history


def _p2_pend_count_at_level(responses, level):
    n = 0
    for resp in responses:
        if int(resp.get("level", -1)) != level:
            continue
        pay = resp.get("payor_response") or {}
        for adj in pay.get("line_adjudications") or []:
            if isinstance(adj, dict) and str(adj.get("authorization_status", "")).lower() == "pending_info":
                n += 1
                break
    return n


def _build_p2_action_system_prompt(strategy):
    guidance = PROVIDER_STRATEGY_GUIDANCE[strategy]
    strategy_block = f"\nSTRATEGY GUIDANCE:\n{guidance}\n" if guidance else ""
    return (
        "PHASE 2 PROVIDER ACTION DECISION\n"
        "You are a hospital provider team deciding how to respond to the insurer's authorization decision.\n"
        f"{strategy_block}"
        f"{PROVIDER_ACTION_SCHEMA}\n"
        "Respond only with valid JSON matching the schema."
    )


def _build_p2_action_user_prompt(level, line_statuses_json):
    """Rebuild user prompt with current template, preserving original line data."""
    return (
        f"Current Review Level: {level}\n"
        f"Max Appeal Level: 2 (IRE - final)\n\n"
        "CURRENT LINE STATUSES AFTER PAYOR RESPONSE:\n"
        f"{line_statuses_json}\n\n"
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


# ── Phase 3 helpers ──────────────────────────────────────────────────────────

def _p3_prior_round_summaries(submissions, responses):
    out = []
    for sub, resp in zip(submissions, responses):
        lvl = int(sub.get("level", 0) or resp.get("level", 0))
        claim_sub = sub.get("claim_submission") or {}
        billed = list(claim_sub.get("billed_lines") or [])
        billed_lines = [
            {"line_number": L.get("line_number"), "procedure_code": L.get("procedure_code"),
             "authorization_number": L.get("authorization_number")}
            for L in billed if isinstance(L, dict)
        ]
        pay = resp.get("payor_response") or {}
        adjs = list(pay.get("line_adjudications") or [])
        line_outcomes = [
            {"line_number": a.get("line_number"), "status": a.get("adjudication_status"),
             "decision_reason": a.get("decision_reason"),
             "requested_documents": a.get("requested_documents") or []}
            for a in adjs if isinstance(a, dict)
        ]
        out.append({"level": lvl, "billed_lines": billed_lines, "line_outcomes": line_outcomes})
    return out


def _p3_encounter_history(submissions, responses):
    out = []
    for i, (sub, resp) in enumerate(zip(submissions, responses)):
        lvl = int(sub.get("level", 0) or resp.get("level", 0))
        claim_sub = sub.get("claim_submission") or {}
        billed = list(claim_sub.get("billed_lines") or [])
        provider_billed = [
            {"line_number": L.get("line_number"), "procedure_code": L.get("procedure_code"),
             "authorization_number": L.get("authorization_number")}
            for L in billed if isinstance(L, dict)
        ]
        pay = resp.get("payor_response") or {}
        adjs = list(pay.get("line_adjudications") or [])
        my_decisions = [
            {"line_number": a.get("line_number"), "status": a.get("adjudication_status"),
             "decision_reason": a.get("decision_reason"),
             "requested_documents": a.get("requested_documents") or []}
            for a in adjs if isinstance(a, dict)
        ]
        out.append({"round": i + 1, "level": lvl, "provider_billed": provider_billed, "my_prior_decision": my_decisions})
    return out


def _p3_pend_count_at_level(responses, level):
    n = 0
    for resp in responses:
        if int(resp.get("level", -1)) != level:
            continue
        pay = resp.get("payor_response") or {}
        for adj in pay.get("line_adjudications") or []:
            if isinstance(adj, dict) and str(adj.get("adjudication_status", "")).lower() == "pending_info":
                n += 1
                break
    return n


# ── Main rewriter ────────────────────────────────────────────────────────────

def rewrite_one(path: str) -> tuple[bool, dict]:
    """Rewrite Phase 2 + Phase 3 prompts in memory. Returns (changed, data)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    run_id = data.get("run_id") or ""
    condition = _parse_condition(run_id)
    if not condition:
        print(f"  skip {path}: cannot parse condition from run_id={run_id}")
        return False, data
    config = CONFIGS[condition]
    provider_params = {"policy": PROVIDER_POLICY, "strategy": config["provider_strategy"]}
    payor_params = {"policy": PAYOR_POLICY, "strategy": config["payor_strategy"]}

    events = data.get("events") or []
    changed = 0

    # ── Phase 2 state tracking ───────────────────────────────────────────
    p2_submissions = []
    p2_responses = []
    p2_first_pv = None
    p2_line_meta = {}

    # ── Phase 3 state tracking ───────────────────────────────────────────
    p3_submissions = []
    p3_responses = []
    p3_first_pv = None
    p3_line_meta = {}
    p3_current_lines = []

    for ev in events:
        phase = ev.get("phase")
        kind = ev.get("kind")
        payload = ev.get("payload") or {}
        turn = int(ev.get("turn", 0))

        # ── PHASE 2 ─────────────────────────────────────────────────────
        if phase == "phase_2_utilization_review":
            if kind == "submission_built":
                sub = payload.get("submission") or {}
                ctx = sub.get("context") or {}
                pv = ctx.get("patient_visible_data") or {}
                if p2_first_pv is None:
                    p2_first_pv = pv
                lines_state = ctx.get("service_lines_state") or []
                for L in lines_state:
                    if isinstance(L, dict) and L.get("line_number") is not None:
                        p2_line_meta[L["line_number"]] = L

                state = SimpleNamespace()
                state.patient_visible_data = pv
                state.service_lines = [
                    SimpleNamespace(**{
                        "line_number": L.get("line_number"),
                        "procedure_code": L.get("procedure_code"),
                        "service_name": L.get("service_name", ""),
                        "authorization_status": L.get("authorization_status"),
                        "current_review_level": L.get("current_review_level", 0),
                        "requested_documents": L.get("requested_documents") or [],
                        "decision_reason": L.get("decision_reason"),
                        "requested_quantity": L.get("requested_quantity", 1),
                        "modification_type": L.get("modification_type"),
                        "approved_quantity": L.get("approved_quantity"),
                    })
                    for L in lines_state if isinstance(L, dict)
                ]
                state.phase2_submissions = list(p2_submissions)
                state.phase2_responses = list(p2_responses)
                level = int(sub.get("level", 0))
                prior_rounds = _p2_prior_round_summaries(p2_submissions, p2_responses)

                new_sys = create_phase2_provider_system_prompt(provider_params)
                new_user = create_phase2_provider_user_prompt(state, turn=turn, level=level, prior_rounds=prior_rounds)
                if sub.get("prompts"):
                    sub["prompts"]["system_prompt"] = new_sys
                    sub["prompts"]["user_prompt"] = new_user
                    changed += 1
                p2_submissions.append(sub)

            elif kind == "response_built":
                resp = payload.get("response") or {}
                ctx = resp.get("context") or {}
                pv_summary = ctx.get("patient_summary") or {}
                pv_full = (p2_first_pv or {}).copy()
                pv_full.update({k: v for k, v in pv_summary.items() if v is not None})
                state = SimpleNamespace()
                state.patient_visible_data = pv_full
                state.phase2_submissions = list(p2_submissions)
                state.phase2_responses = list(p2_responses)

                level = int(resp.get("level", 0))
                insurer_req = p2_submissions[-1].get("insurer_request", {}) if p2_submissions else {}
                pend_count = _p2_pend_count_at_level(p2_responses, level)
                encounter_history = _p2_encounter_history(p2_submissions, p2_responses)

                new_sys = create_phase2_payor_system_prompt(payor_params)
                new_user = create_phase2_payor_user_prompt(
                    state, insurer_req, turn=turn, level=level,
                    pend_count_at_level=pend_count, encounter_history=encounter_history,
                )
                if resp.get("prompts"):
                    resp["prompts"]["system_prompt"] = new_sys
                    resp["prompts"]["user_prompt"] = new_user
                    changed += 1
                p2_responses.append(resp)

            elif kind == "provider_action_llm_call":
                prompts = payload.get("prompts")
                if not prompts:
                    continue
                old_user = prompts.get("user_prompt", "")
                level_str = old_user.split("\n")[0] if old_user else ""
                level = 0
                if "Current Review Level:" in level_str:
                    try:
                        level = int(level_str.split(":")[1].strip())
                    except (ValueError, IndexError):
                        pass

                start_marker = "CURRENT LINE STATUSES AFTER PAYOR RESPONSE:\n"
                end_marker = "\n\nDECISION:"
                ls_json = "[]"
                s_idx = old_user.find(start_marker)
                e_idx = old_user.find(end_marker)
                if s_idx >= 0 and e_idx > s_idx:
                    ls_json = old_user[s_idx + len(start_marker):e_idx]

                prompts["system_prompt"] = _build_p2_action_system_prompt(config["provider_strategy"])
                prompts["user_prompt"] = _build_p2_action_user_prompt(level, ls_json)
                changed += 1

        # ── PHASE 3 ─────────────────────────────────────────────────────
        elif phase == "phase_3_claims":
            if kind == "submission_built":
                sub = payload.get("submission") or {}
                ctx = sub.get("context") or {}
                pv = ctx.get("patient_visible_data") or {}
                if p3_first_pv is None:
                    p3_first_pv = pv
                lines_state = ctx.get("service_lines_state") or []
                for L in lines_state:
                    if isinstance(L, dict) and L.get("line_number") is not None:
                        p3_line_meta[L["line_number"]] = {
                            "procedure_code": L.get("procedure_code", ""),
                            "service_name": L.get("service_name", ""),
                            "requested_quantity": L.get("requested_quantity", 1),
                            "authorization_number": L.get("authorization_number"),
                            "authorization_status": L.get("authorization_status"),
                        }
                state = SimpleNamespace()
                state.patient_visible_data = pv
                state.service_lines = [SimpleNamespace(**{**L, "service_name": L.get("service_name", ""), "requested_quantity": L.get("requested_quantity", 1)}) for L in lines_state]
                state.phase3_submissions = list(p3_submissions)
                state.phase3_responses = list(p3_responses)
                level = int(sub.get("level", 0))
                prior_rounds = _p3_prior_round_summaries(p3_submissions, p3_responses)
                new_sys = create_phase3_provider_system_prompt(provider_params)
                new_user = create_phase3_provider_user_prompt(state, turn=turn, level=level, prior_rounds=prior_rounds)
                if sub.get("prompts"):
                    sub["prompts"]["system_prompt"] = new_sys
                    sub["prompts"]["user_prompt"] = new_user
                    changed += 1
                p3_submissions.append(sub)

            elif kind == "response_built":
                resp = payload.get("response") or {}
                ctx = resp.get("context") or {}
                pv = ctx.get("patient_summary") or {}
                state = SimpleNamespace()
                state.patient_visible_data = (p3_first_pv or {}).copy() if p3_first_pv else {}
                state.patient_visible_data.update({k: v for k, v in pv.items() if v is not None})
                if "patient_id" not in state.patient_visible_data:
                    state.patient_visible_data["patient_id"] = state.patient_visible_data.get("patient_id", "")
                level = int(resp.get("level", 0))
                encounter_history = _p3_encounter_history(p3_submissions, p3_responses)
                pend_count = _p3_pend_count_at_level(p3_responses, level)
                claim_obj = p3_submissions[-1].get("claim_submission", {}) if p3_submissions else {}
                new_sys = create_phase3_payor_system_prompt(payor_params)
                new_user = create_phase3_payor_user_prompt(
                    state, claim_obj, turn=turn, level=level,
                    pend_count_at_level=pend_count, encounter_history=encounter_history,
                )
                if resp.get("prompts"):
                    resp["prompts"]["system_prompt"] = new_sys
                    resp["prompts"]["user_prompt"] = new_user
                    changed += 1
                p3_responses.append(resp)
                pay = resp.get("payor_response") or {}
                adjs = pay.get("line_adjudications") or []
                p3_current_lines = []
                for a in adjs:
                    if not isinstance(a, dict) or a.get("line_number") is None:
                        continue
                    ln = int(a["line_number"])
                    meta = p3_line_meta.get(ln, {})
                    p3_current_lines.append(SimpleNamespace(
                        line_number=ln,
                        procedure_code=meta.get("procedure_code", ""),
                        service_name=meta.get("service_name", ""),
                        requested_quantity=meta.get("requested_quantity", 1),
                        authorization_number=meta.get("authorization_number"),
                        authorization_status=meta.get("authorization_status"),
                        adjudication_status=a.get("adjudication_status"),
                        decision_reason=a.get("decision_reason"),
                        requested_documents=a.get("requested_documents") or [],
                        current_review_level=level,
                        delivered=True,
                    ))

            elif kind == "provider_action_llm_call":
                prompts = payload.get("prompts")
                if not prompts or not p3_current_lines:
                    continue
                action_state = SimpleNamespace(
                    service_lines=p3_current_lines,
                    turn=turn,
                    provider_params=provider_params,
                )
                new_prompts = build_phase3_provider_action_prompts(action_state, provider_params)
                prompts["system_prompt"] = new_prompts["system_prompt"]
                prompts["user_prompt"] = new_prompts["user_prompt"]
                changed += 1

    return changed > 0, data


def main():
    ap = argparse.ArgumentParser(description="Rewrite Phase 2+3 prompts in audit JSONs")
    ap.add_argument("paths", nargs="+", help="Directory or audit JSON paths")
    ap.add_argument("--dry-run", action="store_true", help="Do not write files")
    args = ap.parse_args()
    files = []
    for p in args.paths:
        if os.path.isfile(p) and p.endswith("_audit.json"):
            files.append(p)
        elif os.path.isdir(p):
            for name in os.listdir(p):
                if name.endswith("_audit.json"):
                    files.append(os.path.join(p, name))
    if not files:
        print("No *_audit.json files found")
        return
    for path in sorted(files):
        print(path)
        try:
            in_dir = os.path.dirname(os.path.abspath(path))
            base = os.path.basename(in_dir)
            out_dir = os.path.normpath(os.path.join(in_dir, "..", "new_" + base))
            changed, data = rewrite_one(path)
            if not args.dry_run:
                os.makedirs(out_dir, exist_ok=True)
                out_audit = os.path.join(out_dir, os.path.basename(path))
                with open(out_audit, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            print(f"  updated={changed} -> {out_dir if not args.dry_run else '(dry-run)'}")
        except Exception as e:
            print(f"  error: {e}")
            raise


if __name__ == "__main__":
    main()
