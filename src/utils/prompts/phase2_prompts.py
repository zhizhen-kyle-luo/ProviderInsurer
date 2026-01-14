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
    MAX_REQUEST_INFO_PER_LEVEL,
    INTERNAL_REASONING,
    WORKFLOW_LEVELS,
    PROVIDER_REQUEST_TYPES,
    PAYOR_ACTIONS_GUIDE,
)
from .response_schemas import (
    phase2_provider_response_format,
    phase2_treatment_decision_response_format,
    phase2_payor_response_format,
)
from .prompt_renderers import (
    phase2_diagnostic_request_summary,
    phase2_treatment_request_summary,
    phase2_level_of_care_request_summary,
    render_diagnosis_summary,
)


def create_unified_provider_request_prompt(state, case, iteration, prior_iterations, level):
    """Unified provider prompt for Phase 2 pre-adjudication utilization review.
    """
    import json
    if level not in WORKFLOW_LEVELS:
        raise ValueError(f"unknown level '{level}' in create_unified_provider_request_prompt")

    # format prior iterations for context
    prior_context = ""
    completed_tests = []
    if prior_iterations:
        prior_context = "PRIOR ITERATIONS:\n"
        for i, iter_data in enumerate(prior_iterations, 1):
            prior_context += f"\nIteration {i}:\n"
            prior_context += f"  Your request: {iter_data['provider_request_type']}\n"
            prior_context += f"  Payor decision: {iter_data['payor_decision']}\n"
            if iter_data.get('payor_decision_reason'):
                prior_context += f"  Denial reason: {iter_data['payor_decision_reason']}\n"
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
    if level == 0:
        stage_instruction = "INITIAL DETERMINATION: Submit your best clinical justification based on initial presentation and any available objective data.\n"
    elif level == 1:
        stage_instruction = "INTERNAL APPEAL: You are appealing a prior denial. Address the specific denial reason explicitly and provide additional clinical evidence that addresses the payor's concerns.\n"
    elif level == 2:
        stage_instruction = "FINAL INDEPENDENT REVIEW: This is your final opportunity to present evidence. Ensure all objective values (labs, vitals, imaging) are clearly documented with specific numbers. Maximize clarity and completeness.\n"

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

NOTE: The Insurer uses different criteria that you cannot see.
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

{PROVIDER_REQUEST_TYPES}

CLINICAL DOCUMENTATION:
Update your clinical notes each iteration as you narrow your differential diagnosis. Notes should:
- Integrate new test results and clinical findings
- Document evolving diagnostic reasoning
- Support medical necessity for requested service
- Follow standard H&P format (concise, pertinent findings only)

Your notes should justify the requested service based on clinical data.

RESPONSE: Return ONLY valid JSON (no narrative text, no explanation). Do not deviate from this format.

RESPONSE FORMAT (JSON):
{phase2_provider_response_format()}
"""

    return base_prompt


def create_treatment_decision_after_phase2_denial_prompt(
    state,
    decision_reason: str,
):
    """Prompt for provider decision to treat after Phase 2 denial."""
    return f"""TREATMENT DECISION AFTER PHASE 2 DENIAL

SITUATION: Your Phase 2 utilization review request was DENIED after exhausting all appeals.
You must decide: Provide care anyway (risking nonpayment), or decline treatment?

PHASE 2 OUTCOME:
- Status: denied
- Denial Reason: {decision_reason}

CLINICAL CONTEXT:
- Patient Age: {state.admission.patient_demographics.age}
- Chief Complaint: {state.clinical_presentation.chief_complaint}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}

TWO DECISIONS:
1. treat_anyway: Provide care despite the denial (patient pays OOP, or you provide charity care, or hope claim approved retroactively)
2. no_treat: Do not provide care (patient abandons treatment, conserve resources, avoid uncompensated care risk)

IMPORTANT CONTEXT:
- Medical abandonment tort: Terminating care without proper notice can create legal liability
- Financial risk: Treating without authorization means risking nonpayment
- Patient impact: 78% of patients abandon treatment when coverage is denied (AMA survey)

TASK: Decide whether to treat the patient despite the denial.

RESPONSE FORMAT (JSON):
{phase2_treatment_decision_response_format()}

Use your clinical judgment and documentation constraints to guide this decision."""


def create_unified_payor_review_prompt(state, provider_request, iteration, level, pend_count_at_level=0):
    """Unified payor prompt for Phase 2 pre-adjudication utilization review.
    """

    if level not in WORKFLOW_LEVELS:
        raise ValueError(f"unknown level '{level}' in create_unified_payor_review_prompt")

    level_config = WORKFLOW_LEVELS[level]

    if 'request_type' not in provider_request:
        raise ValueError("provider_request missing required field 'request_type'")
    request_type = provider_request.get('request_type')
    if not request_type:
        raise ValueError("provider_request.request_type is empty")

    if 'requested_service' not in provider_request:
        raise ValueError("provider_request missing required field 'requested_service'")
    requested_service = provider_request.get('requested_service')
    if not isinstance(requested_service, dict):
        raise ValueError("provider_request.requested_service must be a dict")

    if request_type == 'diagnostic_test':
        if 'service_name' not in requested_service:
            raise ValueError("requested_service missing required field 'service_name' for diagnostic_test")
        if 'test_justification' not in requested_service:
            raise ValueError("requested_service missing required field 'test_justification' for diagnostic_test")
        if 'expected_findings' not in requested_service:
            raise ValueError("requested_service missing required field 'expected_findings' for diagnostic_test")
        request_summary = phase2_diagnostic_request_summary(requested_service)
    elif request_type == 'level_of_care':
        if 'requested_status' not in requested_service:
            raise ValueError("requested_service missing required field 'requested_status' for level_of_care")
        if 'alternative_status' not in requested_service:
            raise ValueError("requested_service missing required field 'alternative_status' for level_of_care")
        if 'severity_indicators' not in requested_service:
            raise ValueError("requested_service missing required field 'severity_indicators' for level_of_care")
        request_summary = phase2_level_of_care_request_summary(requested_service)
    elif request_type == 'treatment':
        if 'service_name' not in requested_service:
            raise ValueError("requested_service missing required field 'service_name' for treatment")
        if 'clinical_evidence' not in requested_service:
            raise ValueError("requested_service missing required field 'clinical_evidence' for treatment")
        if 'guideline_references' not in requested_service:
            raise ValueError("requested_service missing required field 'guideline_references' for treatment")
        guideline_references = requested_service.get('guideline_references')
        if not isinstance(guideline_references, list):
            raise ValueError("requested_service.guideline_references must be a list for treatment")
        request_summary = phase2_treatment_request_summary(requested_service, guideline_references)
    else:
        raise ValueError(f"unknown request_type '{request_type}' - must be 'diagnostic_test', 'level_of_care', or 'treatment'")

    # get diagnosis codes if present
    if 'diagnosis_codes' not in provider_request:
        raise ValueError("provider_request missing required field 'diagnosis_codes'")
    diagnosis_codes = provider_request.get('diagnosis_codes')
    if not isinstance(diagnosis_codes, list):
        raise ValueError("provider_request.diagnosis_codes must be a list")
    diagnosis_summary = render_diagnosis_summary(diagnosis_codes)

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
    can_pend_by_level = level_config["can_pend"]
    is_terminal = level_config["terminal"]
    is_independent = level_config["independent"]

    # enforce MAX_REQUEST_INFO_PER_LEVEL: disable pend if limit reached
    can_pend = can_pend_by_level and (pend_count_at_level < MAX_REQUEST_INFO_PER_LEVEL)
    pend_limit_reached = can_pend_by_level and (pend_count_at_level >= MAX_REQUEST_INFO_PER_LEVEL)

    if can_pend:
        decision_options = "approved | modified | denied | pending_info"
    else:
        decision_options = "approved | modified | denied"

    stage_instruction = f"""LEVEL {level} - {level_config['name'].upper()} ({role_label}):
Reviewer: {role_label}
Mode: {review_style}
Decision options: {decision_options}
{level_description}

{PAYOR_ACTIONS_GUIDE}

"""
    if pend_limit_reached:
        stage_instruction += f"""CRITICAL: You have reached the maximum REQUEST_INFO limit ({MAX_REQUEST_INFO_PER_LEVEL} pends) at this level.
You MUST issue a final decision: APPROVED, MODIFIED, or DENIED.
REQUEST_INFO (pending_info) is NO LONGER available.

"""
    if is_terminal:
        stage_instruction += """CRITICAL: This is a TERMINAL review level. You MUST issue a final APPROVED or DENIED decision.
REQUEST_INFO (pending_info) is NOT available at this level.

"""
    if is_independent:
        stage_instruction += """NOTE: As an independent external reviewer, you do NOT have access to plan-internal notes.
Your decision must be based solely on the submitted clinical record.

"""

    if 'clinical_notes' not in provider_request:
        raise ValueError("provider_request missing required field 'clinical_notes'")
    clinical_notes = provider_request['clinical_notes']

    base_prompt = f"""ITERATION {iteration}/{MAX_ITERATIONS}

{stage_instruction}{policy_section}PROVIDER REQUEST:
{diagnosis_summary}

{request_summary}

Clinical Notes:
{clinical_notes}

PATIENT CONTEXT:
- Age: {state.admission.patient_demographics.age}
- Medical History: {', '.join(state.clinical_presentation.medical_history)}
- Current Diagnoses: {', '.join(state.admission.preliminary_diagnoses)}

TASK: Review the Phase 2 pre-adjudication utilization review request and issue a coverage decision (or REQUEST_INFO) based on medical necessity and coverage criteria.

EVALUATION CRITERIA:
{
    "- Is diagnostic test medically necessary to establish diagnosis?" if request_type == 'diagnostic_test'
    else "- Does clinical severity justify requested level of care?" if request_type == 'level_of_care'
    else "- Is treatment medically necessary based on clinical evidence?"
}
{
    "- Will test results meaningfully change clinical management?" if request_type == 'diagnostic_test'
    else "- Do severity indicators meet criteria for requested status vs alternative?" if request_type == 'level_of_care'
    else "- Has step therapy been completed (if applicable)?"
}
- Does request align with clinical guidelines?
- Is documentation sufficient?

RESPONSE: Return ONLY valid JSON (no narrative text, no explanation). Do not deviate from this format.

RESPONSE FORMAT (JSON):
{phase2_payor_response_format(decision_options, can_pend, role_label, level)}"""

    return base_prompt
