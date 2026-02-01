from __future__ import annotations

"""
Shared workflow definitions for LLM prompts.
Imported by phase2_prompts and phase3_prompts.

This file builds human-readable prompt text from the canonical definitions in config.py.
config.py is the single source of truth for valid tokens/values.

Action hierarchy:
- Bundle-level actions: CONTINUE, APPEAL, RESUBMIT, ABANDON
- Per-line intents (under CONTINUE): PROVIDE_DOCS, ACCEPT_MODIFY (both per-line, explicit)
- Per-line intents (under APPEAL): which lines to escalate (with to_level)

Key distinction between PROVIDE_DOCS vs RESUBMIT:
- PROVIDE_DOCS: Same PA request, provider supplies missing documentation payor asked for
- RESUBMIT: Withdraw current PA entirely, submit a new/corrected request (may have different
  lines, codes, quantities, or additional services). Used for provider-side errors like
  incorrect coding, missing diagnoses, or strategic decision to request different services.
"""

from .config import (
    VALID_PROVIDER_BUNDLE_ACTIONS,
    VALID_PROVIDER_CONTINUE_INTENTS,
    VALID_PAYOR_LINE_STATUSES,
    VALID_REQUEST_TYPES,
)

# review level definitions
REVIEW_LEVEL_DEFINITIONS = (
    "Review levels:\n"
    "- Level 0 (Initial Review): UM nurse/triage reviews against policy checklist.\n"
    "- Level 1 (Reconsideration): Medical Director peer-to-peer review.\n"
    "- Level 2 (Independent Review): External IRE; final binding decision, no pend allowed.\n"
)

# Shared instructions used in phase prompts
WORKFLOW_ACTION_DEFINITIONS = (
    f"{REVIEW_LEVEL_DEFINITIONS}\n"
    "Provider bundle actions:\n"
    "- CONTINUE: proceed without escalating review level. Requires per-line intents:\n"
    "  - For pending_info lines: use intent=PROVIDE_DOCS (you will supply requested docs)\n"
    "  - For modified lines you accept: use intent=ACCEPT_MODIFY\n"
    "- APPEAL: escalate denied/modified lines to next review level (disputes coverage decision).\n"
    "  Requires per-line entries with to_level (must be current_level + 1, max 2).\n"
    "- RESUBMIT: withdraw the current PA/claim entirely and submit a new/corrected request.\n"
    "  Use for provider-side errors (wrong codes, missing diagnoses) or to request different services.\n"
    "  NOT a formal appeal - starts fresh at level 0.\n"
    "- ABANDON: stop pursuit entirely.\n"
    "  - NO_TREAT: patient does not receive service.\n"
    "  - TREAT_ANYWAY: provider delivers service and absorbs cost.\n\n"
    "Payor line decisions:\n"
    "- approved: meets criteria; issue authorization number.\n"
    "- modified: approve with changes (e.g., quantity_reduction, site_change); set modification_type.\n"
    "- denied: does not meet criteria; explain which criteria failed.\n"
    "- pending_info: missing documentation; list requested_documents (not allowed at level 2).\n\n"
    f"Valid request types: {list(VALID_REQUEST_TYPES)}.\n"
    "Use these exact tokens (case-insensitive) in JSON responses."
)
