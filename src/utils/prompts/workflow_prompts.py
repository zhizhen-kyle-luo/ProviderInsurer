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

# Shared instructions used in phase prompts
WORKFLOW_ACTION_DEFINITIONS = (
    "Provider bundle actions:\n"
    "- CONTINUE: proceed without escalation, which may include supplying requested docs, "
    "accepting modified terms, or submitting amended details.\n"
    "- APPEAL: escalate adverse decisions (denied/modified) to the next review level.\n"
    "- ABANDON: stop the authorization pursuit for this case.\n\n"
    "Provider line intents (only under CONTINUE): "
    f"{WORKFLOW_PROVIDER_LINE_INTENTS}\n\n"
    "Payor line decisions (per line): "
    f"{WORKFLOW_PAYOR_LINE_DECISIONS}\n\n"
    "Valid request types for services: "
    f"{WORKFLOW_REQUEST_TYPES}.\n"
    "Use these exact tokens (case-insensitive) for enums in JSON responses."
)
