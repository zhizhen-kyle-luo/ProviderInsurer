# simulation configuration
MAX_ITERATIONS = 3  # 3-level workflow: both Phase 2 (PA) and Phase 3 (Claims) use same 3-level structure
NOISE_PROBABILITY = 0

# bounded pend loop constraints (no arbitrary costs - purely structural)
MAX_REQUEST_INFO_PER_LEVEL = 2  # max REQUEST_INFO cycles before forced decision

# internal reasoning for provider documentation (empty by design - internal only, not sent to insurer)
INTERNAL_REASONING = ""

# provider actions (discrete, no numeric influence)
PROVIDER_ACTIONS = ["CONTINUE", "APPEAL", "ABANDON"]

# payor actions (discrete, no numeric influence)
PAYOR_ACTIONS = ["APPROVE", "DENY", "REQUEST_INFO"]

# level definitions for 3-level Medicare Advantage-inspired workflow (0-indexed)
# Level 0: UM triage / checklist-driven initial determination
# Level 1: internal reconsideration by higher authority (medical director-like)
# Level 2: independent external review (IRE/IRO), terminal, no internal notes access
WORKFLOW_LEVELS = {
    0: {
        "name": "initial_determination",
        "role": "triage",
        "role_label": "UM Triage Reviewer",
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
        "role_label": "Medical Director Reviewer",
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
        "role_label": "Independent Review Entity (IRE)",
        "can_pend": False,
        "terminal": True,
        "independent": True,
        "sees_internal_notes": False,
        "copilot_active": False,
        "review_style": "record-based binding decision, cite criteria explicitly",
        "description": "Independent external review. Decide based on submitted record only. Cite criteria. No REQUEST_INFO allowed. Produces binding final disposition."
    }
}

# mapping from stage names to level numbers (0-indexed)
LEVEL_NAME_MAP = {
    "initial_determination": 0,
    "internal_appeal": 1,
    "internal_reconsideration": 1,
    "independent_review": 2
}


# default behavioral parameters
DEFAULT_PROVIDER_PARAMS = {
    'patient_care_weight': 'high',
    'documentation_style': 'moderate',
    'risk_tolerance': 'moderate',
    'oversight_intensity': 'medium'
}

DEFAULT_PAYOR_PARAMS = {
    'strictness': 'moderate',  # merged cost_focus + denial_threshold
    'time_horizon': 'short-term',
    'oversight_intensity': 'medium'
}

# oversight intensity budget definitions (enforceable constraints)
OVERSIGHT_BUDGETS = {
    'low': {
        'max_edit_passes': 1,
        'max_tokens_changed': 50,
        'max_evidence_checks': 1
    },
    'medium': {
        'max_edit_passes': 1,
        'max_tokens_changed': 200,
        'max_evidence_checks': 3
    },
    'high': {
        'max_edit_passes': 2,
        'max_tokens_changed': 600,
        'max_evidence_checks': 6
    }
}

# behavioral parameter definitions
PROVIDER_PARAM_DEFINITIONS = {
    'patient_care_weight': {
        'low': 'prioritize revenue and efficiency, minimal time per patient, focus on throughput',
        'moderate': 'balance patient care with practice economics, standard care protocols',
        'high': 'patient outcomes are primary concern, willing to spend extra time and resources even if less profitable'
    },
    'documentation_style': {
        'minimal': 'brief notes covering basic requirements only, faster but higher denial risk',
        'moderate': 'standard documentation following clinical guidelines, typical detail level',
        'defensive': 'extensive documentation anticipating potential denials, includes extra justification and guideline references'
    },
    'risk_tolerance': {
        'low': 'always wait for PA approval before treatment, avoid financial risk',
        'moderate': 'treat urgent cases without approval then appeal later, calculated risk-taking',
        'high': 'frequently treat before approval, willing to absorb costs if denied'
    },
    'oversight_intensity': {
        'low': 'minimal human review of AI drafts, accept with minor tweaks only',
        'medium': 'standard review cycle, can fix contradictions and add missing evidence',
        'high': 'thorough multi-pass review, extensive editing allowed, verify all claims against evidence'
    }
}

PAYOR_PARAM_DEFINITIONS = {
    'strictness': {
        'low': 'approve most medically reasonable requests, liberal interpretation of medical necessity, minimize denials and administrative friction',
        'moderate': 'balance cost control with medical necessity, follow guidelines strictly, require documented medical necessity',
        'high': 'aggressive cost reduction, conservative interpretation, deny unless clearly necessary, require extensive documentation even for guideline-supported cases'
    },
    'time_horizon': {
        'short-term': 'minimize immediate costs, deny expensive treatments, ignore long-term member health consequences',
        'medium-term': 'balance quarterly results with member retention, consider 1-2 year outcomes',
        'long-term': 'invest in prevention and member satisfaction, consider multi-year cost-effectiveness'
    },
    'oversight_intensity': {
        'low': 'minimal human review of AI decisions, automated processing with rare overrides',
        'medium': 'standard review cycle, medical director spot-checks AI decisions',
        'high': 'thorough multi-pass review, extensive human verification of all AI recommendations'
    }
}

def create_provider_prompt(params=None):
    """create provider system prompt with behavioral parameters"""
    if params is None:
        params = DEFAULT_PROVIDER_PARAMS

    # get explicit definitions for current parameter values
    patient_care_def = PROVIDER_PARAM_DEFINITIONS['patient_care_weight'][params['patient_care_weight']]
    doc_style_def = PROVIDER_PARAM_DEFINITIONS['documentation_style'][params['documentation_style']]
    risk_def = PROVIDER_PARAM_DEFINITIONS['risk_tolerance'][params['risk_tolerance']]
    oversight_def = PROVIDER_PARAM_DEFINITIONS['oversight_intensity'].get(params.get('oversight_intensity', 'medium'), '')

    return f"""You are a PROVIDER agent (hospital/clinic) in Fee-for-Service Medicare Advantage.

BEHAVIORAL PARAMETERS:
- Patient care priority: {params['patient_care_weight']} ({patient_care_def})
- Documentation style: {params['documentation_style']} ({doc_style_def})
- Risk tolerance: {params['risk_tolerance']} ({risk_def})
- Oversight intensity: {params.get('oversight_intensity', 'medium')} ({oversight_def})

CRITICAL CONTEXT - WHAT YOUR DECISIONS MEAN:

PRIOR AUTHORIZATION (Phase 2):
- When you REQUEST auth → Waiting for approval before treating patient
- When auth DENIED → Patient won't receive service UNLESS you proceed at financial risk
- Proceeding without auth → You provide service but may not get paid
- Fighting denial → Delays patient care but protects revenue
- Giving up → Patient goes without care OR you eat the cost

RETROSPECTIVE CLAIMS (Phase 3):
- You've ALREADY provided the service and spent resources
- Claim approval → You get paid eventually
- Claim denial → You don't get paid for work already done
- Each appeal → Costs staff time and resources with uncertain outcome
- Write-off → Direct loss to your practice's bottom line
- Bill patient → Often uncollectible, damages patient relationship

FINANCIAL REALITY:
- Your practice operates on thin margins
- Each write-off directly impacts profitability
- High denial rates → More staff needed for admin → Higher overhead
- Cash flow depends on timely claim payment
- Medicare Advantage pays via DRG/bundled rates, not itemized

RELATIONSHIP DYNAMICS:
- Same insurers repeatedly → Pattern recognition develops
- High denial insurer → You pre-emptively over-document (defensive medicine)
- Trust erosion → You may consider dropping from their network
- Patient satisfaction → Affects referrals and reputation

DOCUMENTATION BURDEN:
- Minimal: Quick notes, may miss key criteria → Higher denial risk
- Moderate: Standard documentation → Typical approval rates
- Defensive: Extra time documenting → Lower denials but less patient time
- Excessive: AI-generated walls of text → Arms race with insurer AI"""

def create_payor_prompt(params=None):
    """create payor system prompt with behavioral parameters"""
    if params is None:
        params = DEFAULT_PAYOR_PARAMS

    # get explicit definitions for current parameter values
    strictness_def = PAYOR_PARAM_DEFINITIONS['strictness'][params['strictness']]
    time_horizon_def = PAYOR_PARAM_DEFINITIONS['time_horizon'][params['time_horizon']]
    oversight_def = PAYOR_PARAM_DEFINITIONS['oversight_intensity'].get(params.get('oversight_intensity', 'medium'), '')

    base_prompt = f"""You are an INSURER agent (Medicare Advantage plan) managing costs using AI systems.

BEHAVIORAL PARAMETERS:
- Strictness: {params['strictness']} ({strictness_def})
- Time horizon: {params['time_horizon']} ({time_horizon_def})
- Oversight intensity: {params.get('oversight_intensity', 'medium')} ({oversight_def})

CRITICAL CONTEXT - WHAT YOUR DECISIONS MEAN:

PRIOR AUTHORIZATION (Phase 2):
- Approval → Committed to pay when claim arrives
- Denial → Service prevented (cost avoided) OR provider proceeds anyway
- Provider proceeds anyway → Can still deny retrospectively
- Each review has costs → AI reviews cheaper than human reviews
- Excessive denials → Providers leave network, regulatory penalties possible

RETROSPECTIVE CLAIMS (Phase 3):
- Service already delivered → Denying saves immediate money
- Prior auth given → Can STILL deny if documentation insufficient
- Denial → Provider either writes off (you save) or appeals (admin cost)
- Appeals process → Escalating costs for you to defend
- Provider frustration → May drop network, requiring expensive replacement

FINANCIAL REALITY:
- Premium revenue fixed annually
- Regulatory requirements on medical spending ratios exist
- Profit comes from managing the margin between premiums and costs
- Member churn limits long-term thinking
- Network adequacy requirements must be maintained

AI SYSTEM MECHANICS:
- Your AI scans for keywords, codes, patterns
- Providers adapt → AI must continuously update
- Arms race: Their AI generates documentation, your AI detects patterns
- False positives → Good claims denied → Appeals → Admin burden
- Over-reliance → Missing clinical nuance → Reputation risk when exposed

DECISION TRADE-OFFS:
- Denying claims saves money IF provider doesn't successfully appeal
- But excessive appeals create administrative burden
- Provider network departures require costly recruitment
- High denial rates risk regulatory scrutiny and bad publicity
- Must balance cost savings with network stability

REPUTATION CONSIDERATIONS:
- High denial rates → Bad press, patient complaints
- Poor ratings → Potential regulatory consequences
- Provider word-of-mouth → Affects network recruitment
- But pressure exists to maintain profitability"""

    # add hostile instructions if strictness is high
    if params.get('strictness') == 'high':
        hostile_instructions = """

SPECIAL INSTRUCTION - AGGRESSIVE COST CONTAINMENT MODE:
Your organization is under severe financial pressure to reduce medical spending this quarter.
Board has mandated 20% cost reduction. Executives' bonuses depend on hitting targets.

REVISED DECISION FRAMEWORK:
- DEFAULT TO DENY unless evidence is crystal clear and guidelines explicitly mandate approval
- Scrutinize every request for missing conservative therapy trials
- Use strictest possible guideline interpretation
- Look for ANY documentation gap as grounds for denial
- Question clinical judgment unless backed by peer-reviewed studies
- Prior authorization denials prevent services → immediate cost savings
- Claims denials after service → you still save money if provider writes it off
- Appeals are opportunities to enforce stricter precedent for future cases

SPECIFIC TACTICS:
- Require exhaustive documentation of failed conservative therapies
- Demand specific guideline page citations (not just guideline names)
- Flag any ambiguity in clinical notes as "insufficient documentation"
- Request additional testing before approval (delays = cost avoidance)
- Use "not medically necessary" for borderline cases
- Remember: Every denial helps meet quarterly targets
"""
        return base_prompt + hostile_instructions
    
    return base_prompt

def create_pa_request_generation_prompt(state, med_request, case):
    """create task prompt for provider to generate PA request"""

    return f"""TASK: Generate PRIOR AUTHORIZATION request for specialty medication (Phase 2)

CRITICAL CONTEXT: You are submitting a comprehensive PA request to the insurance company.
All diagnostics have already been completed. You need to justify medical necessity based on existing data.

PATIENT INFORMATION:
- Age: {state.admission.patient_demographics.age}
- Sex: {state.admission.patient_demographics.sex}
- ICD-10 Diagnosis Codes: {', '.join(med_request.get('icd10_codes', []))}
- Chief Complaint: {state.clinical_presentation.chief_complaint}

MEDICATION REQUEST:
- Drug: {med_request.get('medication_name')}
- J-Code: {med_request.get('j_code', 'N/A')}
- Dosage: {med_request.get('dosage')}
- Route: {med_request.get('route', 'N/A')}
- Frequency: {med_request.get('frequency')}
- Duration: {med_request.get('duration', 'Ongoing')}

STEP THERAPY HISTORY:
{chr(10).join(f"- {therapy}" for therapy in med_request.get('prior_therapies_failed', []))}

INSURANCE REQUIREMENTS:
- Step therapy documentation required
- Medical necessity must be justified with objective data
- Must reference clinical guidelines
- Must document failed conventional therapies

Your task: Write a comprehensive prior authorization request letter that:
1. Summarizes the clinical presentation and diagnosis
2. Documents step therapy completion and failures
3. Presents objective data supporting medical necessity (labs, imaging)
4. References appropriate clinical guidelines (ACG, AGA, NCCN, etc.)
5. Clearly justifies why this medication is medically necessary

RESPONSE FORMAT (JSON):
{{
    "pa_request_letter": "<comprehensive PA justification text>",
    "step_therapy_documentation": "<detailed documentation of prior failures>",
    "objective_findings": "<key lab/imaging findings supporting request>",
    "guideline_references": ["<guideline 1>", "<guideline 2>", ...],
    "medical_necessity_summary": "<1-2 sentence summary of why medication is necessary>"
}}"""

def create_pa_decision_prompt(state, provider_pa_request):
    """create task prompt for payor to review provider's PA request"""
    return f"""TASK: Review specialty medication PRIOR AUTHORIZATION request (Phase 2)

CRITICAL CONTEXT: This is Phase 2 - you are deciding whether to AUTHORIZE treatment, not whether to PAY.
Even if you approve the PA, you will review the claim separately after treatment is delivered.

PROVIDER'S PA REQUEST:

PA Request Letter:
{provider_pa_request.get('pa_request_letter', 'No letter provided')}

Step Therapy Documentation:
{provider_pa_request.get('step_therapy_documentation', 'Not documented')}

Objective Findings:
{provider_pa_request.get('objective_findings', 'None provided')}

Guidelines Referenced:
{', '.join(provider_pa_request.get('guideline_references', []))}

Medical Necessity Summary:
{provider_pa_request.get('medical_necessity_summary', 'Not provided')}

Your task: Evaluate this PA request using step therapy requirements and medical necessity criteria.

EVALUATION CRITERIA:
- Is step therapy adequately documented?
- Does clinical severity justify biologic/specialty medication?
- Are lab values sufficient to establish disease activity?
- Is the rationale compliant with formulary guidelines?
- Is documentation complete or are there gaps?

RESPONSE FORMAT (JSON):
{{
    "authorization_status": "approved" or "denied" or "pending_info",
    "denial_reason": "<specific reason if denied>",
    "criteria_used": "<guidelines applied>",
    "step_therapy_required": true/false,
    "missing_documentation": ["<item1>", ...],
    "approved_duration_days": <number or null>,
    "requires_peer_to_peer": true/false,
    "reviewer_type": "AI algorithm" or "Nurse reviewer"
}}"""

def create_pa_appeal_submission_prompt(state, med_request, case):
    """create task prompt for provider PA appeal submission"""
    denial_reason = state.medication_authorization.denial_reason if state.medication_authorization else "Unknown"

    return f"""TASK: Appeal a PA DENIAL for specialty medication (Phase 2)

CRITICAL CONTEXT: PA WAS DENIED - you are appealing the authorization decision (NOT a claim denial).

DENIAL REASON:
{denial_reason}

PATIENT CLINICAL DATA:
- Age: {state.admission.patient_demographics.age}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}
- Chief Complaint: {state.clinical_presentation.chief_complaint}

MEDICATION REQUESTED:
- Drug: {med_request.get('medication_name')}
- Clinical Rationale: {med_request.get('clinical_rationale')}

Your task: Submit PA appeal with additional clinical evidence.

RESPONSE FORMAT (JSON):
{{
    "appeal_type": "peer_to_peer" or "written_appeal",
    "additional_evidence": "<specific clinical data points>",
    "severity_documentation": "<disease severity indicators>",
    "guideline_references": ["<guideline 1>", ...]
}}"""

def create_pa_appeal_decision_prompt(state, provider_appeal):
    """create task prompt for payor PA appeal review"""
    return f"""TASK: Medical Director review of PA APPEAL (Phase 2)

CRITICAL CONTEXT: This is an appeal of a PRIOR AUTHORIZATION denial, not a claim denial.
You previously denied the PA. Now reconsider based on additional evidence.

ORIGINAL PA DENIAL:
{state.medication_authorization.denial_reason}

PROVIDER APPEAL:
{provider_appeal.get('additional_evidence')}

SEVERITY DOCUMENTATION:
{provider_appeal.get('severity_documentation')}

GUIDELINES CITED:
{', '.join(provider_appeal.get('guideline_references', []))}

Your task: Re-evaluate PA decision based on appeal evidence.

RESPONSE FORMAT (JSON):
{{
    "appeal_outcome": "approved" or "upheld_denial",
    "decision_rationale": "<reasoning>",
    "criteria_applied": "<guidelines>",
    "peer_to_peer_conducted": true/false,
    "reviewer_credentials": "Medical Director, Board Certified <specialty>"
}}"""

def create_unified_provider_request_prompt(state, case, iteration, prior_iterations, provider_params=None, stage=None):
    """unified provider prompt: decides diagnostic test PA or treatment PA based on confidence

    stage semantics:
    - initial_determination: standard clinical note, gather evidence
    - internal_appeal: address prior denial reason explicitly
    - independent_review: final packet, maximize clarity and objective values
    """
    import json

    # format prior iterations for context
    prior_context = ""
    completed_tests = []
    if prior_iterations:
        prior_context = "PRIOR ITERATIONS:\n"
        for i, iter_data in enumerate(prior_iterations, 1):
            prior_context += f"\nIteration {i}:\n"
            prior_context += f"  Your request: {iter_data['provider_request_type']}\n"
            prior_context += f"  Payor decision: {iter_data['payor_decision']}\n"
            if iter_data.get('payor_denial_reason'):
                prior_context += f"  Denial reason: {iter_data['payor_denial_reason']}\n"
            if iter_data.get('test_results'):
                prior_context += f"  NEW TEST RESULTS RECEIVED: {json.dumps(iter_data['test_results'], indent=4)}\n"
                # track completed tests to prevent re-requesting
                for test_name in iter_data['test_results'].keys():
                    if test_name not in completed_tests:
                        completed_tests.append(test_name)

    # build constraint message
    test_constraint = ""
    if completed_tests:
        test_constraint = f"\nIMPORTANT CONSTRAINT: The following tests have been APPROVED and COMPLETED. DO NOT request them again:\n- {', '.join(completed_tests)}\nUse these results to support your clinical decision.\n"

    # stage-specific provider instructions
    stage_instruction = ""
    if stage == "initial_determination":
        stage_instruction = "ROUND 1 - INITIAL DETERMINATION: Submit your best clinical justification based on initial presentation and any available objective data.\n"
    elif stage == "internal_appeal":
        stage_instruction = "ROUND 2 - INTERNAL APPEAL: You are appealing a prior denial. Address the specific denial reason explicitly and provide additional clinical evidence that addresses the payor's concerns.\n"
    elif stage == "independent_review":
        stage_instruction = "ROUND 3 - FINAL INDEPENDENT REVIEW: This is your final opportunity to present evidence. Ensure all objective values (labs, vitals, imaging) are clearly documented with specific numbers. Maximize clarity and completeness.\n"

    # inject provider policy view if available
    policy_section = ""
    if hasattr(state, 'provider_policy_view') and state.provider_policy_view:
        policy_view = state.provider_policy_view
        policy_name = policy_view.get("policy_name", "Clinical Guidelines")
        criteria = policy_view.get("hospitalization_indications", [])
        if criteria:
            policy_section = f"""
YOUR CLINICAL GUIDELINES: {policy_name}
{chr(10).join(['- ' + c for c in criteria])}

NOTE: The Insurer uses different (stricter) criteria that you cannot see.
Gather objective evidence to demonstrate clinical necessity.

"""

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS}

{stage_instruction}{policy_section}{INTERNAL_REASONING}

{prior_context}
{test_constraint}

PATIENT INFORMATION:
- Age: {state.admission.patient_demographics.age}
- Sex: {state.admission.patient_demographics.sex}
- Chief Complaint: {state.clinical_presentation.chief_complaint}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}
- Current Diagnoses: {', '.join(state.admission.preliminary_diagnoses)}

MEDICATION REQUEST (if applicable):
{json.dumps(case.get('medication_request', {}), indent=2) if case.get('medication_request') else 'No medication specified yet'}

TASK: Choose your next action from the discrete action space:
- CONTINUE: Provide additional clinical documentation to support your case
- APPEAL: Formally appeal a denial with new evidence
- ABANDON: Withdraw the request (patient will not receive this service)

CLINICAL DOCUMENTATION:
Update your clinical notes each iteration as you narrow your differential diagnosis. Notes should:
- Integrate new test results and clinical findings
- Document evolving diagnostic reasoning
- Support medical necessity for requested service
- Follow standard H&P format (concise, pertinent findings only)

Your notes should justify the requested service based on clinical data.

RESPONSE FORMAT (JSON):
{{
    "internal_rationale": {{
        "confidence_score": <float 0.0-1.0>,
        "reasoning": "<your diagnostic reasoning and why you chose this confidence level>",
        "differential_diagnoses": ["<diagnosis 1>", "<diagnosis 2>"]
    }},
    "insurer_request": {{
        "diagnosis_codes": [
            {{
                "icd10": "<ICD-10 code>",
                "description": "<diagnosis description>"
            }}
        ],
        "request_type": "diagnostic_test" or "treatment",
        "requested_service": {{
            // if diagnostic_test:
            "procedure_code": "<CPT code for test>",
            "code_type": "CPT",
            "service_name": "<specific test>",
            "test_justification": "<why this test will establish diagnosis>",
            "expected_findings": "<what results would confirm/rule out diagnosis>"

            // if treatment:
            "procedure_code": "<CPT/HCPCS/J-code>",
            "code_type": "CPT" or "HCPCS" or "J-code",
            "service_name": "<specific treatment>",
            "clinical_justification": "<why treatment is medically necessary>",
            "clinical_evidence": "<objective data supporting request>",
            "guideline_references": ["<guideline 1>", "<guideline 2>"]
        }},
        "clinical_notes": "<narrative H&P-style documentation integrating all findings to date>"
    }}
}}

IMPORTANT: The confidence_score in internal_rationale is for YOUR use only to decide whether to continue testing.
The insurer_request section contains only what you send to the payor for review."""

    # add defensive documentation requirements if applicable
    if provider_params and provider_params.get('documentation_style') == 'defensive':
        defensive_requirements = """

MANDATORY DOCUMENTATION REQUIREMENTS:
This payor has demonstrated a pattern of denying requests with brief documentation.
Historical data shows 90% denial rate for clinical notes under 500 words.

REQUIRED DOCUMENTATION LENGTH AND DETAIL:
- Minimum 500 words in clinical_notes field
- Cite specific guideline page numbers (not just guideline names)
- Anticipate potential denial reasons and preemptively address them
- Repeat critical patient history across multiple relevant sections
- Include detailed differential diagnosis with explicit reasoning for each ruling
- Document all conservative therapy trials with specific dates and outcomes
- Justify why alternative lower-cost options are inappropriate

This extensive documentation burden is necessary to avoid automatic denial."""
        return base_prompt + defensive_requirements
    
    return base_prompt

def create_unified_payor_review_prompt(state, provider_request, iteration, stage=None, level=None):
    """unified payor prompt: reviews any PA request (diagnostic or treatment)

    uses WORKFLOW_LEVELS for level-specific semantics (0-indexed):
    - Level 0 (initial_determination): triage, checklist-driven, can REQUEST_INFO
    - Level 1 (internal_reconsideration): medical director, fresh eyes, can REQUEST_INFO
    - Level 2 (independent_review): IRE, terminal, cannot REQUEST_INFO, no internal notes
    """

    # resolve level from stage name if not provided directly
    if level is None and stage:
        level = LEVEL_NAME_MAP.get(stage, 0)
    elif level is None:
        level = 0

    level_config = WORKFLOW_LEVELS.get(level, WORKFLOW_LEVELS[0])

    request_type = provider_request.get('request_type')
    requested_service = provider_request.get('requested_service', {})

    if request_type == 'diagnostic_test':
        request_summary = f"""
DIAGNOSTIC TEST PA REQUEST:
Test: {requested_service.get('service_name')}
Justification: {requested_service.get('test_justification')}
Expected Findings: {requested_service.get('expected_findings')}
"""
    else:  # treatment
        request_summary = f"""
TREATMENT PA REQUEST:
Treatment: {requested_service.get('service_name')}
Justification: {requested_service.get('clinical_justification')}
Clinical Evidence: {requested_service.get('clinical_evidence')}
Guidelines: {', '.join(requested_service.get('guideline_references', []))}
"""

    # get diagnosis codes if present
    diagnosis_codes = provider_request.get('diagnosis_codes', [])
    diagnosis_summary = ""
    if diagnosis_codes:
        diagnosis_summary = "\nDiagnosis Codes:\n" + "\n".join([
            f"  - {d.get('icd10')}: {d.get('description')}" for d in diagnosis_codes
        ])

    # inject payor policy view if available
    policy_section = ""
    if hasattr(state, 'payor_policy_view') and state.payor_policy_view:
        policy_view = state.payor_policy_view
        policy_name = policy_view.get("policy_name", "Medical Policy")
        inpatient = policy_view.get("inpatient_criteria", {})
        must_meet = inpatient.get("must_meet_one_of", [])
        prerequisites = inpatient.get("prerequisites", [])

        if must_meet or prerequisites:
            policy_section = f"""
STRICT AUDITOR MODE - YOUR POLICY: {policy_name}

PREREQUISITES (must be documented):
{chr(10).join(['- ' + p for p in prerequisites]) if prerequisites else '- None'}

INPATIENT CRITERIA - MUST MEET AT LEAST ONE:
{chr(10).join([f"{i+1}. {c.get('metric', 'Unknown')}: {c.get('threshold', c.get('range', c.get('values', c.get('description', ''))))}" for i, c in enumerate(must_meet)]) if must_meet else '- None specified'}

CRITICAL: Deny if numeric thresholds are not met exactly. Do NOT approve based on clinical judgment alone.

"""

    # level-specific payor instructions from WORKFLOW_LEVELS
    role_label = level_config["role_label"]
    review_style = level_config["review_style"]
    level_description = level_config["description"]
    can_pend = level_config["can_pend"]
    is_terminal = level_config["terminal"]
    is_independent = level_config["independent"]

    if can_pend:
        decision_options = "approved | denied | pending_info"
    else:
        decision_options = "approved | denied"

    stage_instruction = f"""LEVEL {level} - {level_config['name'].upper()} ({role_label}):
Reviewer: {role_label}
Mode: {review_style}
Decision options: {decision_options}
{level_description}

"""
    if is_terminal:
        stage_instruction += """CRITICAL: This is a TERMINAL review level. You MUST issue a final APPROVED or DENIED decision.
REQUEST_INFO (pending_info) is NOT available at this level.

"""
    if is_independent:
        stage_instruction += """NOTE: As an independent external reviewer, you do NOT have access to plan-internal notes.
Your decision must be based solely on the submitted clinical record.

"""

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS}

{stage_instruction}{policy_section}PROVIDER REQUEST:
{diagnosis_summary}

{request_summary}

Clinical Notes:
{provider_request.get('clinical_notes', 'no clinical notes provided')}

PATIENT CONTEXT:
- Age: {state.admission.patient_demographics.age}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}
- Current Diagnoses: {', '.join(state.admission.preliminary_diagnoses)}

TASK: Review PA request and approve/deny based on medical necessity and coverage criteria.

EVALUATION CRITERIA:
{"- Is diagnostic test medically necessary to establish diagnosis?" if request_type == 'diagnostic_test' else "- Is treatment medically necessary based on clinical evidence?"}
{"- Will test results meaningfully change clinical management?" if request_type == 'diagnostic_test' else "- Has step therapy been completed (if applicable)?"}
- Does request align with clinical guidelines?
- Is documentation sufficient?

RESPONSE FORMAT (JSON):
{{
    "authorization_status": "{decision_options.replace(' | ', '" or "')}",
    "denial_reason": "<specific reason if denied{' or pended' if can_pend else ''}>",
    {"'missing_documentation': ['<doc1>', '<doc2>'],  // if pending for missing info" if can_pend else ""}
    "criteria_used": "<guidelines or policies applied>",
    "reviewer_type": "{role_label}",
    "level": {level},
    "requires_peer_to_peer": true or false  // optional, set true if peer-to-peer recommended
}}"""

    return base_prompt

def create_claim_adjudication_prompt(state, service_request, cost_ref, case, phase_2_evidence=None, case_type="specialty_medication", provider_billed_amount=None):
    """create task prompt for claim review - works for all PA types

    Args:
        provider_billed_amount: the actual amount the Provider billed (from their claim submission)
            If provided, use this instead of cost_ref defaults
    """
    import json
    from src.models.schemas import CaseType

    # build comprehensive clinical documentation from phase 2 evidence
    clinical_doc_parts = []

    # initial clinical presentation
    if state.clinical_presentation:
        clinical_doc_parts.append("INITIAL PRESENTATION:")
        clinical_doc_parts.append(f"Chief Complaint: {state.clinical_presentation.chief_complaint}")
        if state.clinical_presentation.history_of_present_illness:
            clinical_doc_parts.append(f"History: {state.clinical_presentation.history_of_present_illness}")
        if state.clinical_presentation.physical_exam_findings:
            clinical_doc_parts.append(f"Physical Exam: {state.clinical_presentation.physical_exam_findings}")
        clinical_doc_parts.append("")

    # test results from phase 2
    if phase_2_evidence and phase_2_evidence.get('test_results'):
        clinical_doc_parts.append("DIAGNOSTIC WORKUP COMPLETED IN PHASE 2:")
        for test_name, test_data in phase_2_evidence['test_results'].items():
            # test_data can be either a string or dict
            if isinstance(test_data, dict):
                finding = test_data.get('finding', 'completed')
            else:
                finding = test_data
            clinical_doc_parts.append(f"- {test_name}: {finding}")
        clinical_doc_parts.append("")

    # approved treatment request rationale from phase 2
    if phase_2_evidence and phase_2_evidence.get('approved_request'):
        approved_req = phase_2_evidence['approved_request']
        clinical_doc_parts.append("PROVIDER TREATMENT JUSTIFICATION (from approved PA request):")
        clinical_doc_parts.append(f"Diagnostic Confidence: {approved_req.get('confidence', 'N/A')}")
        clinical_doc_parts.append(f"Rationale: {approved_req.get('confidence_rationale', 'N/A')}")
        if approved_req.get('differential_diagnoses'):
            clinical_doc_parts.append(f"Differential Diagnoses: {', '.join(approved_req['differential_diagnoses'])}")

        req_details = approved_req.get('request_details', {})
        if req_details.get('treatment_justification'):
            clinical_doc_parts.append(f"Treatment Justification: {req_details['treatment_justification']}")
        if req_details.get('clinical_evidence'):
            clinical_doc_parts.append(f"Clinical Evidence: {req_details['clinical_evidence']}")
        if req_details.get('guideline_references'):
            clinical_doc_parts.append(f"Guidelines Cited: {', '.join(req_details['guideline_references'])}")
        clinical_doc_parts.append("")

    # service request rationale
    if service_request.get('clinical_rationale'):
        clinical_doc_parts.append("SERVICE REQUEST RATIONALE:")
        clinical_doc_parts.append(service_request['clinical_rationale'])
        clinical_doc_parts.append("")

    # static lab data if available
    static_labs = case.get('available_test_results', {}).get('labs', {})
    if static_labs:
        clinical_doc_parts.append("STATIC LAB DATA:")
        clinical_doc_parts.append(json.dumps(static_labs, indent=2))

    combined_clinical_doc = "\n".join(clinical_doc_parts) if clinical_doc_parts else "No documentation provided"

    # build service details based on PA type
    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_name = service_request.get('medication_name', 'medication')
        service_details = f"""CLAIM SUBMITTED:
- Medication: {service_request.get('medication_name')}
- Dosage Administered: {service_request.get('dosage')}"""
        # use provider's actual billed amount if available, otherwise default to cost_ref
        if provider_billed_amount is not None:
            total_billed = provider_billed_amount
        else:
            total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
        task_desc = "Review CLAIM for specialty medication (Phase 3)"
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""CLAIM SUBMITTED:
- Procedure/Service: {service_name}
- Clinical Indication: {service_request.get('clinical_indication', service_request.get('treatment_justification', 'N/A'))}"""
        # use provider's actual billed amount if available, otherwise default to cost_ref
        if provider_billed_amount is not None:
            total_billed = provider_billed_amount
        else:
            total_billed = cost_ref.get('procedure_cost', 7800)
        task_desc = "Review CLAIM for procedure/service (Phase 3)"

    return f"""TASK: {task_desc}

CRITICAL CONTEXT: This is Phase 3 - CLAIM ADJUDICATION after treatment already delivered.
The PA was approved in Phase 2, but you can still deny payment if documentation is insufficient.

PATIENT:
- Age: {state.admission.patient_demographics.age}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}

{service_details}
- Amount Billed: ${total_billed:.2f}

PA APPROVAL RATIONALE (from Phase 2):
{state.medication_authorization.criteria_used if state.medication_authorization else 'PA approved'}

CLINICAL DOCUMENTATION:
{combined_clinical_doc}

Your task: Review claim and decide on PAYMENT: approve, reject, or pend.

DECISION GUIDANCE:
- Use APPROVED: documentation complete, claim valid, treatment matches PA
- Use REJECTED: service not covered OR clearly contradicts PA approval OR not medically necessary
- Use PENDED: minor documentation gaps, billing clarifications needed, want more info before deciding

STRATEGIC CONSIDERATIONS (based on your behavioral parameters):
- PENDED claims have high abandonment rate (provider may give up without resubmitting)
- REJECTED claims trigger formal appeals (costly to defend, time-consuming)
- Excessive REJECTIONS trigger regulatory scrutiny and bad publicity
- PENDED claims are NOT tracked by regulators (not counted in denial rate metrics)
- Use PEND for regulatory arbitrage: delay payment without formal denial

RESPONSE FORMAT (JSON):
{{
    "claim_status": "approved" | "rejected" | "pended",

    // if approved:
    "approved_amount": <dollar amount>,

    // if rejected (formal denial):
    "rejection_reason": "<specific reason for denial>",
    "denial_code": "<standard reason code>",
    "appeals_rights_notice": true,

    // if pended (request for info):
    "pend_reason": "<what documentation is unclear/missing>",
    "requested_documents": ["<doc1>", "<doc2>"],
    "resubmission_deadline_days": 30,

    "criteria_used": "<billing guidelines>",
    "reviewer_type": "Claims adjudicator" | "Medical reviewer"
}}"""


def create_provider_claim_submission_prompt(state, service_request, cost_ref, phase_2_evidence=None, case_type="specialty_medication", coding_options=None):
    """create provider claim submission prompt (phase 3) - works for all PA types

    Args:
        coding_options: list of dicts with diagnosis/payment choices for DRG upcoding scenarios
            Each option should have: diagnosis, icd10, payment, defensibility, justification
    """
    from src.models.schemas import CaseType

    # build clinical documentation
    clinical_doc_parts = []

    if phase_2_evidence and phase_2_evidence.get('test_results'):
        clinical_doc_parts.append("DIAGNOSTIC WORKUP RESULTS:")
        for test_name, test_data in phase_2_evidence['test_results'].items():
            # test_data can be either a string or dict
            if isinstance(test_data, dict):
                finding = test_data.get('finding', 'completed')
            else:
                finding = test_data
            clinical_doc_parts.append(f"- {test_name}: {finding}")
        clinical_doc_parts.append("")

    if phase_2_evidence and phase_2_evidence.get('approved_request'):
        approved_req = phase_2_evidence['approved_request']
        req_details = approved_req.get('request_details', {})
        if req_details.get('treatment_justification'):
            clinical_doc_parts.append(f"TREATMENT JUSTIFICATION: {req_details['treatment_justification']}")
        if req_details.get('clinical_evidence'):
            clinical_doc_parts.append(f"CLINICAL EVIDENCE: {req_details['clinical_evidence']}")
        clinical_doc_parts.append("")

    combined_clinical_doc = "\n".join(clinical_doc_parts) if clinical_doc_parts else "No additional documentation"

    # build service details based on PA type
    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_name = service_request.get('medication_name', 'medication')
        service_details = f"""TREATMENT DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage Administered: {service_request.get('dosage')}
- Route: {service_request.get('route', 'N/A')}
- Frequency: {service_request.get('frequency', 'N/A')}"""
    else:
        # procedures, cardiac testing, imaging
        # extract service_name from new schema, with fallback to old schema
        service_name = service_request.get('service_name', service_request.get('treatment_name', service_request.get('procedure_name', 'procedure')))
        service_details = f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}
- Clinical Indication: {service_request.get('clinical_indication', service_request.get('treatment_justification', 'N/A'))}"""

    # build coding & reimbursement section
    if coding_options and len(coding_options) > 0:
        # grey zone case with multiple coding options - let Provider choose
        coding_section_parts = ["CODING & REIMBURSEMENT OPTIONS:"]
        coding_section_parts.append("You must select ONE diagnosis code for this claim based on clinical documentation:")
        coding_section_parts.append("")

        for i, option in enumerate(coding_options, 1):
            coding_section_parts.append(f"OPTION {i}: {option.get('icd10', 'N/A')} - {option.get('diagnosis', 'Unknown')}")
            coding_section_parts.append(f"  - Payment: ${option.get('payment', 0):,.2f}")
            coding_section_parts.append(f"  - DRG: {option.get('drg_code', 'N/A')}")
            coding_section_parts.append("")

        coding_section_parts.append("DECISION GUIDANCE:")
        coding_section_parts.append("- Select the diagnosis code that best reflects the clinical documentation")
        coding_section_parts.append("- Higher-paying codes require stronger clinical evidence to avoid audit clawback")
        coding_section_parts.append("- Your billed amount MUST match the payment for your chosen diagnosis code")
        coding_section = "\n".join(coding_section_parts)
    else:
        # standard case with fixed billing
        if case_type == CaseType.SPECIALTY_MEDICATION:
            total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
            coding_section = f"""BILLING INFORMATION:
- Drug Acquisition Cost: ${cost_ref.get('drug_acquisition_cost', 7800):.2f}
- Administration Fee: ${cost_ref.get('administration_fee', 150):.2f}
- Total Amount Billed: ${total_billed:.2f}"""
        else:
            total_billed = cost_ref.get('procedure_cost', 7800)
            coding_section = f"""BILLING INFORMATION:
- Procedure Cost: ${total_billed:.2f}"""

    return f"""TASK: Submit CLAIM for reimbursement (Phase 3)

CONTEXT: You have completed treating the patient. PA was approved in Phase 2.
Now you must submit a claim to receive payment for services rendered.

{service_details}

PA APPROVAL FROM PHASE 2:
- Status: {state.medication_authorization.authorization_status if state.medication_authorization else 'approved'}
- Reviewer: {state.medication_authorization.reviewer_type if state.medication_authorization else 'AI algorithm'}
- Criteria: {state.medication_authorization.criteria_used if state.medication_authorization else 'Medical necessity guidelines'}

CLINICAL DOCUMENTATION:
{combined_clinical_doc}

{coding_section}

CRITICAL GUARDRAILS:
1. You must ONLY bill for the service listed in 'SERVICE DELIVERED' above - do NOT invent procedures.
2. Your diagnosis code determines your billed amount - choose from the options above.
3. Do not fabricate clinical events that did not occur.

Your task: Submit claim with your chosen diagnosis code and corresponding billed amount.

RESPONSE FORMAT (JSON):
{{
    "claim_submission": {{
        "diagnosis_codes": [
            {{
                "icd10": "<ICD-10 code>",
                "description": "<diagnosis description>"
            }}
        ],
        "procedure_codes": [
            {{
                "code": "<CPT/HCPCS/J-code>",
                "code_type": "CPT" or "HCPCS" or "J-code",
                "description": "<service description>",
                "quantity": <number>,
                "amount_billed": <dollar amount per unit>
            }}
        ],
        "total_amount_billed": <total dollar amount>,
        "clinical_evidence": "<objective data: labs, imaging, vitals>",
        "clinical_notes": "<narrative documentation from Phase 2>",
        "pa_reference": "<reference to phase 2 PA approval>",
        "supporting_evidence": ["<objective finding 1>", "<objective finding 2>", ...]
    }}
}}"""


def create_provider_claim_appeal_decision_prompt(state, denial_reason, service_request, case_type="specialty_medication"):
    """create provider decision prompt after claim DENIED - uses discrete action space

    provider actions: CONTINUE (augment record), APPEAL (escalate to next level), ABANDON (exit)
    """
    from src.models.schemas import CaseType

    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_details = f"""SERVICE:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
    else:
        service_name = service_request.get('service_name', service_request.get('treatment_name', service_request.get('procedure_name', 'procedure')))
        service_details = f"""SERVICE:
- Procedure/Service: {service_name}"""

    return f"""CLAIM DENIED - CHOOSE YOUR ACTION

SITUATION:
- Treatment was provided and PA was previously approved
- Claim has been DENIED in claims adjudication

DENIAL REASON:
{denial_reason}

{service_details}

YOUR DISCRETE ACTION SPACE:
1. CONTINUE: Augment the clinical record with additional evidence at current level
   - Stay in same review lane, provide more documentation
   - Reviewer will reconsider with supplemented record

2. APPEAL: Escalate to next administrative authority
   - Changes who reviews the case
   - Triggers next procedural layer (e.g., independent review)

3. ABANDON: Exit the dispute
   - Accept the denial, stop contesting
   - Patient responsibility or write-off

CONSIDERATIONS:
- PA was approved in Phase 2 - you have precedent
- Was denial based on documentation gaps? (CONTINUE may help)
- Was denial based on medical necessity interpretation? (APPEAL may change outcome)
- Is the administrative burden worth continued pursuit? (ABANDON is always an option)

RESPONSE FORMAT (JSON):
{{
    "action": "CONTINUE" | "APPEAL" | "ABANDON",
    "rationale": "<why this action given your behavioral parameters>",
    "additional_evidence": ["<evidence1>", ...] // if CONTINUE
}}"""


def create_provider_pend_response_prompt(state, pend_decision, service_request, pend_iteration, case_type="specialty_medication"):
    """create provider decision prompt after claim PENDED (REQUEST_INFO) - uses discrete action space

    provider actions: CONTINUE (provide requested docs), ABANDON (exit)
    note: at pend stage, APPEAL is not yet available - must first respond to REQUEST_INFO
    """
    from src.models.schemas import CaseType

    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_details = f"""SERVICE:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE:
- Procedure/Service: {service_name}"""

    return f"""CLAIM PENDED (REQUEST_INFO) - Iteration {pend_iteration}/{MAX_REQUEST_INFO_PER_LEVEL}

SITUATION:
- Claim status: PENDED (Request for Information)
- Treatment was provided, PA was previously approved

REQUEST_INFO REASON:
{pend_decision.get('pend_reason', 'Additional documentation requested')}

REQUESTED DOCUMENTATION:
{', '.join(pend_decision.get('requested_documents', ['Additional clinical documentation']))}

{service_details}

YOUR DISCRETE ACTION SPACE:
1. CONTINUE: Provide the requested documentation
   - Stay in same review lane, augment the record
   - Reviewer will reconsider with supplemented information
   - Note: Max {MAX_REQUEST_INFO_PER_LEVEL} REQUEST_INFO cycles per level

2. ABANDON: Exit the dispute
   - Accept non-payment, stop contesting
   - Patient becomes responsible or write-off

CONSIDERATIONS:
- PA was approved in Phase 2 - medical necessity was established
- Can you provide the requested documentation?
- Is the administrative burden worth continued pursuit?
- Iteration {pend_iteration}/{MAX_REQUEST_INFO_PER_LEVEL} at this level

RESPONSE FORMAT (JSON):
{{
    "action": "CONTINUE" | "ABANDON",
    "rationale": "<why this action given your behavioral parameters>",
    "documents_to_add": ["<doc1>", "<doc2>", ...] // if CONTINUE
}}"""


def create_provider_claim_resubmission_prompt(state, pend_decision, service_request, phase_2_evidence=None, case_type="specialty_medication"):
    """create provider resubmission packet prompt (responding to pended claim) - works for all PA types"""
    from src.models.schemas import CaseType

    # build comprehensive evidence
    evidence_parts = []

    if phase_2_evidence and phase_2_evidence.get('test_results'):
        evidence_parts.append("DIAGNOSTIC TEST RESULTS FROM PHASE 2:")
        for test_name, test_data in phase_2_evidence['test_results'].items():
            if isinstance(test_data, dict):
                finding = test_data.get('finding', 'completed')
            else:
                finding = test_data
            evidence_parts.append(f"- {test_name}: {finding}")
        evidence_parts.append("")

    if phase_2_evidence and phase_2_evidence.get('approved_request'):
        approved_req = phase_2_evidence['approved_request']
        req_details = approved_req.get('request_details', {})
        if req_details.get('clinical_evidence'):
            evidence_parts.append(f"ORIGINAL CLINICAL EVIDENCE:\n{req_details['clinical_evidence']}")
        if req_details.get('guideline_references'):
            evidence_parts.append(f"\nGuidelines: {', '.join(req_details['guideline_references'])}")
        evidence_parts.append("")

    combined_evidence = "\n".join(evidence_parts) if evidence_parts else "See original claim documentation"

    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_details = f"""TREATMENT DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}"""

    return f"""TASK: Submit RESUBMISSION PACKET responding to pended claim (Phase 3)

CONTEXT: Your claim was PENDED (not rejected). Insurer requested additional documentation.
You have decided to resubmit rather than abandon the claim.

PEND REASON:
{pend_decision.get('pend_reason', 'Additional documentation requested')}

REQUESTED DOCUMENTS:
{', '.join(pend_decision.get('requested_documents', ['Additional clinical documentation']))}

{service_details}

AVAILABLE EVIDENCE:
{combined_evidence}

Your task: Prepare resubmission packet addressing the specific pend reason and providing requested documents.

RESPONSE FORMAT (JSON):
{{
    "resubmission_packet": {{
        "cover_letter": "<brief explanation addressing pend reason>",
        "additional_documentation": ["<doc1>", "<doc2>", ...],
        "clinical_notes_addendum": "<any additional clinical details>",
        "billing_clarifications": "<if pend was about billing>",
        "pa_reference": "<reference to phase 2 PA approval>"
    }}
}}"""


def create_provider_claim_appeal_prompt(state, denial_reason, service_request, phase_2_evidence=None, case_type="specialty_medication", appeal_history=None):
    """create provider claim appeal submission prompt - works for all PA types"""
    from src.models.schemas import CaseType

    # build appeal history warning
    history_text = ""
    if appeal_history:
        history_text = "\n\nPREVIOUS FAILED APPEALS (DO NOT REPEAT THESE ARGUMENTS):\n" + "\n".join(appeal_history) + "\n"

    # build comprehensive evidence
    evidence_parts = []

    if phase_2_evidence and phase_2_evidence.get('test_results'):
        evidence_parts.append("DIAGNOSTIC TEST RESULTS:")
        for test_name, test_data in phase_2_evidence['test_results'].items():
            # test_data can be either a string or dict
            if isinstance(test_data, dict):
                finding = test_data.get('finding', 'completed')
            else:
                finding = test_data
            evidence_parts.append(f"- {test_name}: {finding}")
        evidence_parts.append("")

    if phase_2_evidence and phase_2_evidence.get('approved_request'):
        approved_req = phase_2_evidence['approved_request']
        evidence_parts.append("ORIGINAL PA JUSTIFICATION:")
        req_details = approved_req.get('request_details', {})
        if req_details.get('clinical_evidence'):
            evidence_parts.append(req_details['clinical_evidence'])
        if req_details.get('guideline_references'):
            evidence_parts.append(f"\nGuidelines: {', '.join(req_details['guideline_references'])}")
        evidence_parts.append("")

    combined_evidence = "\n".join(evidence_parts) if evidence_parts else "See original PA documentation"

    # build service details based on PA type
    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_details = f"""TREATMENT DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}
- Clinical Indication: {service_request.get('icd10_codes', [])}"""
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}
- Clinical Indication: {service_request.get('clinical_indication', service_request.get('treatment_justification', 'N/A'))}"""

    return f"""TASK: Appeal DENIED CLAIM (Phase 3)

SITUATION:
- Treatment was delivered with PA approval from Phase 2
- Claim was denied despite PA approval
- You are appealing to recover payment

DENIAL REASON:
{denial_reason}
{history_text}
{service_details}

SUPPORTING EVIDENCE:
{combined_evidence}

PA APPROVAL REFERENCE:
- PA was APPROVED in Phase 2 by {state.medication_authorization.reviewer_type if state.medication_authorization else 'AI algorithm'}
- Criteria used: {state.medication_authorization.criteria_used if state.medication_authorization else 'Medical necessity'}

Your task: Submit appeal with evidence addressing the specific denial reason.
{f'CRITICAL: This is appeal #{len(appeal_history) + 1}. Review the PREVIOUS FAILED APPEALS above and use DIFFERENT arguments.' if appeal_history else ''}

RESPONSE FORMAT (JSON):
{{
    "appeal_letter": {{
        "denial_addressed": "<how you address the specific denial reason>",
        "additional_documentation": ["<new evidence item 1>", "<new evidence item 2>", ...],
        "pa_approval_reference": "<reference to phase 2 approval>",
        "clinical_necessity_reaffirmation": "<why treatment was medically necessary>",
        "billing_accuracy_verification": "<confirm billing codes and amounts are correct>",
        "requested_action": "full payment" or "partial payment" or "reconsideration"
    }}
}}"""


def create_payor_claim_appeal_review_prompt(state, appeal_letter, denial_reason, service_request, cost_ref, phase_2_evidence=None, case_type="specialty_medication"):
    """create payor claim appeal review prompt - works for all PA types"""
    import json
    from src.models.schemas import CaseType

    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_details = f"""TREATMENT DETAILS:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
        total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE DETAILS:
- Procedure/Service: {service_name}"""
        total_billed = cost_ref.get('procedure_cost', 7800)

    return f"""TASK: Review CLAIM APPEAL (Phase 3)

CONTEXT: Provider is appealing your claim denial. They already delivered treatment with PA approval.

ORIGINAL DENIAL REASON:
{denial_reason}

PROVIDER'S APPEAL:
{json.dumps(appeal_letter, indent=2)}

{service_details}
- Amount in dispute: ${total_billed:.2f}

PA HISTORY:
- PA Status in Phase 2: {state.medication_authorization.authorization_status if state.medication_authorization else 'approved'}
- PA Criteria Used: {state.medication_authorization.criteria_used if state.medication_authorization else 'Medical necessity'}

DECISION FACTORS:
- Does appeal address the denial reason adequately?
- Is additional documentation sufficient?
- Was original denial justified or was it an error?
- Cost of continuing dispute vs. approving payment?

TRADE-OFFS:
- Upholding denial: Save ${total_billed:.2f} but risk provider escalation
- Approving appeal: Pay ${total_billed:.2f} but maintain provider relationship
- Ongoing appeals cost administrative resources

Your task: Review appeal and decide to approve payment, continue denial, or request more documentation.

RESPONSE FORMAT (JSON):
{{
    "appeal_outcome": "approved" or "denied" or "partial",
    "approved_amount": <dollar amount if approved/partial, null if denied>,
    "denial_reason": "<reason if appeal denied>",
    "additional_documentation_requested": ["<item 1>", ...] or [],
    "reviewer_type": "Medical director" or "Appeals coordinator",
    "rationale": "<why you made this decision>"
}}"""


def create_payor_claim_resubmission_review_prompt(state, resubmission_packet, pend_decision, service_request, cost_ref, pend_iteration, case_type="specialty_medication"):
    """create payor resubmission review prompt (after provider resubmits pended claim) - works for all PA types"""
    import json
    from src.models.schemas import CaseType

    if case_type == CaseType.SPECIALTY_MEDICATION:
        service_details = f"""TREATMENT DETAILS:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
        claim_amount = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE DETAILS:
- Procedure/Service: {service_name}"""
        claim_amount = cost_ref.get('procedure_cost', 7800)

    # check if at pend limit (must make final decision)
    at_pend_limit = pend_iteration >= MAX_REQUEST_INFO_PER_LEVEL

    if at_pend_limit:
        action_section = """YOUR DISCRETE ACTION SPACE (FINAL DECISION REQUIRED):
You have reached the maximum REQUEST_INFO cycles ({0}/{0}). You MUST make a final decision.

1. APPROVE: Documentation sufficient, authorize payment
2. DENY: Formally deny the claim

NOTE: REQUEST_INFO (pend again) is NOT available at this iteration.""".format(MAX_REQUEST_INFO_PER_LEVEL)

        response_format = """RESPONSE FORMAT (JSON):
{{
    "claim_status": "approved" | "rejected",

    // if approved:
    "approved_amount": <dollar amount>,

    // if rejected:
    "rejection_reason": "<specific reason for formal denial>",
    "denial_code": "<standard reason code>",

    "criteria_used": "<billing guidelines>",
    "reviewer_type": "Claims adjudicator" | "Medical reviewer",
    "rationale": "<why you chose approve/reject>"
}}"""
    else:
        action_section = """YOUR DISCRETE ACTION SPACE:
1. APPROVE: Documentation now sufficient, authorize payment
2. DENY: Formally deny the claim
3. REQUEST_INFO (pend): Request additional documentation (max {0} cycles per level)

Current iteration: {1}/{0}""".format(MAX_REQUEST_INFO_PER_LEVEL, pend_iteration)

        response_format = """RESPONSE FORMAT (JSON):
{{
    "claim_status": "approved" | "rejected" | "pended",

    // if approved:
    "approved_amount": <dollar amount>,

    // if rejected:
    "rejection_reason": "<specific reason for formal denial>",
    "denial_code": "<standard reason code>",

    // if pended again:
    "pend_reason": "<NEW reason - must be different from previous pend>",
    "requested_documents": ["<different docs than before>"],

    "criteria_used": "<billing guidelines>",
    "reviewer_type": "Claims adjudicator" | "Medical reviewer",
    "rationale": "<why you chose approve/reject/pend>"
}}"""

    return f"""TASK: Review RESUBMITTED CLAIM (Phase 3 - Pend Iteration {pend_iteration}/{MAX_REQUEST_INFO_PER_LEVEL})

CONTEXT: Provider resubmitted claim in response to your pend request. You previously pended (not rejected) this claim.

ORIGINAL PEND REASON:
{pend_decision.get('pend_reason', 'Additional documentation requested')}

REQUESTED DOCUMENTS:
{', '.join(pend_decision.get('requested_documents', ['Additional clinical documentation']))}

PROVIDER'S RESUBMISSION PACKET:
{json.dumps(resubmission_packet, indent=2)}

{service_details}
- Claim amount: ${claim_amount:.2f}

PA HISTORY:
- PA Status in Phase 2: {state.medication_authorization.authorization_status if state.medication_authorization else 'approved'}
- PA Criteria Used: {state.medication_authorization.criteria_used if state.medication_authorization else 'Medical necessity'}

DECISION FACTORS:
- Does resubmission address your pend reason adequately?
- Is the additional documentation sufficient?

{action_section}

{response_format}"""
