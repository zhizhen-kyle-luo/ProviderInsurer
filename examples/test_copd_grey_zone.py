"""
example: run COPD grey zone case to test PEND mechanism on borderline diagnosis

this case tests whether insurer uses PEND to challenge J96.01 (respiratory failure)
coding when technical criteria met (pO2 58) but clinical context suggests
conservative J44.1 (COPD exacerbation) is more appropriate
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.grey_zones import COPD_RESPIRATORY_FAILURE_GREY
from src.utils.prompts import DEFAULT_PAYOR_PARAMS

# payor configured for aggressive cost control (will scrutinize grey zone coding)
AGGRESSIVE_PAYOR_PARAMS = {
    'cost_focus': 'high',  # aggressive cost reduction
    'ai_reliance': 'high',  # AI-driven decisions
    'denial_threshold': 'high',  # conservative interpretation
    'time_horizon': 'short-term'  # minimize immediate costs
}

def main():
    print("=== COPD Respiratory Failure Grey Zone Test ===\n")

    # run with aggressive payor
    print("Running with AGGRESSIVE payor parameters (high cost focus)...\n")
    sim_aggressive = UtilizationReviewSimulation(
        provider_llm="azure",
        payor_llm="azure",
        payor_params=AGGRESSIVE_PAYOR_PARAMS,
        enable_cache=True,
        master_seed=42
    )

    state_aggressive = sim_aggressive.run_case(COPD_RESPIRATORY_FAILURE_GREY)

    # analyze results
    print("\n=== RESULTS (Aggressive Payor) ===")
    print(f"Case ID: {state_aggressive.case_id}")
    print(f"PA Status: {state_aggressive.medication_authorization.authorization_status if state_aggressive.medication_authorization else 'N/A'}")

    if state_aggressive.claim_pended:
        print(f"\n✓ CLAIM PENDED (as expected)")
        print(f"  Pend iterations: {state_aggressive.pend_iterations}")
        print(f"  Resubmission cost: ${state_aggressive.resubmission_cost_incurred:.2f}")
        if state_aggressive.claim_abandoned_via_pend:
            print(f"  ⚠ Provider ABANDONED claim after pend")
        print(f"\nPend mechanism successfully tested - insurer challenged borderline diagnosis")

    if state_aggressive.claim_rejected:
        print(f"\n⚠ CLAIM REJECTED")
        print(f"  Rejection reason: {state_aggressive.medication_authorization.denial_reason}")

    if state_aggressive.medication_financial:
        print(f"\nFINANCIAL OUTCOME:")
        print(f"  Total billed: ${state_aggressive.medication_financial.total_billed:.2f}")
        print(f"  Payer payment: ${state_aggressive.medication_financial.payer_payment:.2f}")
        print(f"  Admin costs: ${state_aggressive.medication_financial.total_administrative_cost:.2f}")

    # save audit log
    if state_aggressive.audit_log:
        output_path = f"outputs/{COPD_RESPIRATORY_FAILURE_GREY['case_id']}_aggressive_audit.md"
        state_aggressive.audit_log.save_to_markdown(output_path)
        print(f"\nAudit log saved to: {output_path}")

    # compare with baseline payor
    print("\n" + "="*60)
    print("Running with BASELINE payor parameters (moderate cost focus)...\n")

    sim_baseline = UtilizationReviewSimulation(
        provider_llm="azure",
        payor_llm="azure",
        payor_params=DEFAULT_PAYOR_PARAMS,
        enable_cache=True,
        master_seed=42
    )

    state_baseline = sim_baseline.run_case(COPD_RESPIRATORY_FAILURE_GREY)

    print("\n=== RESULTS (Baseline Payor) ===")
    print(f"PA Status: {state_baseline.medication_authorization.authorization_status if state_baseline.medication_authorization else 'N/A'}")
    print(f"Claim pended: {state_baseline.claim_pended}")
    print(f"Claim rejected: {state_baseline.claim_rejected}")

    if state_baseline.medication_financial:
        print(f"Payer payment: ${state_baseline.medication_financial.payer_payment:.2f}")

    # comparison
    print("\n=== COMPARISON ===")
    print(f"Aggressive pend rate: {'Yes' if state_aggressive.claim_pended else 'No'}")
    print(f"Baseline pend rate: {'Yes' if state_baseline.claim_pended else 'No'}")

    if state_aggressive.medication_financial and state_baseline.medication_financial:
        payment_diff = state_baseline.medication_financial.payer_payment - state_aggressive.medication_financial.payer_payment
        print(f"\nPayment difference: ${payment_diff:.2f} saved by aggressive payor")

    print("\n" + "="*60)
    print("Grey zone case testing complete!")
    print("\nKey insight: Aggressive payor likely used PEND to challenge J96.01 coding")
    print("even though pO2 58 technically meets respiratory failure threshold.")
    print("This demonstrates regulatory arbitrage: delay payment without formal denial.")

if __name__ == "__main__":
    main()
