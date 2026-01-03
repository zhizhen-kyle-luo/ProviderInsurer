from typing import Dict, Any
from datetime import timedelta
import time
import random
import json
import os
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from src.models.schemas import (
    EncounterState,
    CaseType,
    AdmissionNotification,
    PatientDemographics,
    InsuranceInfo,
    ClinicalPresentation,
    FrictionMetrics
)
from src.data.policies import COPDPolicies
from src.agents.provider import ProviderAgent
from src.agents.payor import PayorAgent
from src.utils.cpt_calculator import CPTCostCalculator
from src.utils.audit_logger import AuditLogger
from src.utils.worm_cache import WORMCache
from src.utils.cached_llm import CachedLLM
from src.evaluation.truth_checker import TruthChecker
from src.utils.prompts import (
    DEFAULT_PROVIDER_PARAMS,
    DEFAULT_PAYOR_PARAMS,
    MAX_ITERATIONS,
    NOISE_PROBABILITY
)
from src.simulation.phases import (
    run_phase_2_utilization_review,
    run_phase_3_claims,
    run_phase_4_financial
)
from src.simulation.test_generation import generate_test_result
from src.simulation.truth_checking_runner import (
    run_truth_check_phase2,
    run_truth_check_phase3
)


def _get_project_cache_dir() -> str:
    """get absolute path to project root .worm_cache directory"""
    # navigate from src/simulation/game_runner.py -> MASH root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, ".worm_cache")


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
        provider_llm: str = "azure",
        payor_llm: str = "azure",
        provider_copilot_llm: str = None,  # None = use base model (strong), "azure" = use copilot deployment (weak)
        payor_copilot_llm: str = None,     # None = use base model (strong), "azure" = use copilot deployment (weak)
        master_seed: int = None,
        max_iterations: int = None,
        azure_config: Dict[str, Any] = None,
        cache_dir: str = None,
        enable_cache: bool = True,
        enable_truth_checking: bool = False,
        truth_checker_llm: str = "azure",
        provider_params: Dict[str, str] = None,
        payor_params: Dict[str, str] = None
    ):
        self.master_seed = master_seed if master_seed is not None else int(time.time())
        self.rng = random.Random(self.master_seed)
        self.max_iterations = max_iterations if max_iterations is not None else MAX_ITERATIONS
        self.enable_truth_checking = enable_truth_checking

        # store behavioral parameters for prompts
        self.provider_params = provider_params if provider_params is not None else DEFAULT_PROVIDER_PARAMS
        self.payor_params = payor_params if payor_params is not None else DEFAULT_PAYOR_PARAMS

        # use project root cache directory if not specified
        cache_path = cache_dir if cache_dir is not None else _get_project_cache_dir()
        self.cache = WORMCache(cache_dir=cache_path, enable_persistence=enable_cache) if enable_cache else None

        provider_model = self._create_llm(provider_llm, azure_config)
        payor_model = self._create_llm(payor_llm, azure_config)

        # copilot models for draft generation (automation strength knob)
        # if copilot_llm is None, use same model as base (strong copilot)
        # if copilot_llm is "azure", use AZURE_COPILOT_DEPLOYMENT_NAME (weak copilot)
        if provider_copilot_llm:
            # weak copilot: use separate copilot deployment
            provider_copilot_model = self._create_llm(
                provider_copilot_llm, azure_config, copilot_role="provider"
            )
            provider_copilot_model_name = provider_copilot_llm
        else:
            # strong copilot: use same model as base (no copilot_role)
            provider_copilot_model = provider_model
            provider_copilot_model_name = provider_llm

        if payor_copilot_llm:
            # weak copilot: use separate copilot deployment
            payor_copilot_model = self._create_llm(
                payor_copilot_llm, azure_config, copilot_role="payor"
            )
            payor_copilot_model_name = payor_copilot_llm
        else:
            # strong copilot: use same model as base (no copilot_role)
            payor_copilot_model = payor_model
            payor_copilot_model_name = payor_llm

        if self.cache:
            provider_model = CachedLLM(provider_model, self.cache, agent_name="provider")
            payor_model = CachedLLM(payor_model, self.cache, agent_name="payor")
            provider_copilot_model = CachedLLM(provider_copilot_model, self.cache, agent_name="provider_copilot")
            payor_copilot_model = CachedLLM(payor_copilot_model, self.cache, agent_name="payor_copilot")

        self.provider_copilot = provider_copilot_model
        self.payor_copilot = payor_copilot_model
        self.provider_copilot_name = provider_copilot_model_name
        self.payor_copilot_name = payor_copilot_model_name

        # store base LLMs for oversight editing (use cached versions if available)
        self.provider_base_llm = provider_model
        self.payor_base_llm = payor_model

        # create deterministic LLM for test result generation (temperature=0)
        self.test_result_llm = self._create_llm(provider_llm, azure_config, temperature=0)

        # initialize truth checker if enabled
        if enable_truth_checking:
            truth_checker_model = self._create_llm(truth_checker_llm, azure_config, temperature=0)
            self.truth_checker = TruthChecker(truth_checker_model)
        else:
            self.truth_checker = None

        self.provider = ProviderAgent(provider_model)
        self.payor = PayorAgent(payor_model)
        self.cost_calculator = CPTCostCalculator()
        self.test_result_cache = {}

    def _create_llm(
        self,
        model_name: str,
        azure_config: Dict[str, Any] = None,
        temperature: float = 0.7,
        copilot_role: str = None
    ):
        """
        create LLM instance. for copilots, REQUIRES explicit env var:
        - AZURE_PROVIDER_COPILOT_DEPLOYMENT_NAME (provider copilot)
        - AZURE_PAYOR_COPILOT_DEPLOYMENT_NAME (payor copilot)
        - AZURE_COPILOT_DEPLOYMENT_NAME (shared copilot - for both)
        no fallback to base deployment (will error if not set)
        """
        if azure_config or model_name == "azure":
            import os
            if model_name == "azure" and not azure_config:
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                api_key = os.getenv("AZURE_OPENAI_API_KEY")

                # for copilots, check role-specific env var first, then shared
                # NO FALLBACK to base - must be explicitly set
                if copilot_role:
                    role_upper = copilot_role.upper()
                    deployment = (
                        os.getenv(f"AZURE_{role_upper}_COPILOT_DEPLOYMENT_NAME") or
                        os.getenv("AZURE_COPILOT_DEPLOYMENT_NAME")
                    )
                    api_version = os.getenv("AZURE_COPILOT_API_VERSION", "2024-12-01-preview")
                else:
                    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
                    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

                missing = []
                if not endpoint:
                    missing.append("AZURE_OPENAI_ENDPOINT")
                if not api_key:
                    missing.append("AZURE_OPENAI_API_KEY")
                if not deployment:
                    if copilot_role:
                        role_upper = copilot_role.upper()
                        missing.append(
                            f"AZURE_{role_upper}_COPILOT_DEPLOYMENT_NAME or AZURE_COPILOT_DEPLOYMENT_NAME"
                        )
                    else:
                        missing.append("AZURE_OPENAI_DEPLOYMENT_NAME")

                if missing:
                    raise ValueError(f"missing azure environment variables: {', '.join(missing)}. check .env file has values set.")

                azure_config = {
                    "endpoint": endpoint,
                    "key": api_key,
                    "deployment_name": deployment,
                    "api_version": api_version
                }
            # some azure deployments (o1, o3-mini) only support default temperature=1
            return AzureChatOpenAI(
                azure_endpoint=azure_config["endpoint"],
                api_key=azure_config["key"],
                azure_deployment=azure_config["deployment_name"],
                api_version=azure_config["api_version"]
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
        return generate_test_result(test_name, case, self.test_result_cache, self.test_result_llm)

    def _build_admission_from_patient_data(self, case: Dict[str, Any]) -> AdmissionNotification:
        """construct AdmissionNotification from patient_visible_data (Golden Schema)"""
        from datetime import datetime

        patient_data = case["patient_visible_data"]
        insurance_data = case.get("insurance_info", {})

        demographics = PatientDemographics(
            patient_id=patient_data.get("patient_id", "UNKNOWN"),
            age=patient_data.get("age", 0),
            sex=patient_data.get("sex", "M"),
            mrn=patient_data.get("patient_id", "UNKNOWN")
        )

        insurance = InsuranceInfo(
            plan_type=insurance_data.get("plan_type", "MA"),
            payer_name=insurance_data.get("payer_name", "Unknown"),
            member_id=patient_data.get("patient_id", "UNKNOWN"),
            authorization_required=insurance_data.get("authorization_required", True)
        )

        admission_date_str = patient_data.get("admission_date", "2024-01-01")
        admission_date = datetime.strptime(admission_date_str, "%Y-%m-%d").date()

        return AdmissionNotification(
            patient_demographics=demographics,
            insurance=insurance,
            admission_date=admission_date,
            admission_source=patient_data.get("admission_source", "Direct"),
            chief_complaint=patient_data.get("chief_complaint", ""),
            preliminary_diagnoses=patient_data.get("medical_history", [])
        )

    def _build_clinical_presentation_from_patient_data(self, case: Dict[str, Any]) -> ClinicalPresentation:
        """construct ClinicalPresentation from patient_visible_data (Golden Schema)"""
        patient_data = case["patient_visible_data"]

        return ClinicalPresentation(
            chief_complaint=patient_data.get("chief_complaint", ""),
            history_of_present_illness=patient_data.get("presenting_symptoms", patient_data.get("chief_complaint", "")),
            vital_signs=patient_data.get("vital_signs", {}),
            physical_exam_findings=patient_data.get("presenting_symptoms", ""),
            medical_history=patient_data.get("medical_history", [])
        )

    def run_case(self, case: Dict[str, Any]) -> EncounterState:
        """
        Run single case through 4-phase utilization review workflow.

        Phase 1: Patient presentation (already complete in case data)
        Phase 2: Prior authorization review
        Phase 3: Appeal process if denied
        Phase 4: Financial settlement

        routes to appropriate workflow based on case_type
        """
        # initialize audit logger for this case (before noise introduction)
        self.audit_logger = AuditLogger(case_id=case["case_id"])

        # apply environmental noise deterministically
        case = self._introduce_noise(case)

        # clear test result cache for new case
        self.test_result_cache = {}

        case_type = case.get("case_type") or case.get("pa_type", CaseType.INPATIENT_ADMISSION)

        # construct structured objects from Golden Schema (patient_visible_data)
        admission = self._build_admission_from_patient_data(case)
        clinical_presentation = self._build_clinical_presentation_from_patient_data(case)

        # load case-specific policies or fallback to generic
        case_id_lower = case["case_id"].lower()
        if "copd" in case_id_lower or "respiratory" in case_id_lower:
            provider_policy = COPDPolicies.GOLD_STANDARD
            payor_policy = COPDPolicies.INTERQUAL_STRICT
        else:
            provider_policy = {"policy_name": "Standard Clinical Guidelines", "hospitalization_indications": []}
            payor_policy = {"policy_name": "Standard Medical Policy", "inpatient_criteria": {"must_meet_one_of": []}}

        state = EncounterState(
            case_id=case["case_id"],
            admission=admission,
            clinical_presentation=clinical_presentation,
            case_type=case_type,
            friction_metrics=FrictionMetrics(),
            provider_policy_view=provider_policy,
            payor_policy_view=payor_policy
        )

        # unified phase 2 workflow (all case types)
        state = run_phase_2_utilization_review(self, state, case)

        # truth checking after phase 2 (if enabled)
        if self.enable_truth_checking and self.truth_checker:
            state = run_truth_check_phase2(self, state, case)

        # phase 3: claims adjudication (if treatment was approved and delivered)
        # applies to ALL PA types
        if (state.medication_authorization and
            state.medication_authorization.authorization_status == "approved"):
            state = run_phase_3_claims(self, state, case, case_type)

            # truth checking after phase 3 appeals (if enabled and appeal was filed)
            if self.enable_truth_checking and self.truth_checker and state.appeal_filed:
                state = run_truth_check_phase3(self, state, case)

        # phase 4: financial settlement
        if state.medication_authorization:
            state = run_phase_4_financial(state, case)

        if "ground_truth" in case:
            state.ground_truth_outcome = case["ground_truth"]["outcome"]
            state.simulation_matches_reality = (
                state.final_authorized_level == case["ground_truth"]["outcome"]
            )

        # finalize audit log and attach to state with behavioral parameters
        summary = self.audit_logger._generate_summary()
        summary["behavioral_parameters"] = {
            "provider": self.provider_params,
            "payor": self.payor_params
        }
        summary["master_seed"] = self.master_seed

        # add friction metrics to summary
        if state.friction_metrics:
            summary["friction_metrics"] = {
                "provider_actions": state.friction_metrics.provider_actions,
                "payor_actions": state.friction_metrics.payor_actions,
                "probing_tests_count": state.friction_metrics.probing_tests_count,
                "escalation_depth": state.friction_metrics.escalation_depth,
                "total_friction": state.friction_metrics.total_friction
            }

        # add truth check summary if available
        if self.enable_truth_checking:
            truth_check_summary = {}
            if state.truth_check_phase2:
                truth_check_summary["phase2"] = {
                    "is_deceptive": state.truth_check_phase2.is_deceptive,
                    "deception_score": state.truth_check_phase2.deception_score,
                    "hallucinated_claims": state.truth_check_phase2.hallucinated_claims
                }
            if state.truth_check_phase3:
                truth_check_summary["phase3"] = {
                    "is_deceptive": state.truth_check_phase3.is_deceptive,
                    "deception_score": state.truth_check_phase3.deception_score,
                    "hallucinated_claims": state.truth_check_phase3.hallucinated_claims
                }
            if truth_check_summary:
                summary["truth_check_summary"] = truth_check_summary

        self.audit_logger.finalize(summary)
        state.audit_log = self.audit_logger.get_audit_log()

        return state

    def run_multiple_cases(self, cases: list[Dict[str, Any]]) -> list[EncounterState]:
        """run multiple cases sequentially"""
        return [self.run_case(case) for case in cases]

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
