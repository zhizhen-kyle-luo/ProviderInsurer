from __future__ import annotations

"""
Shared workflow definitions for LLM prompts.
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

# Review level definitions (maps to Medicare Advantage appeal levels)
REVIEW_LEVEL_DEFINITIONS = (
    "Review levels (Medicare Advantage appeal structure):\n"
    "- Level 0 (Organization Determination): UM triage applies plan's coverage criteria "
    "mechanically under throughput pressure. Low interpretive latitude.\n"
    "- Level 1 (Plan Reconsideration): Fresh physician reviewer not involved in Level 0. "
    "Deliberate clinical judgment with higher interpretive latitude. Full case file access. "
    "65-day filing deadline. Unfavorable decisions are automatically forwarded to Level 2.\n"
    "- Level 2 (Independent External Review via Maximus Federal IRE): Independent physician "
    "reviewer not affiliated with the health plan. Evaluates against Medicare coverage rules "
    "(NCDs/LCDs, not insurer's proprietary criteria). Binary approve/deny only. "
    "Final binding decision.\n"
)

# Payor decision definitions - used by both provider (to interpret) and payor (to render)
PAYOR_DECISION_DEFINITIONS = (
    "Payor line decisions:\n"
    "- approved: meets criteria; issue authorization number.\n"
    "- modified: approve with changes (e.g., quantity_reduction, site_change); set modification_type.\n"
    "- denied: does not meet criteria; explain which criteria failed.\n"
    "- pending_info: missing documentation; list requested_documents (not allowed at level 2).\n"
)

# L2-specific decision definitions (binary approve/deny only)
PAYOR_DECISION_DEFINITIONS_L2 = (
    "Reviewer decisions:\n"
    "- approved: meets Medicare coverage criteria; authorize the service.\n"
    "- denied: does not meet Medicare coverage criteria; explain which criteria are not met.\n"
    "Note: modified and pending_info are not available at external review. You must approve or deny.\n"
)

# Provider action definitions - only provider needs this
PROVIDER_ACTION_DEFINITIONS = (
    "Provider action types:\n"
    "- RESUBMIT (bundle-level): withdraw and resubmit a corrected claim/PA at level 0.\n"
    "  In claims (Phase 3) this is a corrected claim (frequency code 7); in PA (Phase 2) a new request.\n"
    "  Use for provider-side errors (wrong codes, missing diagnoses, incorrect auth references).\n"
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

# L2 definitions for IRE reviewer (restricted decision vocab)
WORKFLOW_ACTION_DEFINITIONS_PAYOR_L2 = (
    f"{REVIEW_LEVEL_DEFINITIONS}\n"
    f"{PAYOR_DECISION_DEFINITIONS_L2}\n"
    "Use these exact tokens (case-insensitive) in JSON responses."
)
