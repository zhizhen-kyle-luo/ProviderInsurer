"""
Prompt Configuration Constants and Workflow Definitions

Shared configuration for all prompts:
- WORKFLOW_LEVELS: 3-level review structure (initial → reconsideration → independent)
- Behavioral parameters for provider and payor agents
- Oversight budgets for human review effort
"""
MAX_ITERATIONS = 3
NOISE_PROBABILITY = 0
MAX_REQUEST_INFO_PER_LEVEL = 2

# Internal reasoning for provider documentation (empty by design - internal only, not sent to insurer)
INTERNAL_REASONING = ""

# ============================================================================
# STRATEGIC ACTION SPACE (3 actions each side, used by Phase 2 and Phase 3)
# ============================================================================
# Based on Medicare Advantage appeals workflow (42 CFR §422.566-592)
# Real-world data: 82% of PA appeals succeed (AMA), but only 15-20% are filed
# CMS 2026 rules: 72h expedited, 7 days standard decision timelines

PROVIDER_ACTIONS_GUIDE = """
PROVIDER ACTION SPACE (choose one each turn):

1. CONTINUE - strengthen record at current review level without escalating
   When: after REQUEST_INFO (pend) to provide missing documentation
   Examples: order additional tests (ABG, troponin, imaging), request alternative test if initial denied (MRI instead of CT), add objective values (vitals, labs, sequential measurements), provide guideline citations (InterQual, MCG), submit peer-reviewed literature
   Note: micro-moves like "rewrite note" or "add citation" are all CONTINUE variants, not separate actions

2. APPEAL - escalate to next review authority (changes who reviews)
   When: after DENY to trigger formal reconsideration
   Examples: Level 0→1 (plan medical director reconsideration), Level 1→2 (automatic forward to Independent Review Entity per 42 CFR §422.592)
   Timeline: 30 days standard, 72 hours expedited
   Success rate: 82% of appeals ultimately succeed, but costs staff time

3. ABANDON - exit dispute, accept alternative outcome
   When: cost exceeds expected recovery, patient care cannot wait, or denial likely irreversible
   Examples: accept observation instead of inpatient, proceed with patient paying out-of-pocket, defer elective procedure
   Why physicians abandon: 62% cite past negative experience, 48% cite patient urgency, 48% cite insufficient staff (AMA data)
"""

PAYOR_ACTIONS_GUIDE = """
PAYOR ACTION SPACE (choose one each turn):

1. APPROVE - authorize coverage/service at current stage
   Examples: approve inpatient status, approve medication with quantity limit, partial approval with restrictions
   Note: can include restrictions like "approved for 30 days only"

2. DENY - adverse determination without authorization
   Examples: deny for not meeting medical necessity, deny for insufficient documentation, deny citing incomplete step therapy
   Note: can suggest alternatives (e.g., "deny inpatient but observation may be appropriate") without authorizing them
   CMS 2026 rule: must provide specific denial reason
   Result: provider may APPEAL to next level (unless already at Level 2 terminal review)

3. REQUEST_INFO - pend decision pending additional documentation
   Examples: request vital signs from admission, request lab values (troponin, BNP), request imaging reports, request prior failed treatments
   Note: NOT available at Level 2 (independent review must decide on submitted record per 42 CFR §422.592)
   Provider response: provider should CONTINUE (not APPEAL) by providing requested info at same level
   Timeline: review clock resets upon receipt of information
"""

PROVIDER_ACTIONS = ["CONTINUE", "APPEAL", "ABANDON"]
PAYOR_ACTIONS = ["APPROVE", "DENY", "REQUEST_INFO"]

# Level definitions for 3-level Medicare Advantage-inspired workflow (0-indexed)
# Level 0: UM triage / checklist-driven initial determination
# Level 1: internal reconsideration by higher authority (medical director-like)
# Level 2: independent external review (IRE/IRO), terminal, no internal notes access

WORKFLOW_LEVELS = {
    0: {
        "name": "initial_determination",
        "role": "triage",
        "role_label": "UM Triage Reviewer (Nurse/Algorithm) - Organization Determination (42 CFR §422.566)",
        "can_pend": True,
        "terminal": False,
        "independent": False,
        "sees_internal_notes": True,
        "copilot_active": True,
        "review_style": "checklist-driven, request info for missing required fields",
        "description": "Initial UM review. Prioritize REQUEST_INFO when required fields are missing. Be checklist-driven. Deny if clear policy mismatch."
    },
    1: {
        "name": "internal_reconsideration",
        "role": "reconsideration",
        "role_label": "Medical Director (Plan Reconsideration) - Plan Reconsideration (42 CFR §422.582)",
        "can_pend": True,
        "terminal": False,
        "independent": False,
        "sees_internal_notes": True,
        "copilot_active": True,
        "review_style": "clinical interpretation, fresh eyes, less pend-prone",
        "description": "Internal reconsideration by higher authority. Allow more clinical interpretation. Less likely to REQUEST_INFO if enough evidence exists. Fresh reviewer semantics."
    },
    2: {
        "name": "independent_review",
        "role": "independent",
        "role_label": "Independent Review Entity (IRE) - IRE Review (42 CFR §422.592)",
        "can_pend": False,
        "terminal": True,
        "independent": True,
        "sees_internal_notes": False,
        "copilot_active": False,
        "review_style": "record-based binding decision, cite criteria explicitly",
        "description": "Independent external review. Decide based on submitted record only. Cite criteria. No REQUEST_INFO allowed. Produces binding final disposition."
    }
}

# Mapping from stage names to level numbers (0-indexed)
LEVEL_NAME_MAP = {
    "initial_determination": 0,
    "internal_appeal": 1,
    "internal_reconsideration": 1,
    "independent_review": 2
}

DEFAULT_PROVIDER_PARAMS = {
    'oversight_intensity': 'medium',
}

DEFAULT_PAYOR_PARAMS = {
    'oversight_intensity': 'low' 
}

OVERSIGHT_GUIDANCE = {
    'low': {
        'instruction': 'skim draft quickly, only fix obvious errors. if draft is reasonable, approve as-is.',
        'typical_behavior': 'most drafts approved with no changes or minor fixes only'
    },
    'medium': {
        'instruction': 'careful review, check key facts against evidence. fix clear errors, add missing critical items.',
        'typical_behavior': 'some drafts approved as-is, others get moderate edits'
    },
    'high': {
        'instruction': 'thorough line-by-line review, verify all claims against evidence. ensure complete accuracy.',
        'typical_behavior': 'most drafts get significant edits, verify all facts'
    }
}


PROVIDER_PARAM_DEFINITIONS = {
    'oversight_intensity': {
        'low': 'minimal human review of AI drafts, accept with minor tweaks only',
        'medium': 'standard review cycle, can fix contradictions and add missing evidence',
        'high': 'thorough multi-pass review, extensive editing allowed, verify all claims against evidence'
    }
}

PAYOR_PARAM_DEFINITIONS = {
    'oversight_intensity': {
        'low': 'minimal human review of AI decisions, automated processing with rare overrides',
        'medium': 'standard review cycle, medical director spot-checks AI decisions',
        'high': 'thorough multi-pass review, extensive human verification of all AI recommendations'
    }
}
