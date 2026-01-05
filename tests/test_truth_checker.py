"""
test truth checker with SNF pulmonary case

demonstrates:
1. running simulation with truth checking enabled
2. automatic persistence of results to experiments/results/
3. audit log with truth check summary
"""

import os
import sys
from dotenv import load_dotenv

# add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.simulation.game_runner import UtilizationReviewSimulation
import importlib.util
import os

# import SNF case from post-acure directory (dash in name requires special handling)
spec = importlib.util.spec_from_file_location(
    "snf_pulmonary_01",
    os.path.join(os.path.dirname(__file__), "..", "src", "data", "cases", "post-acure", "snf_pulmonary_01.py")
)
snf_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snf_module)
SNF_PULMONARY_01 = snf_module.SNF_PULMONARY_01

def main():
    load_dotenv()

    # check for azure config (match variable names in .env)
    azure_config = None
    if os.getenv("AZURE_ENDPOINT"):
        azure_config = {
            "endpoint": os.getenv("AZURE_ENDPOINT"),
            "key": os.getenv("AZURE_KEY"),
            "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        }

    print("=" * 80)
    print("TRUTH CHECKER TEST - SNF Pulmonary Case")
    print("=" * 80)
    print()
    print("This test will:")
    print("1. Run the SNF pulmonary case with truth checking enabled")
    print("2. Save truth check results to experiments/results/")
    print("3. Generate audit log with truth check summary")
    print()

    # initialize simulation with truth checking enabled
    sim = UtilizationReviewSimulation(
        provider_llm="gpt-4",
        payor_llm="gpt-4",
        master_seed=42,
        azure_config=azure_config,
        enable_cache=True,
        enable_truth_checking=True,  # ENABLE TRUTH CHECKING
        truth_checker_llm="gpt-4o-mini"  # lightweight model for fact-checking
    )

    print(f"Running case: {SNF_PULMONARY_01['case_id']}")
    print(f"Patient: {SNF_PULMONARY_01['patient_visible_data']['age']}yo {SNF_PULMONARY_01['patient_visible_data']['sex']}")
    print(f"Chief Complaint: {SNF_PULMONARY_01['patient_visible_data']['chief_complaint']}")
    print()

    # run simulation
    state = sim.run_case(SNF_PULMONARY_01)

    print("=" * 80)
    print("SIMULATION COMPLETE")
    print("=" * 80)
    print()

    # display results
    print("PHASE 2 RESULTS:")
    print(f"  PA Status: {state.authorization_request.authorization_status if state.authorization_request else 'N/A'}")
    print(f"  Denial Occurred: {state.denial_occurred}")
    print()

    # truth check results (Phase 2)
    if state.truth_check_phase2:
        print("TRUTH CHECK - PHASE 2 (PA REQUEST):")
        print(f"  Deceptive: {state.truth_check_phase2.is_deceptive}")
        print(f"  Deception Score: {state.truth_check_phase2.deception_score:.3f}")
        print(f"  Hallucinated Claims: {len(state.truth_check_phase2.hallucinated_claims)}")
        if state.truth_check_phase2.hallucinated_claims:
            print("  Specific Lies:")
            for claim in state.truth_check_phase2.hallucinated_claims:
                print(f"    - {claim}")
        print()

    # phase 3 results
    print("PHASE 3 RESULTS:")
    print(f"  Appeal Filed: {state.appeal_filed}")
    print(f"  Appeal Successful: {state.appeal_successful}")
    print()

    # truth check results (Phase 3)
    if state.truth_check_phase3:
        print("TRUTH CHECK - PHASE 3 (APPEAL):")
        print(f"  Deceptive: {state.truth_check_phase3.is_deceptive}")
        print(f"  Deception Score: {state.truth_check_phase3.deception_score:.3f}")
        print(f"  Hallucinated Claims: {len(state.truth_check_phase3.hallucinated_claims)}")
        if state.truth_check_phase3.hallucinated_claims:
            print("  Specific Lies:")
            for claim in state.truth_check_phase3.hallucinated_claims:
                print(f"    - {claim}")

        # check if provider doubled down on lies
        if state.truth_check_phase2:
            doubled_down = state.truth_check_phase3.deception_score > state.truth_check_phase2.deception_score
            print()
            print(f"  DOUBLED DOWN ON LIES: {'YES' if doubled_down else 'NO'}")
            print(f"    (Phase 2: {state.truth_check_phase2.deception_score:.3f} → Phase 3: {state.truth_check_phase3.deception_score:.3f})")
        print()

    # output locations
    print("=" * 80)
    print("OUTPUT FILES")
    print("=" * 80)
    print()
    print("Truth Check Results:")
    results_dir = os.path.join(os.path.dirname(__file__), "..", "experiments", "results")
    os.makedirs(results_dir, exist_ok=True)
    phase2_path = os.path.join(results_dir, f"{SNF_PULMONARY_01['case_id']}_phase2_truth_check.json")
    phase3_path = os.path.join(results_dir, f"{SNF_PULMONARY_01['case_id']}_phase3_truth_check.json")
    print(f"  Phase 2: {phase2_path}")
    if os.path.exists(phase2_path):
        print(f"    [OK] File created ({os.path.getsize(phase2_path)} bytes)")
    print(f"  Phase 3: {phase3_path}")
    if os.path.exists(phase3_path):
        print(f"    [OK] File created ({os.path.getsize(phase3_path)} bytes)")
    print()

    # save audit log to experiments/results (use absolute path)
    audit_path = os.path.join(results_dir, f"{SNF_PULMONARY_01['case_id']}_audit_log.md")
    state.audit_log.save_to_markdown(audit_path)
    print(f"Audit Log: {audit_path}")
    if os.path.exists(audit_path):
        print(f"  [OK] File created ({os.path.getsize(audit_path)} bytes)")
    print()

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Review the truth check JSON files in experiments/results/")
    print("2. Review the audit log markdown file with truth check summary")
    print("3. Check if provider hallucinated any clinical facts")
    print()

if __name__ == "__main__":
    main()
