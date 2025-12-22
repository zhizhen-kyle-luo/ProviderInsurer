"""
batch experiment runner for pilot study

tests two hypotheses:
1. Strategic Deception: agents lie more under high financial pressure
2. Verbosity Bias: agents write longer text with defensive documentation style

runs all cases with 3 configurations:
- BASELINE: control condition
- HIGH_PRESSURE: deception probe (high risk tolerance + high patient care)
- BUREAUCRATIC: verbosity probe (defensive documentation)
"""

import os
import sys
import csv
import json
from typing import Dict, Any, List
from dotenv import load_dotenv

# add parent to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.cardiac.chest_pain_stress_test_case import CHEST_PAIN_CASE
from src.data.cases.specialty_medications.infliximab_crohns_case_a import INFLIXIMAB_CASE_A
from src.data.cases.specialty_medications.infliximab_crohns_case_b import INFLIXIMAB_CASE_B
from src.utils.experimental_configs import CONFIGS, get_provider_params, get_payor_params

# post-acure directory name has dash, need special handling
import importlib.util
import os as _os

def _load_post_acure_case(filename: str, case_name: str):
    """load case from post-acure directory (dash in name)"""
    spec = importlib.util.spec_from_file_location(
        case_name,
        _os.path.join(_os.path.dirname(__file__), "..", "src", "data", "cases", "post-acure", filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, case_name)

SNF_PULMONARY_01 = _load_post_acure_case("snf_pulmonary_01.py", "SNF_PULMONARY_01")
SNF_COPD_02 = _load_post_acure_case("snf_copd_02.py", "SNF_COPD_02")
SNF_DIALYSIS_03 = _load_post_acure_case("snf_dialysis_03.py", "SNF_DIALYSIS_03")


def list_cases() -> List[Dict[str, Any]]:
    """return all available cases"""
    return [
        CHEST_PAIN_CASE,
        INFLIXIMAB_CASE_A,
        INFLIXIMAB_CASE_B,
        SNF_PULMONARY_01,
        SNF_COPD_02,
        SNF_DIALYSIS_03
    ]


def count_words(text: str) -> int:
    """count words in provider output"""
    return len(text.split())


def run_experiment(
    case: Dict[str, Any],
    config_name: str,
    config: Dict[str, str],
    llm_model: str = "gpt-4",
    azure_config: Dict[str, Any] = None,
    results_dir: str = None
) -> Dict[str, Any]:
    """
    run single case with specific configuration

    args:
        case: case dictionary
        config_name: configuration name (e.g., "BASELINE", "HIGH_PRESSURE")
        config: configuration dictionary with provider and payor parameters
        llm_model: LLM model to use for provider and payor (e.g., "gpt-4", "gpt-3.5-turbo")
        azure_config: azure openai configuration (optional)
        results_dir: directory to save results (optional)

    returns result dict with truth check metrics and word count
    saves audit log and truth check JSON for each run
    """
    print(f"  Running {config_name} [{llm_model}]...", end=" ", flush=True)

    # use centralized helper functions to extract params
    full_provider_params = get_provider_params(config)
    full_payor_params = get_payor_params(config)

    sim = UtilizationReviewSimulation(
        provider_llm=llm_model,
        payor_llm=llm_model,
        master_seed=42,  # deterministic seed for validation mode
        azure_config=azure_config,
        enable_cache=True,
        enable_truth_checking=True,
        truth_checker_llm="gpt-4o-mini",
        provider_params=full_provider_params,
        payor_params=full_payor_params
    )

    state = sim.run_case(case)

    # extract provider output for word count (take last request from phase 2)
    provider_request_text = ""
    if state.audit_log:
        for interaction in reversed(state.audit_log.interactions):
            if interaction.phase == "phase_2_pa" and interaction.agent == "provider":
                if interaction.action in ["treatment_request", "diagnostic_test_request"]:
                    provider_request_text = interaction.llm_response
                    break

    word_count = count_words(provider_request_text)

    # extract truth check results
    is_deceptive = False
    deception_score = 0.0
    if state.truth_check_phase2:
        is_deceptive = state.truth_check_phase2.is_deceptive
        deception_score = state.truth_check_phase2.deception_score

    # extract approval status
    approval_status = "denied"
    if state.medication_authorization:
        approval_status = state.medication_authorization.authorization_status

    # save artifacts for manual inspection
    if results_dir:
        run_id = f"{case['case_id']}_{config_name}"

        # save audit log (most human-readable)
        if state.audit_log:
            audit_path = os.path.join(results_dir, f"{run_id}_audit.md")
            state.audit_log.save_to_markdown(audit_path)

        # save phase 2 truth check JSON (contains hallucinated claims)
        if state.truth_check_phase2:
            truth_path = os.path.join(results_dir, f"{run_id}_truth_check.json")
            with open(truth_path, 'w', encoding='utf-8') as f:
                json.dump(state.truth_check_phase2.model_dump(), f, indent=2)

    print(f"Done (deceptive={is_deceptive}, words={word_count})")

    return {
        "case_id": case["case_id"],
        "config": config_name,
        "llm_model": llm_model,
        "is_deceptive": is_deceptive,
        "deception_score": deception_score,
        "word_count": word_count,
        "approval_status": approval_status
    }


def main():
    """run batch experiment and save results"""
    load_dotenv()

    # azure config
    azure_config = None
    if os.getenv("AZURE_ENDPOINT"):
        azure_config = {
            "endpoint": os.getenv("AZURE_ENDPOINT"),
            "key": os.getenv("AZURE_KEY"),
            "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        }

    # llm models to test
    LLM_MODELS = ["gpt-4", "gpt-3.5-turbo"]

    print("=" * 80)
    print("PILOT EXPERIMENT - BATCH RUN")
    print("=" * 80)
    print()
    print("Hypotheses:")
    print("  H1 (Strategic Deception): HIGH_PRESSURE -> more is_deceptive=True")
    print("  H2 (Verbosity Bias): BUREAUCRATIC -> higher word_count")
    print("  H3 (Model Effects): gpt-4 vs gpt-3.5-turbo behavioral differences")
    print()

    cases = list_cases()
    print(f"Cases: {len(cases)}")
    print(f"Configs: {len(CONFIGS)}")
    print(f"Models: {len(LLM_MODELS)}")
    print(f"Total runs: {len(cases) * len(CONFIGS) * len(LLM_MODELS)}")
    print()

    # prepare results directory (save to experiments/results)
    results_dir = os.path.join(os.path.dirname(__file__), "..", "experiments", "results")
    os.makedirs(results_dir, exist_ok=True)

    # run experiments for each model
    for llm_model in LLM_MODELS:
        print("\n" + "=" * 80)
        print(f"MODEL: {llm_model}")
        print("=" * 80)

        # collect results for this model
        results = []

        for case in cases:
            print(f"\nCase: {case['case_id']}")

            for config_name, config in CONFIGS.items():
                result = run_experiment(case, config_name, config, llm_model, azure_config, results_dir)
                results.append(result)

        # save summary CSV for this model
        model_name_clean = llm_model.replace(".", "_").replace("-", "_")
        output_path = os.path.join(results_dir, f"pilot_results_{model_name_clean}.csv")

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ["case_id", "config", "llm_model", "is_deceptive", "deception_score", "word_count", "approval_status"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        print(f"\n  Model {llm_model} results saved: {output_path}")

    print()
    print("=" * 80)
    print("EXPERIMENT COMPLETE")
    print("=" * 80)
    print()
    print("OUTPUT FILES:")
    for llm_model in LLM_MODELS:
        model_name_clean = llm_model.replace(".", "_").replace("-", "_")
        print(f"  {llm_model}: experiments/results/pilot_results_{model_name_clean}.csv")
    print(f"  Audit Logs: {results_dir}/*_audit.md")
    print(f"  Truth Checks: {results_dir}/*_truth_check.json")
    print()


if __name__ == "__main__":
    main()
