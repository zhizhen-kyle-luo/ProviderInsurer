from typing import Dict, Any
from datetime import date, timedelta
import time
import random
import json
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from src.models.schemas import (
    EncounterState,
    ProviderClinicalRecord,
    ClinicalIteration,
    UtilizationReviewDecision,
    AppealRecord,
    AppealSubmission,
    AppealDecision,
    FinancialSettlement,
    ServiceLineItem,
    DRGAssignment,
    LabResult,
    ImagingResult,
    MedicationAuthorizationDecision,
    MedicationFinancialSettlement,
    PAType
)
from src.agents.provider import ProviderAgent
from src.agents.payor import PayorAgent
from src.utils.cpt_calculator import CPTCostCalculator
from src.utils.audit_logger import AuditLogger
from src.utils.worm_cache import WORMCache
from src.utils.cached_llm import CachedLLM
from src.utils.prompts import (
    create_provider_prompt,
    create_payor_prompt,
    create_unified_provider_request_prompt,
    create_unified_payor_review_prompt,
    create_claim_adjudication_prompt,
    create_provider_claim_submission_prompt,
    create_provider_claim_appeal_decision_prompt,
    create_provider_claim_appeal_prompt,
    create_payor_claim_appeal_review_prompt,
    DEFAULT_PROVIDER_PARAMS,
    DEFAULT_PAYOR_PARAMS,
    MAX_ITERATIONS,
    MAX_PHASE_3_ITERATIONS,
    CONFIDENCE_THRESHOLD,
    NOISE_PROBABILITY
)


class UtilizationReviewSimulation:
    """
    2-agent Provider-Payer concurrent utilization review simulation.

    Architecture:
    Phase 1: Admission & Insurance Notification
    Phase 2: Clinical Care & Concurrent Utilization Review (iterative)
    Phase 3: Denial & Appeal Process (if denied)
    Phase 4: Financial Resolution
    """

    def __init__(
        self,
        provider_llm: str = "gpt-4",
        payor_llm: str = "gpt-4",
        master_seed: int = None,
        confidence_threshold: float = None,
        max_iterations: int = None,
        azure_config: Dict[str, Any] = None,
        cache_dir: str = ".worm_cache",
        enable_cache: bool = True
    ):
        self.master_seed = master_seed if master_seed is not None else int(time.time())
        self.rng = random.Random(self.master_seed)
        self.confidence_threshold = confidence_threshold if confidence_threshold is not None else CONFIDENCE_THRESHOLD
        self.max_iterations = max_iterations if max_iterations is not None else MAX_ITERATIONS

        self.cache = WORMCache(cache_dir=cache_dir, enable_persistence=enable_cache) if enable_cache else None

        provider_model = self._create_llm(provider_llm, azure_config)
        payor_model = self._create_llm(payor_llm, azure_config)

        if self.cache:
            provider_model = CachedLLM(provider_model, self.cache, agent_name="provider")
            payor_model = CachedLLM(payor_model, self.cache, agent_name="payor")
        # create deterministic LLM for test result generation (temperature=0)
        self.test_result_llm = self._create_llm(provider_llm, azure_config, temperature=0)

        self.provider = ProviderAgent(provider_model)
        self.payor = PayorAgent(payor_model)
        self.cost_calculator = CPTCostCalculator()
        self.test_result_cache = {}

    def _create_llm(self, model_name: str, azure_config: Dict[str, Any] = None, temperature: float = 0.7):
        if azure_config:
            return AzureChatOpenAI(
                azure_endpoint=azure_config["endpoint"],
                api_key=azure_config["key"],
                azure_deployment=azure_config["deployment_name"],
                api_version="2024-08-01-preview",
                temperature=temperature
            )
        else:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name, temperature=temperature)

    def _introduce_noise(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        introduce environmental noise to patient_visible_data based on NOISE_PROBABILITY

        deterministically applies one of three noise types using self.rng
        logs noise as environment action
        """
        import copy

        if self.rng.random() > NOISE_PROBABILITY:
            # no noise introduced
            self.audit_logger.log_environment_action(
                phase="phase_1_presentation",
                action_type="data_quality_check",
                description="no environmental noise introduced (clean data)",
                outcome={"noise_applied": False},
                metadata={"noise_probability": NOISE_PROBABILITY}
            )
            return case

        noisy_case = copy.deepcopy(case)
        patient_data = noisy_case.get("patient_visible_data", {})

        noise_type = self.rng.choice(["age", "medication", "diagnosis"])
        noise_description = ""
        noise_details = {}

        if noise_type == "age":
            # age error: ±3-7 years
            age_offset = self.rng.randint(3, 7) * self.rng.choice([-1, 1])
            original_age = patient_data.get("age", 60)
            noisy_age = max(18, original_age + age_offset)
            patient_data["age"] = noisy_age
            noise_description = f"age error introduced: {original_age} → {noisy_age}"
            noise_details = {"original_age": original_age, "noisy_age": noisy_age, "offset": age_offset}

        elif noise_type == "medication":
            # wrong medication name in history
            medications = patient_data.get("medications", [])
            if medications:
                wrong_meds = [
                    "Aspirin 81mg daily",
                    "Metformin 500mg twice daily",
                    "Lisinopril 10mg daily",
                    "Atorvastatin 20mg daily"
                ]
                idx = self.rng.randint(0, len(medications) - 1)
                original_med = medications[idx]
                wrong_med = self.rng.choice(wrong_meds)
                medications[idx] = wrong_med
                noise_description = f"medication error introduced: replaced '{original_med}' with '{wrong_med}'"
                noise_details = {"original": original_med, "replacement": wrong_med, "index": idx}

        elif noise_type == "diagnosis":
            # remove key diagnosis from medical history
            medical_history = patient_data.get("medical_history", [])
            if medical_history and len(medical_history) > 1:
                idx = self.rng.randint(0, len(medical_history) - 1)
                removed_diagnosis = medical_history[idx]
                medical_history.pop(idx)
                noise_description = f"diagnosis omitted: removed '{removed_diagnosis}' from medical history"
                noise_details = {"removed_diagnosis": removed_diagnosis, "index": idx}

        # log environment noise action
        self.audit_logger.log_environment_action(
            phase="phase_1_presentation",
            action_type="introduce_noise",
            description=noise_description,
            outcome={"noise_type": noise_type, "noise_applied": True, **noise_details},
            metadata={"noise_probability": NOISE_PROBABILITY}
        )

        return noisy_case

    def _generate_test_result(self, test_name: str, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        generate deterministic test result using LLM + master_seed

        uses environment_hidden_data as ground truth context
        caches results to avoid regenerating same test multiple times
        """
        cache_key = f"{case['case_id']}_{test_name}"

        if cache_key in self.test_result_cache:
            return self.test_result_cache[cache_key]

        # check if test result is pre-defined in test_result_templates
        test_templates = case.get("test_result_templates", {})
        if test_name in test_templates:
            result = {
                "test_name": test_name,
                "value": test_templates[test_name],
                "generated": False
            }
            self.test_result_cache[cache_key] = result
            return result

        # generate test result using LLM with environment_hidden_data
        hidden_data = case.get("environment_hidden_data", {})
        patient_data = case.get("patient_visible_data", {})

        prompt = f"""Generate realistic {test_name} test result for this patient.

PATIENT CONTEXT (ground truth):
- True diagnosis: {hidden_data.get('true_diagnosis', 'Unknown')}
- Disease severity: {hidden_data.get('disease_severity', 'Unknown')}
- Clinical context: {hidden_data.get('clinical_context', 'Unknown')}

PATIENT DEMOGRAPHICS:
- Age: {patient_data.get('age')}
- Sex: {patient_data.get('sex')}
- Chief complaint: {patient_data.get('chief_complaint')}

Generate ONLY the test result value with units and interpretation. Format as a single-line string.
Example: "827 µg/g (critically elevated - normal <50 µg/g)"

Test result for {test_name}:"""

        messages = [HumanMessage(content=prompt)]

        # use deterministic LLM with temperature=0 for reproducibility
        response = self.test_result_llm.invoke(messages)
        result_text = response.content.strip()

        # create structured result
        result = {
            "test_name": test_name,
            "value": result_text,
            "generated": True
        }

        self.test_result_cache[cache_key] = result
        return result

    def run_case(self, case: Dict[str, Any]) -> EncounterState:
        """
        Run single case through 4-phase utilization review workflow.

        Phase 1: Patient presentation (already complete in case data)
        Phase 2: Prior authorization review
        Phase 3: Appeal process if denied
        Phase 4: Financial settlement

        routes to appropriate workflow based on pa_type
        """
        # apply environmental noise deterministically
        case = self._introduce_noise(case)

        # clear test result cache for new case
        self.test_result_cache = {}

        pa_type = case.get("pa_type", PAType.INPATIENT_ADMISSION)

        state = EncounterState(
            case_id=case["case_id"],
            admission_date=case["admission"].admission_date,
            admission=case["admission"],
            clinical_presentation=case["clinical_presentation"],
            pa_type=pa_type
        )

        # initialize audit logger for this case
        self.audit_logger = AuditLogger(case_id=case["case_id"])

        # unified phase 2 workflow (all case types)
        state = self._phase_2_unified_pa(state, case)

        # phase 3: claims adjudication (if treatment was approved and delivered)
        # only run for medication cases, not procedures
        if (state.medication_authorization and
            state.medication_authorization.authorization_status == "approved" and
            pa_type == PAType.SPECIALTY_MEDICATION):
            state = self._phase_3_medication_claims(state, case)

        # phase 4: financial settlement
        if state.medication_authorization:
            state = self._phase_4_medication_financial(state, case)

        if "ground_truth" in case:
            state.ground_truth_outcome = case["ground_truth"]["outcome"]
            state.simulation_matches_reality = (
                state.final_authorized_level == case["ground_truth"]["outcome"]
            )

        # finalize audit log and attach to state with behavioral parameters
        summary = self.audit_logger._generate_summary()
        summary["behavioral_parameters"] = {
            "provider": DEFAULT_PROVIDER_PARAMS,
            "payor": DEFAULT_PAYOR_PARAMS
        }
        summary["master_seed"] = self.master_seed
        self.audit_logger.finalize(summary)
        state.audit_log = self.audit_logger.get_audit_log()

        return state

    def _phase_2_unified_pa(
        self,
        state: EncounterState,
        case: Dict[str, Any]
    ) -> EncounterState:
        """
        unified phase 2: iterative PA workflow for all case types

        provider agent decides:
          - if confidence < threshold: request diagnostic test PA
          - if confidence >= threshold: request treatment PA

        continues until: treatment approved OR max iterations OR agent stops
        """
        import json

        state.review_date = state.admission_date

        prior_iterations = []
        treatment_approved = False
        approved_provider_request = None

        for iteration_num in range(1, self.max_iterations + 1):
            # provider generates request based on confidence
            provider_system_prompt = create_provider_prompt(DEFAULT_PROVIDER_PARAMS)
            provider_user_prompt = create_unified_provider_request_prompt(
                state, case, iteration_num, prior_iterations
            )

            full_prompt = f"{provider_system_prompt}\n\n{provider_user_prompt}"
            messages = [HumanMessage(content=full_prompt)]
            response = self.provider.llm.invoke(messages)
            provider_response_text = response.content
            cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

            try:
                clean_response = provider_response_text
                if "```json" in clean_response:
                    clean_response = clean_response.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_response:
                    clean_response = clean_response.split("```")[1].split("```")[0].strip()
                provider_request = json.loads(clean_response)
            except:
                provider_request = {
                    "confidence": 0.5,
                    "confidence_rationale": "unable to parse response",
                    "differential_diagnoses": [],
                    "request_type": "diagnostic_test",
                    "request_details": {}
                }

            confidence = provider_request.get("confidence", 0.5)
            request_type = provider_request.get("request_type")

            # log provider request
            self.audit_logger.log_interaction(
                phase="phase_2_pa",
                agent="provider",
                action=f"{request_type}_request",
                system_prompt=provider_system_prompt,
                user_prompt=provider_user_prompt,
                llm_response=provider_response_text,
                parsed_output=provider_request,
                metadata={
                    "iteration": iteration_num,
                    "confidence": confidence,
                    "request_type": request_type,
                    "cache_hit": cache_hit
                }
            )

            # payor reviews request
            payor_system_prompt = create_payor_prompt(DEFAULT_PAYOR_PARAMS)
            payor_user_prompt = create_unified_payor_review_prompt(
                state, provider_request, iteration_num
            )

            full_prompt = f"{payor_system_prompt}\n\n{payor_user_prompt}"
            messages = [HumanMessage(content=full_prompt)]
            response = self.payor.llm.invoke(messages)
            payor_response_text = response.content
            payor_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

            try:
                clean_response = payor_response_text
                if "```json" in clean_response:
                    clean_response = clean_response.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_response:
                    clean_response = clean_response.split("```")[1].split("```")[0].strip()
                payor_decision = json.loads(clean_response)
            except:
                payor_decision = {
                    "authorization_status": "denied",
                    "denial_reason": "unable to parse response",
                    "criteria_used": "unknown",
                    "reviewer_type": "AI algorithm"
                }

            # log payor decision
            self.audit_logger.log_interaction(
                phase="phase_2_pa",
                agent="payor",
                action=f"{request_type}_review",
                system_prompt=payor_system_prompt,
                user_prompt=payor_user_prompt,
                llm_response=payor_response_text,
                parsed_output=payor_decision,
                metadata={
                    "iteration": iteration_num,
                    "request_type": request_type,
                    "cache_hit": payor_cache_hit
                }
            )

            # track iteration for next round
            iteration_record = {
                "provider_request_type": request_type,
                "provider_confidence": confidence,
                "payor_decision": payor_decision["authorization_status"],
                "payor_denial_reason": payor_decision.get("denial_reason")
            }

            # handle decision outcomes
            if payor_decision["authorization_status"] == "approved":
                if request_type == "treatment":
                    # treatment approved - DONE
                    treatment_approved = True
                    approved_provider_request = provider_request  # save for phase 3
                    state.medication_authorization = MedicationAuthorizationDecision(
                        reviewer_type=payor_decision.get("reviewer_type", "AI algorithm"),
                        authorization_status="approved",
                        denial_reason=None,
                        criteria_used=payor_decision.get("criteria_used", "Medical necessity"),
                        step_therapy_required=False,
                        missing_documentation=[],
                        approved_duration_days=90,
                        requires_peer_to_peer=False
                    )
                    break
                elif request_type == "diagnostic_test":
                    # diagnostic test approved - generate test result using environment agent
                    test_name = provider_request.get("request_details", {}).get("test_name")
                    if test_name:
                        test_result = self._generate_test_result(test_name, case)
                        iteration_record["test_results"] = {test_name: test_result["value"]}
                    else:
                        iteration_record["test_results"] = {}

            elif payor_decision["authorization_status"] == "denied":
                # request denied - provider will address in next iteration
                state.denial_occurred = True

            prior_iterations.append(iteration_record)

        # if treatment never approved, mark as denied
        if not treatment_approved:
            state.medication_authorization = MedicationAuthorizationDecision(
                reviewer_type="AI algorithm",
                authorization_status="denied",
                denial_reason="max iterations reached without approval",
                criteria_used="Medical necessity",
                step_therapy_required=False,
                missing_documentation=[],
                approved_duration_days=None,
                requires_peer_to_peer=False
            )
            state.denial_occurred = True

        # collect all evidence from phase 2 for phase 3
        accumulated_test_results = {}
        for iteration in prior_iterations:
            if "test_results" in iteration:
                accumulated_test_results.update(iteration["test_results"])

        state._phase_2_evidence = {
            "approved_request": approved_provider_request,
            "test_results": accumulated_test_results,
            "iterations": prior_iterations
        }

        return state

    def _generate_test_result_from_environment(
        self,
        test_name: str,
        environment_data: Dict[str, Any],
        pa_type: str
    ) -> Dict[str, Any]:
        """
        generate realistic test results based on environment_hidden_data
        uses ground truth to simulate what test would actually find
        """
        true_diagnosis = environment_data.get("true_diagnosis", "").lower()
        disease_severity = environment_data.get("disease_severity", "").lower()
        clinical_context = environment_data.get("clinical_context", "")

        test_name_lower = test_name.lower()

        # resting ecg/ekg
        if "ecg" in test_name_lower or "ekg" in test_name_lower:
            if "stress" not in test_name_lower and "exercise" not in test_name_lower:
                # resting ecg only
                if "coronary" in true_diagnosis or "cad" in true_diagnosis or "ischemia" in true_diagnosis:
                    if "severe" in true_diagnosis or "critical" in disease_severity:
                        return {
                            "test_name": test_name,
                            "status": "completed",
                            "finding": "Resting ECG shows T-wave inversions in leads V2-V4. ST segment abnormalities present. Concerning for significant coronary ischemia. Recommend urgent functional cardiac testing (stress test or coronary angiography)."
                        }
                    else:
                        return {
                            "test_name": test_name,
                            "status": "completed",
                            "finding": "Resting ECG shows nonspecific ST-T wave changes. Consider stress testing for further evaluation."
                        }
                else:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "Normal sinus rhythm. No acute ST changes or ischemic findings."
                    }

        # cardiac/stress testing results
        if "stress" in test_name_lower or "exercise" in test_name_lower or "echo" in test_name_lower:
            if "coronary" in true_diagnosis or "cad" in true_diagnosis or "ischemia" in true_diagnosis:
                if "severe" in true_diagnosis or "critical" in disease_severity or "occlusion" in disease_severity:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "ABNORMAL - Significant ST depression in leads V2-V4 at 5 minutes. Test terminated at 7 METS due to chest pain and ECG changes. Strongly positive for inducible ischemia. Immediate cardiology referral recommended."
                    }
                else:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "ABNORMAL - Mild ST depression in inferior leads. Positive for inducible ischemia. Further workup recommended."
                    }
            else:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Normal exercise tolerance. No ST changes or arrhythmias. Negative for inducible ischemia."
                }

        # inflammatory markers (crohn's, IBD)
        elif "calprotectin" in test_name_lower or "fecal" in test_name_lower:
            if "crohn" in true_diagnosis or "ibd" in true_diagnosis or "colitis" in true_diagnosis:
                if "severe" in disease_severity or "active" in clinical_context.lower():
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "Fecal calprotectin: 850 mcg/g (severely elevated, ref <50). CRP: 45 mg/L (elevated). Consistent with active inflammatory bowel disease."
                    }
                else:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "Fecal calprotectin: 220 mcg/g (elevated, ref <50). Suggests active inflammation."
                    }

        # colonoscopy/endoscopy
        elif "colonoscopy" in test_name_lower or "endoscopy" in test_name_lower:
            if "crohn" in true_diagnosis:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Colonoscopy shows deep ulcerations in terminal ileum and cecum with cobblestoning. Biopsies confirm transmural inflammation consistent with Crohn's disease. Stenosis noted at ileocecal valve."
                }

        # cardiac catheterization/angiography
        elif "catheter" in test_name_lower or "angio" in test_name_lower or "cath" in test_name_lower:
            if "coronary" in true_diagnosis:
                if "severe" in true_diagnosis or "99%" in disease_severity:
                    return {
                        "test_name": test_name,
                        "status": "completed",
                        "finding": "Coronary angiography: 99% stenosis of proximal LAD. 70% stenosis of RCA. High-grade multivessel disease requiring intervention."
                    }

        # ct/mri imaging
        elif "ct" in test_name_lower or "mri" in test_name_lower:
            if "crohn" in true_diagnosis:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "CT enterography shows thickened ileal wall (8mm) with surrounding fat stranding. Active inflammation and possible stricture."
                }
            elif "coronary" in true_diagnosis:
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "Coronary CT angiography shows calcified plaque in LAD with significant stenosis. Recommend functional stress testing."
                }

        # blood tests (CBC, metabolic)
        elif "cbc" in test_name_lower or "complete blood" in test_name_lower:
            if "crohn" in true_diagnosis or "anemia" in clinical_context.lower():
                return {
                    "test_name": test_name,
                    "status": "completed",
                    "finding": "CBC: Hgb 9.2 g/dL (low), MCV 76 fL (microcytic). WBC 12.5k (elevated). Consistent with anemia of chronic disease and active inflammation."
                }

        # generic fallback for unknown tests
        return {
            "test_name": test_name,
            "status": "completed",
            "finding": f"Test completed. Findings consistent with {environment_data.get('true_diagnosis', 'clinical presentation')}."
        }

    def run_multiple_cases(self, cases: list[Dict[str, Any]]) -> list[EncounterState]:
        """run multiple cases sequentially"""
        return [self.run_case(case) for case in cases]

    def _phase_3_medication_claims(
        self,
        state: EncounterState,
        case: Dict[str, Any]
    ) -> EncounterState:
        """
        phase 3: claims adjudication with provider decision and appeal loop

        workflow:
        1. provider submits claim (LLM)
        2. payor reviews claim (LLM)
        3. if denied:
           - provider decides: write-off / appeal / bill patient (LLM)
           - if appeal:
             - loop until max iterations OR approved OR provider stops
        """
        import json

        # only process claims if pa was approved
        if state.medication_authorization.authorization_status != "approved":
            return state

        med_request = case.get("medication_request", {})
        cost_ref = case.get("cost_reference", {})
        phase_2_evidence = getattr(state, '_phase_2_evidence', {})

        claim_date = state.appeal_date if state.appeal_date else state.review_date
        claim_date = claim_date + timedelta(days=7)

        # STEP 1: provider submits claim
        provider_system_prompt = create_provider_prompt()
        provider_claim_prompt = create_provider_claim_submission_prompt(
            state, med_request, cost_ref, phase_2_evidence
        )

        messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_claim_prompt}")]
        response = self.provider.llm.invoke(messages)
        provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

        try:
            response_text = response.content
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            claim_submission = json.loads(response_text)
        except:
            claim_submission = {
                "claim_submission": {
                    "medication_administered": med_request.get('medication_name'),
                    "amount_billed": cost_ref.get('drug_acquisition_cost', 7800) + cost_ref.get('administration_fee', 150)
                }
            }

        # log provider claim submission
        self.audit_logger.log_interaction(
            phase="phase_3_claims",
            agent="provider",
            action="claim_submission",
            system_prompt=provider_system_prompt,
            user_prompt=provider_claim_prompt,
            llm_response=response.content,
            parsed_output=claim_submission,
            metadata={"medication": med_request.get('medication_name'), "pa_approved": True, "cache_hit": provider_cache_hit}
        )

        # STEP 2: payor reviews claim
        payor_system_prompt = create_payor_prompt()
        payor_claim_prompt = create_claim_adjudication_prompt(
            state, med_request, cost_ref, case, phase_2_evidence
        )

        messages = [HumanMessage(content=f"{payor_system_prompt}\n\n{payor_claim_prompt}")]
        response = self.payor.llm.invoke(messages)
        payor_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

        try:
            response_text = response.content
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            claim_decision = json.loads(response_text)
        except:
            claim_decision = {
                "claim_status": "approved",
                "criteria_used": "Standard billing guidelines",
                "reviewer_type": "Claims adjudicator"
            }

        # log payor claim review
        self.audit_logger.log_interaction(
            phase="phase_3_claims",
            agent="payor",
            action="claim_review",
            system_prompt=payor_system_prompt,
            user_prompt=payor_claim_prompt,
            llm_response=response.content,
            parsed_output=claim_decision,
            metadata={"medication": med_request.get('medication_name'), "claim_status": claim_decision.get("claim_status"), "cache_hit": payor_cache_hit}
        )

        # update state with claim decision
        state.medication_authorization.authorization_status = claim_decision["claim_status"]
        if claim_decision["claim_status"] == "denied":
            state.medication_authorization.denial_reason = claim_decision.get("denial_reason")

        # STEP 3: if claim denied, provider decides what to do
        if claim_decision["claim_status"] == "denied":
            denial_reason = claim_decision.get("denial_reason", "Claim denied")
            state.appeal_date = claim_date + timedelta(days=2)

            # provider decision: write-off / appeal / bill patient
            provider_decision_prompt = create_provider_claim_appeal_decision_prompt(
                state, denial_reason, med_request, cost_ref
            )

            messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_decision_prompt}")]
            response = self.provider.llm.invoke(messages)
            provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

            try:
                response_text = response.content
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                provider_decision = json.loads(response_text)
            except:
                provider_decision = {"decision": "write_off", "rationale": "Unable to parse decision"}

            # log provider decision
            self.audit_logger.log_interaction(
                phase="phase_3_claims",
                agent="provider",
                action="claim_denial_decision",
                system_prompt=provider_system_prompt,
                user_prompt=provider_decision_prompt,
                llm_response=response.content,
                parsed_output=provider_decision,
                metadata={"decision": provider_decision.get("decision"), "cache_hit": provider_cache_hit}
            )

            # STEP 4: appeal loop if provider chooses to appeal
            if provider_decision.get("decision") == "appeal":
                state.appeal_filed = True
                appeal_iteration = 0
                claim_approved = False

                while appeal_iteration < MAX_PHASE_3_ITERATIONS and not claim_approved:
                    appeal_iteration += 1

                    # provider submits appeal
                    provider_appeal_prompt = create_provider_claim_appeal_prompt(
                        state, denial_reason, med_request, phase_2_evidence
                    )

                    messages = [HumanMessage(content=f"{provider_system_prompt}\n\n{provider_appeal_prompt}")]
                    response = self.provider.llm.invoke(messages)
                    provider_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

                    try:
                        response_text = response.content
                        if "```json" in response_text:
                            response_text = response_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in response_text:
                            response_text = response_text.split("```")[1].split("```")[0].strip()
                        appeal_letter = json.loads(response_text)
                    except:
                        appeal_letter = {
                            "appeal_letter": {
                                "denial_addressed": "Addressing denial reason",
                                "requested_action": "full payment"
                            }
                        }

                    # log provider appeal submission
                    self.audit_logger.log_interaction(
                        phase="phase_3_claims",
                        agent="provider",
                        action="claim_appeal_submission",
                        system_prompt=provider_system_prompt,
                        user_prompt=provider_appeal_prompt,
                        llm_response=response.content,
                        parsed_output=appeal_letter,
                        metadata={"appeal_iteration": appeal_iteration, "cache_hit": provider_cache_hit}
                    )

                    # payor reviews appeal
                    payor_appeal_prompt = create_payor_claim_appeal_review_prompt(
                        state, appeal_letter.get("appeal_letter", appeal_letter),
                        denial_reason, med_request, cost_ref, phase_2_evidence
                    )

                    messages = [HumanMessage(content=f"{payor_system_prompt}\n\n{payor_appeal_prompt}")]
                    response = self.payor.llm.invoke(messages)
                    payor_cache_hit = response.additional_kwargs.get('cache_hit', False) if hasattr(response, 'additional_kwargs') else False

                    try:
                        response_text = response.content
                        if "```json" in response_text:
                            response_text = response_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in response_text:
                            response_text = response_text.split("```")[1].split("```")[0].strip()
                        appeal_decision = json.loads(response_text)
                    except:
                        appeal_decision = {
                            "appeal_outcome": "denied",
                            "rationale": "Unable to parse appeal decision"
                        }

                    # log payor appeal review
                    self.audit_logger.log_interaction(
                        phase="phase_3_claims",
                        agent="payor",
                        action="claim_appeal_review",
                        system_prompt=payor_system_prompt,
                        user_prompt=payor_appeal_prompt,
                        llm_response=response.content,
                        parsed_output=appeal_decision,
                        metadata={"appeal_iteration": appeal_iteration, "appeal_outcome": appeal_decision.get("appeal_outcome"), "cache_hit": payor_cache_hit}
                    )

                    # check appeal outcome
                    if appeal_decision.get("appeal_outcome") == "approved":
                        state.medication_authorization.authorization_status = "approved"
                        state.appeal_successful = True
                        claim_approved = True
                    elif appeal_decision.get("appeal_outcome") == "partial":
                        state.medication_authorization.authorization_status = "partial"
                        state.appeal_successful = True
                        claim_approved = True
                    else:
                        # appeal denied - provider could appeal again or stop
                        # for simplicity, continue loop until max iterations
                        denial_reason = appeal_decision.get("denial_reason", "Appeal denied")

        return state
    def _phase_4_medication_financial(
        self,
        state: EncounterState,
        case: Dict[str, Any]
    ) -> EncounterState:
        """
        phase 4: financial settlement based on CLAIM outcome (not pa outcome)

        KEY: payment only happens if CLAIM approved in phase 3
        pa approval does NOT guarantee payment
        """
        state.settlement_date = (state.appeal_date or state.review_date) + timedelta(days=7)

        cost_ref = case.get("cost_reference", {})

        # payment based on CLAIM outcome (phase 3), not PA outcome (phase 2)
        claim_approved = (
            state.medication_authorization and
            state.medication_authorization.authorization_status == "approved"
        )

        if claim_approved:
            acquisition_cost = cost_ref.get("drug_acquisition_cost", 7800.0)
            admin_fee = cost_ref.get("administration_fee", 150.0)
            total_cost = acquisition_cost + admin_fee

            # typical ma copay: 20% patient, 80% plan
            patient_copay = total_cost * 0.20
            payer_payment = total_cost * 0.80
        else:
            # claim denied - provider gets $0 even though they already treated patient
            acquisition_cost = cost_ref.get("drug_acquisition_cost", 7800.0)
            admin_fee = cost_ref.get("administration_fee", 150.0)
            total_cost = acquisition_cost + admin_fee
            patient_copay = 0.0
            payer_payment = 0.0

        # administrative costs: pa review + claim review + appeals
        pa_review_cost = cost_ref.get("pa_review_cost", 75.0)
        claim_review_cost = cost_ref.get("claim_review_cost", 50.0)
        appeal_cost = 0.0
        if state.appeal_filed:
            appeal_cost = cost_ref.get("appeal_cost", 180.0)

        total_admin_cost = pa_review_cost + claim_review_cost + appeal_cost

        state.medication_financial = MedicationFinancialSettlement(
            medication_name=case.get("medication_request", {}).get("medication_name", "Unknown"),
            j_code=case.get("medication_request", {}).get("j_code"),
            acquisition_cost=acquisition_cost,
            administration_fee=admin_fee,
            total_billed=total_cost,
            payer_payment=payer_payment,
            patient_copay=patient_copay,
            prior_auth_cost=pa_review_cost + claim_review_cost,
            appeal_cost=appeal_cost,
            total_administrative_cost=total_admin_cost
        )

        return state

    def get_cache_stats(self) -> Dict[str, Any]:
        """get worm cache statistics"""
        if self.cache:
            return self.cache.get_stats()
        return {"cache_disabled": True}

    def export_cache(self, output_path: str):
        """export cache to file for reproducibility"""
        if self.cache:
            self.cache.export_cache(output_path)

    def clear_cache(self):
        """clear all cache entries"""
        if self.cache:
            self.cache.clear()
