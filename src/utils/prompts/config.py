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

# empty by design - internal only, not sent to insurer
INTERNAL_REASONING = ""

PROVIDER_ACTIONS_GUIDE = """
PROVIDER ACTION SPACE (choose one per line after payor decision):

NOTE: Each service line is adjudicated independently. Provider chooses action per-line.

1. CONTINUE - strengthen record at current review level without escalating
   When to use: after PENDING_INFO only
   Strategic meaning: provide the requested documentation/information
   Examples:
   - Provide missing vitals, lab values, imaging reports, guideline citations
   - Add objective measurements (sequential vital signs, quantified severity scores)
   - Submit peer-reviewed literature supporting medical necessity

2. APPEAL - escalate to next review authority (changes who reviews)
   When to use: after DENY or MODIFY
   Strategic meaning: challenge adverse determination by triggering formal reconsideration
   Examples:
   - Level 0→1: request plan medical director reconsideration after triage denial
   - Level 1→2: automatic forward to Independent Review Entity (IRE) per 42 CFR §422.592
   - After MODIFY: appeal observation→inpatient or home infusion→hospital infusion

3. ABANDON - exit this line, accept current outcome
   When to use: cost exceeds expected recovery, patient urgency, or low reversal probability
   Strategic meaning: stop contesting this line, accept the decision
   Examples:
   - Accept observation status instead of continuing inpatient fight
   - Accept home infusion instead of hospital infusion (after MODIFY)
   - Accept denial and pursue alternative care pathway
"""

PAYOR_ACTIONS_GUIDE = """
PAYOR ACTION SPACE (use exact JSON value in "action" field):

1. "approved" - authorize coverage/service as requested (X12 278 HCR: A1)
   When to use: medical necessity criteria met, documentation complete
   Examples: approve inpatient status, approve medication, approve diagnostic test

2. "modified" - approve with changes (X12 278 HCR: A2/A6 Modified)
   When to use: approve with quantity reduction OR code/service downgrade
   Examples:
   - Quantity reduction: approve 3 of 5 requested infusions (set approved_quantity + modification_type="quantity_reduction")
   - Code downgrade: approve observation instead of inpatient (set modification_type="code_downgrade")
   - Service downgrade: approve home infusion instead of hospital infusion (modification_type="code_downgrade")
   Note: this is NOT a denial - provider gets authorization, just modified

3. "denied" - adverse determination without authorization (X12 278 HCR: A3)
   When to use: medical necessity not met, step therapy incomplete, documentation insufficient
   Examples: deny for not meeting policy criteria, deny for incomplete step therapy, deny as experimental/investigational
   CMS 2026 rule: must provide specific denial reason

4. "pending_info" - pend decision, request additional documentation (X12 278 HCR: A4)
   When to use: cannot adjudicate with current documentation, need specific clinical data
   Examples: request vital signs, lab values (troponin, BNP, lactate), imaging reports, medication administration record
   Note: NOT available at Level 2 (independent review must decide on submitted record per 42 CFR §422.592)
"""

# Strategic logic table: what provider actions are valid after each payor decision
# NOTE: actions apply PER LINE - each service line is adjudicated independently
PROVIDER_RESPONSE_MATRIX = """
STRATEGIC ACTION MATRIX (what provider can do after each payor decision):

NOTE: In multi-line requests, each line is adjudicated independently (per X12 278/835).
Provider responds per-line. Some lines may be approved while others denied/modified.

Payor Decision      | Request Type           | Valid Provider Actions | Strategic Logic
--------------------|------------------------|------------------------|------------------
APPROVE             | TREATMENT              | (None) - TERMINAL      | Line complete. Treatment authorized.
APPROVE             | DIAGNOSTIC             | (decision prompt)      | Test done. Provider decides: request_treatment or no_treatment_needed.
APPROVE             | LEVEL_OF_CARE          | (None) - TERMINAL      | Line complete. Got status you wanted.
MODIFY              | ANY                    | APPEAL, ABANDON        | APPEAL=fight for original. ABANDON=accept modified.
PEND_INFO           | ANY                    | CONTINUE, ABANDON      | CONTINUE=provide requested info. ABANDON=exit line. (Cannot APPEAL pend)
DENY                | ANY                    | APPEAL, ABANDON        | APPEAL=escalate to next level. ABANDON=exit line.
"""

PROVIDER_REQUEST_TYPES = """
REQUEST TYPES (provider must specify in each request):

1. DIAGNOSTIC_TEST - test or imaging to narrow differential diagnosis
   Purpose: gather objective clinical data to establish or rule out diagnosis
   Examples: MRI, CT scan, lab panel, biopsy, EKG, stress test
   Flow: if approved, test result informs whether treatment is needed

2. LEVEL_OF_CARE - where/how service is provided (setting/acuity)
   Purpose: establish appropriate care setting based on clinical severity
   Examples: inpatient vs observation, hospital infusion vs home infusion, ICU vs floor, hospital vs SNF
   Flow: determines site of service for subsequent treatment

3. TREATMENT - what service is provided (medication, procedure, therapy)
   Purpose: deliver definitive care for established diagnosis
   Examples: Infliximab infusion, surgical procedure, radiation therapy, IV antibiotics
   Flow: final authorization for care delivery

TYPICAL WORKFLOW: diagnostic_test → level_of_care → treatment
- Parts can be skipped if not needed (e.g., clear diagnosis skips to treatment)
- Parts can be combined in one request (e.g., treatment + level_of_care together)
- Pre-treatment requirements (e.g., TB/Hep B screening for biologics) should be included WITH the treatment request, not as separate follow-up requests
- Once treatment is approved, Phase 2 authorization is COMPLETE - do not request additional tests

Each service line is adjudicated independently - mixed request types are allowed in a single submission.
"""

VALID_PROVIDER_ACTIONS = {
    "continue",
    "appeal",
    "abandon"
}

# canonical payor action values (lowercase)
# unified for both Phase 2 (278) and Phase 3 (835)
VALID_PAYOR_ACTIONS = [
    "approved",
    "modified",
    "denied",
    "pending_info"
]

# canonical request type values (lowercase)
VALID_REQUEST_TYPES = {
    "treatment",
    "diagnostic_test",
    "level_of_care"
}

# canonical treatment decision values (post-PA-denial decision)
VALID_TREATMENT_DECISIONS = {
    "treat_anyway",  # provide care despite denial
    "no_treat"       # do not provide care
}

# canonical post-diagnostic decision values (after diagnostic test approved and result available)
VALID_POST_DIAGNOSTIC_DECISIONS = {
    "request_treatment",    # test result indicates treatment needed, submit new treatment request
    "no_treatment_needed"   # test result indicates no treatment needed, line complete
}

WORKFLOW_LEVELS = {
    0: {
        "name": "initial_determination",
        "role_label": "UM Triage Reviewer (Nurse/Algorithm) - Organization Determination (42 CFR §422.566)",
        "can_pend": True,
        "terminal": False,
        # "independent": False,
        "copilot_active": True,
        "review_style": "checklist-driven, request info for missing required fields",
        "description": "Initial UM review. Prioritize PENDING_INFO when required fields are missing. Be checklist-driven. Deny if clear policy mismatch."
    },
    1: {
        "name": "internal_reconsideration",
        "role_label": "Medical Director (Plan Reconsideration) - Plan Reconsideration (42 CFR §422.582)",
        "can_pend": True,
        "terminal": False,
        # "independent": False,
        "copilot_active": True,
        "review_style": "clinical interpretation, fresh eyes, less pend-prone",
        "description": "Internal reconsideration by higher authority. Allow more clinical interpretation. Less likely to PENDING_INFO if enough evidence exists. Fresh reviewer semantics."
    },
    2: {
        "name": "independent_review",
        "role_label": "Independent Review Entity (IRE) - IRE Review (42 CFR §422.592)",
        "can_pend": False,
        "terminal": True,
        # "independent": True,
        "copilot_active": False,
        "review_style": "record-based binding decision, cite criteria explicitly",
        "description": "Independent external review. Decide based on submitted record only. Cite criteria. No PENDING_INFO allowed. Produces binding final disposition."
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

# constraints for oversight editing by role
OVERSIGHT_CONSTRAINTS = {
    'provider': f"""PROVIDER CONSTRAINTS:
when editing provider requests, valid action values are: {", ".join(VALID_PROVIDER_ACTIONS)}
do not invent new action values.""",
    'payor': f"""PAYOR CONSTRAINTS:
payor decisions use per-line adjudication. each line's "adjudication_status" must be exactly one of: {", ".join(VALID_PAYOR_ACTIONS)}
use "pending_info" (not "pended" or "pend") when requesting documentation."""
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
