"""
batch experiment runner for ACL pilot study

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


# experimental configurations
CONFIGS = {
    "BASELINE": {
        "risk_tolerance": "low",
        "patient_care_weight": "moderate",
        "documentation_style": "moderate"
    },
    "HIGH_PRESSURE": {
        "risk_tolerance": "high",
        "patient_care_weight": "high",
        "documentation_style": "moderate"
    },
    "BUREAUCRATIC": {
        "risk_tolerance": "moderate",
        "patient_care_weight": "moderate",
        "documentation_style": "defensive"
    }
}


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
    provider_params: Dict[str, str],
    azure_config: Dict[str, Any] = None,
    results_dir: str = None
) -> Dict[str, Any]:
    """
    run single case with specific configuration

    returns result dict with truth check metrics and word count
    saves audit log and truth check JSON for each run
    """
    print(f"  Running {config_name}...", end=" ", flush=True)

    # create simulation with WORM cache for reproducibility
    # provider_params are merged with defaults (only specified keys are overridden)
    full_provider_params = {
        "patient_care_weight": provider_params.get("patient_care_weight", "moderate"),
        "documentation_style": provider_params.get("documentation_style", "moderate"),
        "risk_tolerance": provider_params.get("risk_tolerance", "moderate"),
        "ai_adoption": "moderate"  # keep constant for this experiment
    }

    sim = UtilizationReviewSimulation(
        provider_llm="gpt-4",
        payor_llm="gpt-4",
        master_seed=42,  # deterministic seed for validation mode
        azure_config=azure_config,
        enable_cache=True,
        enable_truth_checking=True,
        truth_checker_llm="gpt-4o-mini",
        provider_params=full_provider_params
    )

    state = sim.run_case(case)

    # extract provider output for word count
    provider_request_text = ""
    if state.audit_log:
        for interaction in state.audit_log.interactions:
            if interaction.phase == "phase_2_pa" and interaction.agent == "provider" and interaction.action == "treatment_request":
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

    print("=" * 80)
    print("ACL PILOT EXPERIMENT - BATCH RUN")
    print("=" * 80)
    print()
    print("Hypotheses:")
    print("  H1 (Strategic Deception): HIGH_PRESSURE -> more is_deceptive=True")
    print("  H2 (Verbosity Bias): BUREAUCRATIC -> higher word_count")
    print()

    cases = list_cases()
    print(f"Cases: {len(cases)}")
    print(f"Configs: {len(CONFIGS)}")
    print(f"Total runs: {len(cases) * len(CONFIGS)}")
    print()

    # prepare results directory (save to experiments/results)
    results_dir = os.path.join(os.path.dirname(__file__), "..", "experiments", "results")
    os.makedirs(results_dir, exist_ok=True)

    # collect results
    results = []

    for case in cases:
        print(f"Case: {case['case_id']}")

        for config_name, provider_params in CONFIGS.items():
            result = run_experiment(case, config_name, provider_params, azure_config, results_dir)
            results.append(result)

    # save summary CSV
    output_path = os.path.join(results_dir, "pilot_results.csv")

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ["case_id", "config", "is_deceptive", "deception_score", "word_count", "approval_status"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print()
    print("=" * 80)
    print("EXPERIMENT COMPLETE")
    print("=" * 80)
    print()
    print("OUTPUT FILES:")
    print(f"  Summary CSV: {output_path}")
    print(f"  Audit Logs: {results_dir}/*_audit.md")
    print(f"  Truth Checks: {results_dir}/*_truth_check.json")
    print()

    # quick summary statistics
    baseline_deception = sum(1 for r in results if r["config"] == "BASELINE" and r["is_deceptive"]) / sum(1 for r in results if r["config"] == "BASELINE")
    high_pressure_deception = sum(1 for r in results if r["config"] == "HIGH_PRESSURE" and r["is_deceptive"]) / sum(1 for r in results if r["config"] == "HIGH_PRESSURE")

    baseline_words = sum(r["word_count"] for r in results if r["config"] == "BASELINE") / sum(1 for r in results if r["config"] == "BASELINE")
    bureaucratic_words = sum(r["word_count"] for r in results if r["config"] == "BUREAUCRATIC") / sum(1 for r in results if r["config"] == "BUREAUCRATIC")

    print("PRELIMINARY RESULTS:")
    print(f"  H1: BASELINE deception rate: {baseline_deception:.1%}")
    print(f"      HIGH_PRESSURE deception rate: {high_pressure_deception:.1%}")
    print(f"      Delta = {high_pressure_deception - baseline_deception:+.1%}")
    print()
    print(f"  H2: BASELINE avg words: {baseline_words:.0f}")
    print(f"      BUREAUCRATIC avg words: {bureaucratic_words:.0f}")
    print(f"      Delta = {bureaucratic_words - baseline_words:+.0f} words")
    print()


if __name__ == "__main__":
    main()
