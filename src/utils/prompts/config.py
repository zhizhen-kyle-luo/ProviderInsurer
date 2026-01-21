"""
Prompt Configuration Constants and Workflow Definitions

Single source of truth for:
- review ladder levels and constraints
- canonical action/value vocab
- oversight budgets (review + edit), enforced in code
"""

MAX_ITERATIONS = 3
NOISE_PROBABILITY = 0
MAX_REQUEST_INFO_PER_LEVEL = 2

INTERNAL_REASONING = ""

# Provider now acts at BUNDLE level (one action per turn) with line-targeted directives.
PROVIDER_ACTIONS_GUIDE = """
PROVIDER BUNDLE ACTION SPACE (choose exactly one per turn after payor line decisions):

1. CONTINUE
   Use when: there are pending_info lines and you will supply requested docs at same level
   Meaning: strengthen record without escalation

2. APPEAL
   Use when: there are denied/modified lines and you escalate review authority
   Meaning: advance appeal_level for targeted lines (max level=2)

3. ACCEPT_MODIFY
   Use when: you accept the payer's modified terms for targeted lines
   Meaning: close those lines as approved-as-modified (no escalation)

4. RESUBMIT_AMENDED
   Use when: you materially change the request for targeted lines (code/site/qty/framing/new evidence)
   Meaning: treated as new request instance for that line (appeal_level resets to 0, pend_round resets to 0)

5. ABANDON
   Use when: you stop pursuing authorization for this case in Phase 2
   Modes: NO_TREAT or TREAT_ANYWAY (if you deliver services without auth)
"""

PAYOR_ACTIONS_GUIDE = """
PAYOR ACTION SPACE (per line):

"approved"      authorize as requested
"modified"      authorize with changes (qty reduction or downgrade)
"denied"        adverse determination
"pending_info"  request specific missing documentation (not allowed at Level 2)
"""

PROVIDER_REQUEST_TYPES = """
REQUEST TYPES:
- diagnostic_test
- level_of_care
- treatment

Typical workflow: diagnostic_test → level_of_care → treatment
Can be skipped or combined; mixed request types allowed in one bundle.
"""

# Backward compatibility: some code expects these 3 canonical intents.
VALID_PROVIDER_ACTIONS = {"continue", "appeal", "abandon"}

# New canonical bundle actions used by prompts + transitions (preferred).
VALID_PROVIDER_BUNDLE_ACTIONS = {
    "CONTINUE",
    "APPEAL",
    "ABANDON",
    "ACCEPT_MODIFY",
    "RESUBMIT_AMENDED",
}

VALID_PAYOR_ACTIONS = ["approved", "modified", "denied", "pending_info"]

VALID_REQUEST_TYPES = {"treatment", "diagnostic_test", "level_of_care"}

VALID_TREATMENT_DECISIONS = {"treat_anyway", "no_treat"}

VALID_POST_DIAGNOSTIC_DECISIONS = {"request_treatment", "no_treatment_needed"}

WORKFLOW_LEVELS = {
    0: {
        "name": "initial_determination",
        "role_label": "UM Triage Reviewer (Nurse/Algorithm) - Organization Determination (42 CFR §422.566)",
        "can_pend": True,
        "terminal": False,
        "copilot_active": True,
        "review_style": "checklist-driven, request info for missing required fields",
        "description": "Initial UM review. Use pending_info when required fields are missing. Deny if clear policy mismatch.",
    },
    1: {
        "name": "internal_reconsideration",
        "role_label": "Medical Director (Plan Reconsideration) - Plan Reconsideration (42 CFR §422.582)",
        "can_pend": True,
        "terminal": False,
        "copilot_active": True,
        "review_style": "clinical interpretation, fresh eyes, less pend-prone",
        "description": "Higher authority review. Less pend-prone if enough evidence exists.",
    },
    2: {
        "name": "independent_review",
        "role_label": "Independent Review Entity (IRE) - IRE Review (42 CFR §422.592)",
        "can_pend": False,
        "terminal": True,
        "copilot_active": False,
        "review_style": "record-based binding decision, cite criteria explicitly",
        "description": "Final review. Decide on record. No pending_info allowed.",
    },
}

LEVEL_NAME_MAP = {
    "initial_determination": 0,
    "internal_appeal": 1,
    "internal_reconsideration": 1,
    "independent_review": 2,
}

DEFAULT_PROVIDER_PARAMS = {"oversight_intensity": "medium"}
DEFAULT_PAYOR_PARAMS = {"oversight_intensity": "low"}

# Human-readable instructions (ok to keep). Budgets below are what code enforces.
OVERSIGHT_GUIDANCE = {
    "low": {
        "instruction": "skim view packet, only fix obvious errors. if reasonable, approve as-is.",
        "typical_behavior": "most drafts pass with minimal edits",
    },
    "medium": {
        "instruction": "careful review of flagged/adverse lines. fix clear errors, add missing critical items.",
        "typical_behavior": "moderate edits on some turns",
    },
    "high": {
        "instruction": "thorough review, verify claims against evidence packet. ensure correctness and schema compliance.",
        "typical_behavior": "more edits, more lines expanded",
    },
}

# Enforced budgets for review (what overseer can see) + edit (what can change).
# review_expand_lines: number of line items shown in full detail (summary still includes all lines)
# review_token_budget: cap on view packet size (approx)
# max_patch_ops / max_paths_touched: hard limits on edits
OVERSIGHT_BUDGETS = {
    "provider": {
        "low":    {"review_expand_lines": 1, "review_token_budget": 900,  "max_patch_ops": 3,  "max_paths_touched": 3},
        "medium": {"review_expand_lines": 2, "review_token_budget": 1600, "max_patch_ops": 7,  "max_paths_touched": 6},
        "high":   {"review_expand_lines": 4, "review_token_budget": 2600, "max_patch_ops": 14, "max_paths_touched": 10},
    },
    "payor": {
        "low":    {"review_expand_lines": 1, "review_token_budget": 900,  "max_patch_ops": 3,  "max_paths_touched": 3},
        "medium": {"review_expand_lines": 2, "review_token_budget": 1600, "max_patch_ops": 7,  "max_paths_touched": 6},
        "high":   {"review_expand_lines": 4, "review_token_budget": 2600, "max_patch_ops": 14, "max_paths_touched": 10},
    },
}

OVERSIGHT_CONSTRAINTS = {
    "provider": f"""PROVIDER CONSTRAINTS:
- bundle action must be one of: {", ".join(sorted(VALID_PROVIDER_BUNDLE_ACTIONS))}
- do not invent new action values""",
    "payor": f"""PAYOR CONSTRAINTS:
- each line authorization_status/adjudication_status must be exactly one of: {", ".join(VALID_PAYOR_ACTIONS)}
- use "pending_info" when requesting documentation (not "pend"/"pended")""",
}

PROVIDER_PARAM_DEFINITIONS = {
    "oversight_intensity": {
        "low": "minimal human review/edit budgets enforced by code",
        "medium": "standard review/edit budgets enforced by code",
        "high": "large review/edit budgets enforced by code",
    }
}

PAYOR_PARAM_DEFINITIONS = {
    "oversight_intensity": {
        "low": "minimal human review/edit budgets enforced by code",
        "medium": "standard review/edit budgets enforced by code",
        "high": "large review/edit budgets enforced by code",
    }
}
