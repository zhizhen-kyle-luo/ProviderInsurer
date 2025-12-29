# simulation configuration
MAX_ITERATIONS = 3  # phase 2: Initial Claim -> Appeal L1 -> Appeal L2
MAX_PHASE_3_ITERATIONS = 10  # phase 3: claims adjudication max appeal iterations
CONFIDENCE_THRESHOLD = 0.9
NOISE_PROBABILITY = 0.15

# phase 3 claim adjudication costs
CLAIM_REJECTION_COST = 100.0          # formal appeal cost
CLAIM_REJECTION_SUCCESS_RATE = 0.75   # 75% overturn rate

CLAIM_PEND_RESUBMIT_COST = 25.0       # resubmission admin cost
CLAIM_PEND_SUCCESS_RATE = 0.40        # 40% approval after resubmit

MAX_PEND_ITERATIONS = 10               # safety limit to prevent infinite loops

# confidence score guidelines for provider agent
CONFIDENCE_GUIDELINES = """
CONFIDENCE SCORE (0.0-1.0):
represents your diagnostic certainty for proposing treatment

0.0-0.3: very uncertain diagnosis
  - need basic diagnostic workup (CBC, basic metabolic panel, vital signs)
  - multiple differentials remain plausible
  - insufficient data to narrow diagnosis

0.3-0.6: working diagnosis forming
  - initial test results available
  - narrowing differential based on objective findings
  - need confirmatory testing to establish diagnosis

0.6-0.9: strong clinical suspicion
  - key diagnostic criteria met
  - may need confirmatory testing (imaging, biopsy, specialized labs)
  - high probability of specific diagnosis but not definitive

0.9-1.0: confident diagnosis
  - diagnostic criteria satisfied per clinical guidelines
  - objective evidence supports diagnosis
  - ready to propose definitive treatment
  - evidence sufficient for treatment PA request

DECISION LOGIC:
- if confidence < 0.9: request diagnostic test PA to build confidence
- if confidence >= 0.9: request treatment PA (medication, procedure, admission)

IMPORTANT: generate your own confidence score based on available clinical data
"""

# default behavioral parameters
DEFAULT_PROVIDER_PARAMS = {
    'patient_care_weight': 'high',
    'documentation_style': 'moderate',
    'risk_tolerance': 'moderate',
    'ai_adoption': 'moderate'
}

DEFAULT_PAYOR_PARAMS = {
    'cost_focus': 'moderate',
    'ai_reliance': 'high',
    'denial_threshold': 'moderate',
    'time_horizon': 'short-term'
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
    'ai_adoption': {
        'low': 'manual documentation, minimal AI assistance, traditional clinical writing',
        'moderate': 'AI assists with templates and suggestions, provider reviews and edits all content',
        'high': 'heavily AI-generated documentation with minimal human editing, efficiency-focused'
    }
}

PAYOR_PARAM_DEFINITIONS = {
    'cost_focus': {
        'low': 'approve most medically reasonable requests, minimize denials and administrative friction',
        'moderate': 'balance cost control with medical necessity, follow guidelines strictly',
        'high': 'aggressive cost reduction, deny unless clearly necessary, challenge borderline cases'
    },
    'ai_reliance': {
        'low': 'human medical directors review all PA requests, AI used only for data retrieval',
        'moderate': 'AI flags questionable cases, humans make all final authorization decisions',
        'high': 'AI makes most routine decisions autonomously, humans only review appeals and complex cases'
    },
    'denial_threshold': {
        'low': 'liberal interpretation of medical necessity, approve if clinically reasonable',
        'moderate': 'strictly follow published guidelines, require documented medical necessity',
        'high': 'conservative interpretation, require extensive documentation even for guideline-supported cases'
    },
    'time_horizon': {
        'short-term': 'minimize immediate costs, deny expensive treatments, ignore long-term member health consequences',
        'medium-term': 'balance quarterly results with member retention, consider 1-2 year outcomes',
        'long-term': 'invest in prevention and member satisfaction, consider multi-year cost-effectiveness'
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
    ai_def = PROVIDER_PARAM_DEFINITIONS['ai_adoption'][params['ai_adoption']]

    return f"""You are a PROVIDER agent (hospital/clinic) in Fee-for-Service Medicare Advantage.

BEHAVIORAL PARAMETERS:
- Patient care priority: {params['patient_care_weight']} ({patient_care_def})
- Documentation style: {params['documentation_style']} ({doc_style_def})
- Risk tolerance: {params['risk_tolerance']} ({risk_def})
- AI adoption: {params['ai_adoption']} ({ai_def})

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
    cost_focus_def = PAYOR_PARAM_DEFINITIONS['cost_focus'][params['cost_focus']]
    ai_reliance_def = PAYOR_PARAM_DEFINITIONS['ai_reliance'][params['ai_reliance']]
    denial_threshold_def = PAYOR_PARAM_DEFINITIONS['denial_threshold'][params['denial_threshold']]
    time_horizon_def = PAYOR_PARAM_DEFINITIONS['time_horizon'][params['time_horizon']]

    base_prompt = f"""You are an INSURER agent (Medicare Advantage plan) managing costs using AI systems.

BEHAVIORAL PARAMETERS:
- Cost focus: {params['cost_focus']} ({cost_focus_def})
- AI reliance: {params['ai_reliance']} ({ai_reliance_def})
- Denial threshold: {params['denial_threshold']} ({denial_threshold_def})
- Time horizon: {params['time_horizon']} ({time_horizon_def})

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

    # add hostile instructions if cost focus is high
    if params.get('cost_focus') == 'high':
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
    import json

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
    import json
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

def create_unified_provider_request_prompt(state, case, iteration, prior_iterations, provider_params=None):
    """unified provider prompt: decides diagnostic test PA or treatment PA based on confidence"""
    import json

    # format prior iterations for context
    prior_context = ""
    completed_tests = []
    if prior_iterations:
        prior_context = "PRIOR ITERATIONS:\n"
        for i, iter_data in enumerate(prior_iterations, 1):
            prior_context += f"\nIteration {i}:\n"
            prior_context += f"  Your request: {iter_data['provider_request_type']}\n"
            prior_context += f"  Your confidence: {iter_data['provider_confidence']}\n"
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
        test_constraint = f"\nIMPORTANT CONSTRAINT: The following tests have been APPROVED and COMPLETED. DO NOT request them again:\n- {', '.join(completed_tests)}\nUse the results above to update your confidence. If confidence is now >= {CONFIDENCE_THRESHOLD}, request TREATMENT (not more tests).\n"

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS}

{CONFIDENCE_GUIDELINES}

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

TASK: Based on your current diagnostic confidence, decide your next action:
- If confidence < {CONFIDENCE_THRESHOLD}: Request diagnostic test PA to build confidence
- If confidence >= {CONFIDENCE_THRESHOLD}: Request treatment PA (medication, procedure, admission)

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

def create_unified_payor_review_prompt(state, provider_request, iteration):
    """unified payor prompt: reviews any PA request (diagnostic or treatment)"""
    import json

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

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS}

PROVIDER REQUEST:
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
    "authorization_status": "approved" or "denied",
    "denial_reason": "<specific reason if denied, including what's missing or why unnecessary>",
    "criteria_used": "<guidelines or policies applied>",
    "reviewer_type": "AI algorithm" or "Nurse reviewer" or "Medical director"
}}"""
    
    return base_prompt

def create_claim_adjudication_prompt(state, service_request, cost_ref, case, phase_2_evidence=None, pa_type="specialty_medication", provider_billed_amount=None):
    """create task prompt for claim review - works for all PA types

    Args:
        provider_billed_amount: the actual amount the Provider billed (from their claim submission)
            If provided, use this instead of cost_ref defaults
    """
    import json
    from src.models.schemas import PAType

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
    if pa_type == PAType.SPECIALTY_MEDICATION:
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


def create_provider_claim_submission_prompt(state, service_request, cost_ref, phase_2_evidence=None, pa_type="specialty_medication", coding_options=None):
    """create provider claim submission prompt (phase 3) - works for all PA types

    Args:
        coding_options: list of dicts with diagnosis/payment choices for DRG upcoding scenarios
            Each option should have: diagnosis, icd10, payment, defensibility, justification
    """
    import json
    from src.models.schemas import PAType

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
    if pa_type == PAType.SPECIALTY_MEDICATION:
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
        if pa_type == PAType.SPECIALTY_MEDICATION:
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


def create_provider_claim_appeal_decision_prompt(state, denial_reason, service_request, cost_ref, pa_type="specialty_medication"):
    """create provider decision prompt after claim REJECTED (formal denial) - works for all PA types

    note: this is for REJECTED claims only. PENDED claims use create_provider_pend_response_prompt
    """
    from src.models.schemas import PAType

    if pa_type == PAType.SPECIALTY_MEDICATION:
        service_name = service_request.get('medication_name', 'medication')
        service_details = f"""TREATMENT DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
        total_billed = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
    else:
        # extract service_name from new schema, with fallback to old schema
        service_name = service_request.get('service_name', service_request.get('treatment_name', service_request.get('procedure_name', 'procedure')))
        service_details = f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}"""
        total_billed = cost_ref.get('procedure_cost', 7800)

    return f"""CRITICAL DECISION: CLAIM WAS REJECTED (Phase 3)

SITUATION:
- You already treated the patient and incurred costs
- PA was APPROVED in Phase 2, but claim was FORMALLY REJECTED in Phase 3
- Amount at stake: ${total_billed:.2f}

REJECTION REASON:
{denial_reason}

{service_details}

YOUR OPTIONS:
1. WRITE-OFF: Absorb the cost yourself (direct financial loss to practice)
2. APPEAL: Fight the formal rejection with additional documentation
   - Cost: ${CLAIM_REJECTION_COST:.2f} (formal appeal process)
   - Historical success rate: {int(CLAIM_REJECTION_SUCCESS_RATE * 100)}% (appeals overturn rejections)
   - Time: 30-60 days for review
3. BILL PATIENT: Transfer cost to patient (often uncollectible, damages relationship)

FINANCIAL IMPACT:
- Write-off: You lose ${total_billed:.2f} immediately
- Appeal: Admin cost ${CLAIM_REJECTION_COST:.2f}, {int(CLAIM_REJECTION_SUCCESS_RATE * 100)}% chance to recover ${total_billed:.2f}
- Bill Patient: Patient may not pay, may damage relationship and reputation

APPEAL SUCCESS FACTORS:
- Was rejection based on documentation? (Appeal likely to succeed)
- Was rejection based on medical necessity? (Appeal uncertain)
- Was rejection based on billing errors? (Appeal likely to succeed if correctable)
- PA was already approved, so you have precedent on your side

Expected value of appeal: ${total_billed * CLAIM_REJECTION_SUCCESS_RATE - CLAIM_REJECTION_COST:.2f}

Your task: Decide how to handle this rejected claim based on your behavioral parameters.

RESPONSE FORMAT (JSON):
{{
    "decision": "write_off" or "appeal" or "bill_patient",
    "rationale": "<why you chose this option given your incentives>",
    "expected_outcome": "<what you expect to happen>",
    "admin_time_investment": <hours if appealing, 0 otherwise>
}}"""


def create_provider_pend_response_prompt(state, pend_decision, service_request, cost_ref, pend_iteration, pa_type="specialty_medication"):
    """create provider decision prompt after claim pended (RFI) - works for all PA types"""
    from src.models.schemas import PAType

    if pa_type == PAType.SPECIALTY_MEDICATION:
        service_name = service_request.get('medication_name', 'medication')
        service_details = f"""TREATMENT DELIVERED:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
        claim_amount = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE DELIVERED:
- Procedure/Service: {service_name}"""
        claim_amount = cost_ref.get('procedure_cost', 7800)

    expected_value_resubmit = claim_amount * CLAIM_PEND_SUCCESS_RATE - CLAIM_PEND_RESUBMIT_COST

    return f"""CLAIM PENDED - DECISION REQUIRED (Iteration {pend_iteration}/{MAX_PEND_ITERATIONS})

SITUATION:
- Claim amount: ${claim_amount:.2f}
- Claim status: PENDED (Request for Information)
- You have already provided treatment and incurred costs

PEND REASON:
{pend_decision.get('pend_reason', 'Additional documentation requested')}

REQUESTED DOCUMENTATION:
{', '.join(pend_decision.get('requested_documents', ['Additional clinical documentation']))}

{service_details}

YOUR OPTIONS:
1. RESUBMIT: Provide requested docs
   - Cost: ${CLAIM_PEND_RESUBMIT_COST:.2f} (staff time to gather and resubmit documentation)
   - Historical success rate: {int(CLAIM_PEND_SUCCESS_RATE * 100)}% (claim gets paid)
   - Risk: May get PENDED AGAIN for different reason (regulatory arbitrage tactic)

2. ABANDON: Write off the claim
   - Cost: ${claim_amount:.2f} (direct loss - you already provided service)
   - Note: Industry data shows many providers abandon pended claims due to admin burden

COST-BENEFIT ANALYSIS:
- Expected value of resubmission: ${expected_value_resubmit:.2f}
- Current iteration: {pend_iteration}/{MAX_PEND_ITERATIONS} (max pends before forced rejection)
- PA was APPROVED in Phase 2, so medical necessity was already established

STRATEGIC CONSIDERATIONS:
- Insurer uses PEND to avoid reporting formal denials to regulators
- Each pend iteration costs you admin time with no guarantee of payment
- If you abandon, insurer achieves non-payment without regulatory penalty
- Your behavioral parameters (patient care weight, risk tolerance) should guide decision

Your task: Decide whether to resubmit documentation or abandon claim based on your incentives.

RESPONSE FORMAT (JSON):
{{
    "decision": "resubmit" | "abandon",
    "rationale": "<why you chose this option given cost-benefit analysis and behavioral parameters>",
    "documents_to_add": ["<doc1>", "<doc2>", ...],  // if resubmitting
    "expected_outcome": "<what you expect to happen>"
}}"""


def create_provider_claim_resubmission_prompt(state, pend_decision, service_request, phase_2_evidence=None, pa_type="specialty_medication"):
    """create provider resubmission packet prompt (responding to pended claim) - works for all PA types"""
    import json
    from src.models.schemas import PAType

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

    if pa_type == PAType.SPECIALTY_MEDICATION:
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


def create_provider_claim_appeal_prompt(state, denial_reason, service_request, phase_2_evidence=None, pa_type="specialty_medication", appeal_history=None):
    """create provider claim appeal submission prompt - works for all PA types"""
    import json
    from src.models.schemas import PAType

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
    if pa_type == PAType.SPECIALTY_MEDICATION:
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


def create_payor_claim_appeal_review_prompt(state, appeal_letter, denial_reason, service_request, cost_ref, phase_2_evidence=None, pa_type="specialty_medication"):
    """create payor claim appeal review prompt - works for all PA types"""
    import json
    from src.models.schemas import PAType

    if pa_type == PAType.SPECIALTY_MEDICATION:
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


def create_payor_claim_resubmission_review_prompt(state, resubmission_packet, pend_decision, service_request, cost_ref, pend_iteration, pa_type="specialty_medication"):
    """create payor resubmission review prompt (after provider resubmits pended claim) - works for all PA types"""
    import json
    from src.models.schemas import PAType

    if pa_type == PAType.SPECIALTY_MEDICATION:
        service_details = f"""TREATMENT DETAILS:
- Medication: {service_request.get('medication_name')}
- Dosage: {service_request.get('dosage')}"""
        claim_amount = cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
    else:
        service_name = service_request.get('treatment_name', service_request.get('procedure_name', 'procedure'))
        service_details = f"""SERVICE DETAILS:
- Procedure/Service: {service_name}"""
        claim_amount = cost_ref.get('procedure_cost', 7800)

    return f"""TASK: Review RESUBMITTED CLAIM (Phase 3 - Pend Iteration {pend_iteration}/{MAX_PEND_ITERATIONS})

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
- Current pend iteration: {pend_iteration}/{MAX_PEND_ITERATIONS}

DECISION FACTORS:
- Does resubmission address your pend reason adequately?
- Is the additional documentation sufficient?
- Do you have grounds to PEND AGAIN for a different reason?
- Cost-benefit: Approving payment vs. continuing pend cycle

STRATEGIC OPTIONS:
1. APPROVE: Documentation now sufficient, authorize payment
2. REJECT: Formally deny (triggers costly appeals, counts toward denial rate in regulatory reporting)
3. PEND AGAIN: Request different/additional documentation (provider may abandon, avoids formal denial metrics)

STRATEGIC CONSIDERATIONS:
- If pend iteration reaches {MAX_PEND_ITERATIONS}/{MAX_PEND_ITERATIONS}, claim will be FORCED to rejection
- Each pend increases provider abandonment probability (saves you money without formal denial)
- But excessive pending may trigger provider to escalate or leave network
- PENDED claims are NOT reported to regulators, REJECTED claims ARE reported

Your task: Review resubmission and decide: approve, reject, or pend again.

RESPONSE FORMAT (JSON):
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
