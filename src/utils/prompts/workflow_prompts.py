from __future__ import annotations

"""
Shared definitions of action vocab and workflow semantics.
Imported by phase2_prompts and phase3_prompts.
"""

# Top-level bundle actions for provider
WORKFLOW_PROVIDER_BUNDLE_ACTIONS = ["CONTINUE", "APPEAL", "ABANDON"]

# Line-level intents under CONTINUE
WORKFLOW_PROVIDER_LINE_INTENTS = [
    "PROVIDE_REQUESTED_DOCS",
    "ACCEPT_MODIFY",
    "RESUBMIT_AMENDED",
]

# Line-level payor actions
WORKFLOW_PAYOR_LINE_DECISIONS = ["approved", "modified", "denied", "pending_info"]

# Request types
WORKFLOW_REQUEST_TYPES = ["diagnostic_test", "treatment", "level_of_care"]

# review level definitions (maps to Medicare appeal levels 1-3)
REVIEW_LEVEL_DEFINITIONS = (
    "Review levels:\n"
    "- Level 0 (Initial Review): UM nurse/triage reviews against policy checklist. "
    "(Medicare: Redetermination by MAC)\n"
    "- Level 1 (Reconsideration): Medical Director peer-to-peer review. "
    "(Medicare: QIC reconsideration)\n"
    "- Level 2 (Independent Review): External IRE; final binding decision, no pending_info allowed. "
    "(Medicare: ALJ hearing)\n"
)

# Shared instructions used in phase prompts
WORKFLOW_ACTION_DEFINITIONS = (
    f"{REVIEW_LEVEL_DEFINITIONS}\n"
    "Provider bundle actions:\n"
    "- CONTINUE: proceed without escalating review level.\n"
    "  - PROVIDE_REQUESTED_DOCS: respond to pending_info by supplying requested documentation.\n"
    "  - ACCEPT_MODIFY: accept insurer's modified approval (e.g., reduced quantity).\n"
    "  - RESUBMIT_AMENDED: fix billing/coding errors and resubmit (corrected claim).\n"
    "- APPEAL: escalate denied/modified lines to the next review level (disputes coverage decision).\n"
    "- ABANDON: stop pursuit; either NO_TREAT (patient does not receive service) or "
    "TREAT_ANYWAY (provider absorbs cost).\n\n"
    "Payor line decisions:\n"
    "- approved: meets criteria; issue authorization number.\n"
    "- modified: approve with changes (e.g., quantity_reduction, site_change); set modification_type.\n"
    "- denied: does not meet criteria; explain which criteria failed.\n"
    "- pending_info: missing documentation; list requested_documents (not allowed at level 2).\n\n"
    f"Valid request types: {WORKFLOW_REQUEST_TYPES}.\n"
    "Use these exact tokens (case-insensitive) in JSON responses."
)
