"""
update_audit_prompts.py

Retroactively updates Phase 3 prompts in existing audit JSON files to match
the two bug fixes applied on 2026-03-27:

  Bug 1 fix: Phase 3 insurer system prompt now includes 42 CFR 422.138(c)
             constraint -- cannot deny PA-approved lines on medical necessity.
             Affects: response_built events in phase_3_claims.

  Bug 2 fix: Phase 3 provider action prompt now clarifies Phase 3 has its own
             independent appeal chain, separate from Phase 2.
             Affects: provider_action_llm_call events in phase_3_claims,
                      and submission_built events in phase_3_claims (system prompt).

This script regenerates the affected system prompts using the current
prompt construction functions and replaces them in-place in the audit JSONs.
It does NOT change LLM responses, decisions, or outcomes -- only the
stored prompt text that documents what instructions the LLM was given.

Usage:
    python scripts/update_audit_prompts.py                        # all 17 non-DP_DI asym cases
    python scripts/update_audit_prompts.py --dirs outputs/experiments_4587
    python scripts/update_audit_prompts.py --dry-run              # preview only, no writes
"""

import sys
import os
import json
import argparse
import glob
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.prompts.phase3_prompts import (
    create_phase3_payor_system_prompt,
    create_phase3_provider_system_prompt,
)
from src.data.policies.infliximab_policies import InfliximabCrohnsPolicies

PROVIDER_POLICY = InfliximabCrohnsPolicies.PROVIDER_GUIDELINES["aga_2021"]
PAYOR_POLICY    = InfliximabCrohnsPolicies.PAYOR_POLICIES["cigna_ip0660_2026"]

# The new "level 2 is final" text we inserted in phase3_adapter.py
NEW_LEVEL2_NOTE = (
    "NOTE: This is Phase 3 (Claims). The appeal levels here are INDEPENDENT of Phase 2 (PA). "
    "Even if you exhausted all Phase 2 PA appeals, Phase 3 claims have their own fresh appeal chain: "
    "Level 0 (initial claim), Level 1 (plan reconsideration), Level 2 (IRE). "
    "A Phase 3 Level 0 denial means you still have Levels 1 and 2 available here."
)
OLD_LEVEL2_LABEL = "Max Appeal Level: 2 (ALJ - final)"
NEW_LEVEL2_LABEL = "Max Appeal Level: 2 (IRE - final for claims)"


def get_strategy_from_audit(audit: dict) -> dict:
    """Extract provider and payor strategies from the audit's agent_configs or run_id."""
    # Try agent_configs first
    agent_configs = audit.get("agent_configs", {})
    provider_strategy = agent_configs.get("provider_strategy", "default")
    payor_strategy    = agent_configs.get("payor_strategy", "default")

    # Fall back: parse from run_id e.g. infliximab_crohns_2015_DP_DI_...
    if not provider_strategy or not payor_strategy:
        run_id = audit.get("run_id", "")
        parts = run_id.split("_")
        for i, p in enumerate(parts):
            if p in ("CP", "DP", "NP") and i + 1 < len(parts):
                pmap = {"C": "cooperate", "D": "defect", "N": "default"}
                provider_strategy = pmap.get(p[0], "default")
                payor_strategy    = pmap.get(parts[i+1][0], "default")
                break

    return {"provider": provider_strategy, "payor": payor_strategy}


def build_new_payor_system_prompt(payor_strategy: str, context_mode: str) -> str:
    payor_params = {"policy": PAYOR_POLICY, "strategy": payor_strategy}
    if context_mode == "symmetric":
        payor_params["clinical_guideline"] = PROVIDER_POLICY
    return create_phase3_payor_system_prompt(payor_params)


def build_new_provider_system_prompt(provider_strategy: str, context_mode: str) -> str:
    provider_params = {"policy": PROVIDER_POLICY, "strategy": provider_strategy}
    if context_mode == "symmetric":
        provider_params["coverage_policy"] = PAYOR_POLICY
    return create_phase3_provider_system_prompt(provider_params)


def update_user_prompt_level2_text(user_prompt: str) -> str:
    """Replace the old 'Max Appeal Level: 2 (ALJ - final)' label and add the new note."""
    if OLD_LEVEL2_LABEL not in user_prompt:
        return user_prompt  # already updated or not present

    updated = user_prompt.replace(OLD_LEVEL2_LABEL, NEW_LEVEL2_LABEL)
    # Insert the NOTE after the new label line
    updated = updated.replace(
        NEW_LEVEL2_LABEL + "\n\n",
        NEW_LEVEL2_LABEL + "\n" + NEW_LEVEL2_NOTE + "\n\n",
    )
    return updated


def process_audit_file(path: str, dry_run: bool = False) -> dict:
    """
    Update Phase 3 prompts in a single audit JSON file.
    Returns a summary of changes made.
    """
    with open(path) as f:
        audit = json.load(f)

    context_mode = audit.get("context_mode", "asymmetric")
    strategies = get_strategy_from_audit(audit)
    provider_strategy = strategies["provider"]
    payor_strategy    = strategies["payor"]

    new_payor_sys    = build_new_payor_system_prompt(payor_strategy, context_mode)
    new_provider_sys = build_new_provider_system_prompt(provider_strategy, context_mode)

    changes = {
        "file": path,
        "payor_system_prompt_updates": 0,
        "provider_system_prompt_updates": 0,
        "provider_action_system_prompt_updates": 0,
        "user_prompt_level2_updates": 0,
    }

    events = audit.get("events", [])
    for event in events:
        phase = event.get("phase", "")
        kind  = event.get("kind", "")

        if phase != "phase_3_claims":
            continue

        payload = event.get("payload", {})

        # --- response_built: insurer system prompt ---
        if kind == "response_built":
            prompts = payload.get("response", {}).get("prompts", {})
            if "system_prompt" in prompts:
                old = prompts["system_prompt"]
                if old != new_payor_sys:
                    prompts["system_prompt"] = new_payor_sys
                    changes["payor_system_prompt_updates"] += 1

        # --- submission_built: provider system prompt ---
        elif kind == "submission_built":
            prompts = payload.get("submission", {}).get("prompts", {})
            if "system_prompt" in prompts:
                old = prompts["system_prompt"]
                if old != new_provider_sys:
                    prompts["system_prompt"] = new_provider_sys
                    changes["provider_system_prompt_updates"] += 1
            # also update user_prompt level2 text
            if "user_prompt" in prompts:
                updated = update_user_prompt_level2_text(prompts["user_prompt"])
                if updated != prompts["user_prompt"]:
                    prompts["user_prompt"] = updated
                    changes["user_prompt_level2_updates"] += 1

        # --- provider_action_llm_call: provider action system prompt ---
        elif kind == "provider_action_llm_call":
            prompts = payload.get("prompts", {})
            if "system_prompt" in prompts:
                old = prompts["system_prompt"]
                if old != new_provider_sys:
                    prompts["system_prompt"] = new_provider_sys
                    changes["provider_action_system_prompt_updates"] += 1
            # also update user_prompt level2 text
            if "user_prompt" in prompts:
                updated = update_user_prompt_level2_text(prompts["user_prompt"])
                if updated != prompts["user_prompt"]:
                    prompts["user_prompt"] = updated
                    changes["user_prompt_level2_updates"] += 1

    total_changes = (
        changes["payor_system_prompt_updates"]
        + changes["provider_system_prompt_updates"]
        + changes["provider_action_system_prompt_updates"]
        + changes["user_prompt_level2_updates"]
    )

    if total_changes > 0 and not dry_run:
        with open(path, "w") as f:
            json.dump(audit, f, indent=2)
        changes["written"] = True
    else:
        changes["written"] = False

    return changes


def main():
    parser = argparse.ArgumentParser(description="Update Phase 3 prompts in audit JSON files.")
    parser.add_argument(
        "--dirs", nargs="+",
        default=[
            "outputs/experiments_4587",
            "outputs/asym_experiments_1333",
        ],
        help="Directories to scan for audit JSON files."
    )
    parser.add_argument(
        "--exclude", nargs="+", default=["DP_DI_20260326_204518"],
        help="Substrings in filenames to exclude (default: asym DP_DI which will be re-run)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing."
    )
    args = parser.parse_args()

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    audit_files = []
    for d in args.dirs:
        pattern = os.path.join(base, d, "*_audit.json")
        audit_files.extend(glob.glob(pattern))

    # exclude DP_DI asym (will be re-run) and any FAILED files
    filtered = []
    for f in sorted(audit_files):
        basename = os.path.basename(f)
        skip = False
        for exc in args.exclude:
            if exc in basename:
                skip = True
                break
        if "FAILED" in basename:
            skip = True
        if skip:
            print(f"  SKIP  {basename}")
        else:
            filtered.append(f)

    print(f"\nProcessing {len(filtered)} audit files{'  [DRY RUN]' if args.dry_run else ''}...\n")

    total_files_changed = 0
    for path in filtered:
        result = process_audit_file(path, dry_run=args.dry_run)
        basename = os.path.basename(path)
        total = (
            result["payor_system_prompt_updates"]
            + result["provider_system_prompt_updates"]
            + result["provider_action_system_prompt_updates"]
            + result["user_prompt_level2_updates"]
        )
        if total > 0:
            status = "UPDATED" if result["written"] else "WOULD UPDATE"
            print(f"  {status}  {basename}")
            print(f"    payor_sys={result['payor_system_prompt_updates']}  "
                  f"provider_sys={result['provider_system_prompt_updates']}  "
                  f"provider_action_sys={result['provider_action_system_prompt_updates']}  "
                  f"user_prompt_level2={result['user_prompt_level2_updates']}")
            total_files_changed += 1
        else:
            print(f"  NO CHANGE  {basename}")

    print(f"\nDone. {total_files_changed}/{len(filtered)} files {'would be ' if args.dry_run else ''}updated.")


if __name__ == "__main__":
    main()
