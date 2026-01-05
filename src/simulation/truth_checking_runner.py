# """
# truth checking runner for phase 2 and phase 3

# runs truth checker on provider outputs and saves results to experiments/results/
# """

# import os
# import json
# from typing import Dict, Any, TYPE_CHECKING

# from src.models.schemas import EncounterState

# if TYPE_CHECKING:
#     from src.simulation.game_runner import UtilizationReviewSimulation


# def extract_provider_request_from_phase2(audit_logger) -> str:
#     """
#     extract provider PA request letter from phase 2 audit log

#     the PA request is logged in phase_2_utilization_review with action containing 'treatment request'
#     we want the full LLM response text that contains the clinical justification
#     """
#     if not audit_logger:
#         return ""

#     audit_log = audit_logger.get_audit_log()

#     for interaction in audit_log.interactions:
#         if interaction.phase == "phase_2_utilization_review" and interaction.action == "treatment_request" and interaction.agent == "provider":
#             return interaction.llm_response

#     return ""


# def extract_provider_appeal_from_phase3(audit_logger) -> str:
#     """
#     extract provider appeal letter from phase 3 audit log

#     used to detect if provider doubles down on hallucinations during appeals
#     """
#     if not audit_logger:
#         return ""

#     audit_log = audit_logger.get_audit_log()

#     for interaction in audit_log.interactions:
#         if interaction.phase == "phase_3_claims" and interaction.action == "appeal_submission" and interaction.agent == "provider":
#             return interaction.llm_response

#     return ""


# def run_truth_check_phase2(
#     sim: "UtilizationReviewSimulation",
#     state: EncounterState,
#     case: Dict[str, Any]
# ) -> EncounterState:
#     """
#     run truth checker on phase 2 PA request

#     extracts provider request and verifies against ground truth
#     saves result to experiments/results/ and attaches to state
#     """
#     provider_request = extract_provider_request_from_phase2(sim.audit_logger)
#     if not provider_request:
#         return state

#     ground_truth = case.get("environment_hidden_data", {})

#     # extract phase 2 interaction history from audit log
#     phase_2_interactions = []
#     test_results_returned = {}
#     if state.audit_log:
#         for interaction in state.audit_log.interactions:
#             if interaction.phase == "phase_2_utilization_review":
#                 # extract request summary
#                 request_summary = "N/A"
#                 if interaction.agent == "provider":
#                     req_service = interaction.parsed_output.get("requested_service", {})
#                     request_summary = req_service.get("service_name", "N/A")

#                 # extract response summary (test results from environment)
#                 response_summary = None
#                 if interaction.agent == "environment":
#                     response_summary = interaction.parsed_output
#                     # collect test results
#                     if "test_results" in interaction.parsed_output:
#                         test_results_returned.update(interaction.parsed_output["test_results"])

#                 phase_2_interactions.append({
#                     "iteration": interaction.metadata.get("iteration", "?"),
#                     "agent": interaction.agent,
#                     "action": interaction.action,
#                     "request_summary": request_summary,
#                     "response_summary": response_summary,
#                     "full_request": interaction.parsed_output
#                 })

#     # build full context for truth checker
#     # truth checker has access to BOTH policy documents (provider and payor cannot see each other's)
#     full_context = {
#         "interaction_history": phase_2_interactions,
#         "patient_visible_data": case.get("patient_visible_data", {}),
#         "test_results_returned": test_results_returned,
#         "behavioral_params": {
#             "provider": sim.provider_params,
#             "payor": sim.payor_params
#         },
#         # BOTH policies for asymmetry analysis (agents only see their own)
#         "provider_policy": state.provider_policy_view,  # GOLD 2023 (fuzzy)
#         "payor_policy": state.payor_policy_view  # InterQual 2022 (strict)
#     }

#     # run truth checker with full context
#     truth_result = sim.truth_checker.check_claims(
#         provider_output=provider_request,
#         ground_truth=ground_truth,
#         case_id=case["case_id"],
#         phase="phase_2_utilization_review",
#         full_context=full_context
#     )

#     # save to experiments/results/ (use absolute path from project root)
#     project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
#     results_dir = os.path.join(project_root, "experiments", "results")
#     os.makedirs(results_dir, exist_ok=True)
#     output_path = os.path.join(results_dir, f"{case['case_id']}_phase2_truth_check.json")
#     with open(output_path, 'w') as f:
#         json.dump(truth_result.model_dump(), f, indent=2)

#     # attach to state
#     state.truth_check_phase2 = truth_result

#     return state


# def run_truth_check_phase3(
#     sim: "UtilizationReviewSimulation",
#     state: EncounterState,
#     case: Dict[str, Any]
# ) -> EncounterState:
#     """
#     run truth checker on phase 3 appeal letter

#     detects if provider doubles down on hallucinations during appeals
#     saves result to experiments/results/ and attaches to state
#     """
#     provider_appeal = extract_provider_appeal_from_phase3(sim.audit_logger)
#     if not provider_appeal:
#         return state

#     ground_truth = case.get("environment_hidden_data", {})

#     # extract phase 3 interaction history (for context in appeals)
#     phase_3_interactions = []
#     if state.audit_log:
#         for interaction in state.audit_log.interactions:
#             if interaction.phase == "phase_3_claims":
#                 phase_3_interactions.append({
#                     "iteration": interaction.metadata.get("iteration", "?"),
#                     "agent": interaction.agent,
#                     "action": interaction.action,
#                     "full_request": interaction.parsed_output
#                 })

#     # build full context (reuse patient data and test results from phase 2)
#     # truth checker has access to BOTH policy documents
#     full_context = {
#         "interaction_history": phase_3_interactions,
#         "patient_visible_data": case.get("patient_visible_data", {}),
#         "behavioral_params": {
#             "provider": sim.provider_params,
#             "payor": sim.payor_params
#         },
#         # BOTH policies for asymmetry analysis
#         "provider_policy": state.provider_policy_view,  # GOLD 2023
#         "payor_policy": state.payor_policy_view  # InterQual 2022
#     }

#     # run truth checker with full context
#     truth_result = sim.truth_checker.check_claims(
#         provider_output=provider_appeal,
#         ground_truth=ground_truth,
#         case_id=case["case_id"],
#         phase="phase_3_appeal",
#         full_context=full_context
#     )

#     # save to experiments/results/ (use absolute path from project root)
#     project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
#     results_dir = os.path.join(project_root, "experiments", "results")
#     os.makedirs(results_dir, exist_ok=True)
#     output_path = os.path.join(results_dir, f"{case['case_id']}_phase3_truth_check.json")
#     with open(output_path, 'w') as f:
#         json.dump(truth_result.model_dump(), f, indent=2)

#     # attach to state
#     state.truth_check_phase3 = truth_result

#     return state
