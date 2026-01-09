"""phase2_prompts.py

Phase 2 Prompts: PRE-ADJUDICATION UTILIZATION REVIEW (Prospective/Concurrent)

Phase 2 is *not always "prior authorization"*.
- For elective/non-emergent services: Phase 2 behaves like prospective review (prior auth).
- For ER/inpatient episodes: Phase 2 behaves like concurrent review (coverage to continue care).

Key operational property: the record is EVOLVING.
The payer can REQUEST_INFO (pend), and the provider can respond in real time
by adding documentation and ordering tests (when allowed by your simulation).
"""

from .config import (
    MAX_ITERATIONS,
    INTERNAL_REASONING,
    WORKFLOW_LEVELS,
    LEVEL_NAME_MAP,
)


def create_unified_provider_request_prompt(state, case, iteration, prior_iterations, stage=None):
    """Unified provider prompt for Phase 2 pre-adjudication utilization review.

    The provider chooses whether to request a diagnostic test or a treatment,
    and updates documentation iteratively in response to payer REQUEST_INFO/denials.

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
        import json
        policy_view = state.provider_policy_view
        content_data = policy_view.get("content", {}).get("data", {})
        if content_data:
            policy_section = f"""
YOUR CLINICAL GUIDELINES:
{json.dumps(content_data, indent=2)}

NOTE: The Insurer uses different (stricter) criteria that you cannot see.
Gather objective evidence to demonstrate clinical necessity.

"""

    provider_behavior_section = ""

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS}

{stage_instruction}{policy_section}{provider_behavior_section}{INTERNAL_REASONING}

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

TASK: Provide updated clinical documentation and your authorization request.

CLINICAL DOCUMENTATION:
Update your clinical notes each iteration as you narrow your differential diagnosis. Notes should:
- Integrate new test results and clinical findings
- Document evolving diagnostic reasoning
- Support medical necessity for requested service
- Follow standard H&P format (concise, pertinent findings only)

Your notes should justify the requested service based on clinical data.

RESPONSE: Return ONLY valid JSON (no narrative text, no explanation). Do not deviate from this format.

RESPONSE FORMAT (JSON):
{{
    "internal_rationale": {{
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
"""

    return base_prompt


def create_treatment_decision_after_pa_denial_prompt(
    state,
    denial_reason: str,
):
    """Prompt for provider decision to treat after PA denial."""
    return f"""TREATMENT DECISION AFTER PA DENIAL

SITUATION: Your prior authorization request was DENIED after exhausting all appeals.
You must decide: Provide care anyway (risking nonpayment), or decline treatment?

PA OUTCOME:
- Status: denied
- Denial Reason: {denial_reason}

CLINICAL CONTEXT:
- Patient Age: {state.admission.patient_demographics.age}
- Chief Complaint: {state.clinical_presentation.chief_complaint}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}

TWO DECISIONS:
1. treat_anyway: Provide care despite PA denial (patient pays OOP, or you provide charity care, or hope claim approved retroactively)
2. no_treat: Do not provide care (patient abandons treatment, conserve resources, avoid uncompensated care risk)

IMPORTANT CONTEXT:
- Medical abandonment tort: Terminating care without proper notice can create legal liability
- Financial risk: Treating without authorization means risking nonpayment
- Patient impact: 78% of patients abandon treatment when PA denied (AMA survey)

TASK: Decide whether to treat the patient despite PA denial.

RESPONSE FORMAT (JSON):
{{
    "decision": "treat_anyway" or "no_treat",
    "rationale": "<explain your reasoning considering clinical need, financial risk, and legal obligations>"
}}

Use your clinical judgment and documentation constraints to guide this decision."""


def create_unified_payor_review_prompt(state, provider_request, iteration, stage=None, level=None):
    """Unified payor prompt for Phase 2 pre-adjudication utilization review.

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
DIAGNOSTIC TEST REVIEW REQUEST (Phase 2):
Test: {requested_service.get('service_name')}
Justification: {requested_service.get('test_justification')}
Expected Findings: {requested_service.get('expected_findings')}
"""
    else:  # treatment
        request_summary = f"""
TREATMENT REVIEW REQUEST (Phase 2):
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
        import json
        policy_view = state.payor_policy_view
        content_data = policy_view.get("content", {}).get("data", {})
        if content_data:
            policy_section = f"""
STRICT AUDITOR MODE - YOUR COVERAGE POLICY:
{json.dumps(content_data, indent=2)}

CRITICAL: Apply your coverage criteria strictly. Deny if documentation does not meet policy requirements.

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

TASK: Review the Phase 2 pre-adjudication utilization review request and issue a coverage decision (or REQUEST_INFO) based on medical necessity and coverage criteria.

EVALUATION CRITERIA:
{"- Is diagnostic test medically necessary to establish diagnosis?" if request_type == 'diagnostic_test' else "- Is treatment medically necessary based on clinical evidence?"}
{"- Will test results meaningfully change clinical management?" if request_type == 'diagnostic_test' else "- Has step therapy been completed (if applicable)?"}
- Does request align with clinical guidelines?
- Is documentation sufficient?

RESPONSE: Return ONLY valid JSON (no narrative text, no explanation). Do not deviate from this format.

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
