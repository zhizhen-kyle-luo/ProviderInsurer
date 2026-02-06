from __future__ import annotations

"""
Shared definitions of action vocab and workflow semantics.
Imported by phase2_prompts and phase3_prompts.

Uses validation sets from config.py as source of truth.
"""

from .config import (
    VALID_PROVIDER_ACTION_TYPES,
    VALID_PROVIDER_LINE_ACTIONS,
    VALID_ABANDON_MODES_PHASE2,
    VALID_ABANDON_MODES_PHASE3,
    VALID_PAYOR_LINE_STATUSES,
    VALID_REQUEST_TYPES,
)

# Review level definitions (maps to Medicare appeal levels)
REVIEW_LEVEL_DEFINITIONS = (
    "Review levels:\n"
    "- Level 0 (Initial Review): UM nurse/triage reviews against policy checklist. "
    "(Medicare: Redetermination by MAC)\n"
    "- Level 1 (Reconsideration): Medical Director peer-to-peer review. "
    "(Medicare: QIC reconsideration)\n"
    "- Level 2 (Independent Review): External IRE; final binding decision, no pending_info allowed. "
    "(Medicare: ALJ hearing)\n"
)

# Payor decision definitions - used by both provider (to interpret) and payor (to render)
PAYOR_DECISION_DEFINITIONS = (
    "Payor line decisions:\n"
    "- approved: meets criteria; issue authorization number.\n"
    "- modified: approve with changes (e.g., quantity_reduction, site_change); set modification_type.\n"
    "- denied: does not meet criteria; explain which criteria failed.\n"
    "- pending_info: missing documentation; list requested_documents (not allowed at level 2).\n"
)

# Provider action definitions - only provider needs this
PROVIDER_ACTION_DEFINITIONS = (
    "Provider action types:\n"
    "- RESUBMIT (bundle-level): withdraw entire PA/claim, start fresh at level 0.\n"
    "  Use for provider-side errors (wrong codes, missing diagnoses).\n"
    "- LINE_ACTIONS (per-line): specify action for each non-approved line.\n\n"
    "Per-line actions (within LINE_ACTIONS):\n"
    "- ACCEPT_MODIFY: accept payor's modification (for modified lines)\n"
    "- PROVIDE_DOCS: will provide requested documents (for pending_info lines)\n"
    "- APPEAL: escalate to next review level (for denied/modified lines, requires to_level)\n"
    "- ABANDON: give up on this line (requires mode: NO_TREAT/TREAT_ANYWAY in Phase 2, WRITE_OFF in Phase 3)\n"
)

# Full definitions for provider (needs both payor decisions and own actions)
WORKFLOW_ACTION_DEFINITIONS_PROVIDER = (
    f"{REVIEW_LEVEL_DEFINITIONS}\n"
    f"{PAYOR_DECISION_DEFINITIONS}\n"
    f"{PROVIDER_ACTION_DEFINITIONS}\n"
    "Use these exact tokens (case-insensitive) in JSON responses."
)

# Definitions for payor (only needs own decision vocab, not provider actions)
WORKFLOW_ACTION_DEFINITIONS_PAYOR = (
    f"{REVIEW_LEVEL_DEFINITIONS}\n"
    f"{PAYOR_DECISION_DEFINITIONS}\n"
    "Use these exact tokens (case-insensitive) in JSON responses."
)
