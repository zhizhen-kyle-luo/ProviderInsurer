"""
run COPD grey zone case across multiple experimental configurations

tests upcoding dynamics and payor behavior sensitivity:
- BASELINE: standard provider behavior
- HOSTILE_PAYOR: aggressive cost control
- HIGH_PRESSURE: high-risk provider under financial pressure
- MODERATE_PAYOR: balanced payor approach

generates comparative analysis showing how different configurations
affect authorization outcomes, billing, and payment
"""

import sys
import os

# get project root directory (parent of examples/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# outputs directory (at project root level)
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

from dotenv import load_dotenv
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.grey_zones import COPD_RESPIRATORY_FAILURE_GREY
from src.utils.experimental_configs import CONFIGS, get_provider_params, get_payor_params

def print_phase_outcome(state, scenario_name):
    """print detailed outcome analysis based on actual state"""
    print(f"\n=== SCENARIO: {scenario_name} ===")
    print(f"Case ID: {state.case_id}")

    # check phase 2 outcome
    pa_status = state.authorization_request.authorization_status if state.authorization_request else None

    if pa_status == "denied":
        print("\nResult: TOTAL DENIAL OF SERVICE (Phase 2)")
        print("  Access to care BLOCKED - patient never received treatment")
        print(f"  Denial reason: {state.authorization_request.denial_reason}")
        print("\n  Financial impact:")
        print("    Provider: $0 revenue (service not provided)")
        print("    Payor: $0 cost (denied before service)")
        print("    Patient: NO CARE RECEIVED")
        return "phase_2_denial"

    elif pa_status in ["approved", "pending_info"]:
        print(f"\nPhase 2: Service APPROVED - proceeding to treatment and Phase 3 billing")

        # check phase 3 outcome
        if state.claim_pended:
            print("\nPhase 3: CLAIM PENDED")
            print(f"  Pend iterations: {state.pend_iterations}")
            print(f"  Resubmission cost incurred: ${state.resubmission_cost_incurred:.2f}")

            if state.claim_abandoned_via_pend:
                print("  Result: Provider ABANDONED claim")
                print("  Regulatory arbitrage SUCCESS - payor avoided payment without formal denial")
            else:
                print("  Result: Claim eventually processed after resubmission")

        elif state.claim_rejected:
            print("\nPhase 3: CLAIM REJECTED (formal denial)")
            print(f"  Rejection reason: {state.authorization_request.denial_reason}")
            print("  Provider can appeal but must absorb costs")

        else:
            print("\nPhase 3: CLAIM APPROVED")
            print("  Payment processed normally")

        # financial analysis
        if state.financial_settlement:
            print(f"\n  Financial Settlement:")
            print(f"    Total billed: ${state.financial_settlement.total_billed:.2f}")
            print(f"    Payor payment: ${state.financial_settlement.payer_payment:.2f}")
            print(f"    Admin costs: ${state.financial_settlement.total_administrative_cost:.2f}")

            if hasattr(state, 'resubmission_cost_incurred'):
                print(f"    Pend resubmission cost: ${state.resubmission_cost_incurred:.2f}")

        return "phase_3_processed"

    else:
        print(f"\nUnexpected PA status: {pa_status}")
        return "unknown"


def main():
    # configs to test (subset for focused comparison)
    TEST_CONFIGS = ["BASELINE", "HOSTILE_PAYOR", "HIGH_PRESSURE", "MODERATE_PAYOR"]

    print("=" * 80)
    print("COPD GREY ZONE SENSITIVITY ANALYSIS")
    print("=" * 80)
    print("\nClinical Context:")
    print("  - Patient: 70yo male, COPD history, pO2 58 mmHg (just under 60 threshold)")
    print("  - Grey Zone: Technically meets respiratory failure criteria")
    print("  - BUT: No ICU, no BiPAP, only 2L O2, rapid improvement")
    print("  - Coding dispute: J96.01 ($7,800) vs J44.1 ($5,200) = $2,600 difference")
    print(f"\nTesting {len(TEST_CONFIGS)} configurations:")
    for config_name in TEST_CONFIGS:
        print(f"  - {config_name}")
    print("\n" + "=" * 80)

    # ensure outputs directory exists
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    # collect results for comparative analysis
    results = []

    for config_name in TEST_CONFIGS:
        print(f"\n### CONFIG: {config_name} ###\n")

        config = CONFIGS[config_name]
        provider_params = get_provider_params(config)
        payor_params = get_payor_params(config)

        sim = UtilizationReviewSimulation(
            provider_llm="azure",
            payor_llm="azure",
            provider_params=provider_params,
            payor_params=payor_params,
            enable_cache=True,
            master_seed=42
        )

        state = sim.run_case(COPD_RESPIRATORY_FAILURE_GREY)

        # extract metrics
        pa_status = state.authorization_request.authorization_status if state.authorization_request else "N/A"
        total_billed = state.financial_settlement.total_billed if state.financial_settlement else 0.0
        total_paid = state.financial_settlement.payer_payment if state.financial_settlement else 0.0
        iteration_count = len([i for i in state.audit_log.interactions if i.phase == "phase_2_pa"]) if state.audit_log else 0

        # determine final status
        if pa_status == "denied":
            final_status = "Denied (Phase 2)"
        elif state.claim_pended and state.claim_abandoned_via_pend:
            final_status = "Abandoned (Pend)"
        elif state.claim_rejected:
            final_status = "Rejected (Phase 3)"
        elif pa_status in ["approved", "pending_info"]:
            final_status = "Approved"
        else:
            final_status = pa_status

        results.append({
            "config": config_name,
            "total_billed": total_billed,
            "total_paid": total_paid,
            "final_status": final_status,
            "iterations": iteration_count
        })

        print(f"  Status: {final_status}")
        print(f"  Billed: ${total_billed:.2f}")
        print(f"  Paid: ${total_paid:.2f}")
        print(f"  Iterations: {iteration_count}")

        # save to organized folder structure
        if state.audit_log:
            run_folder = os.path.join(OUTPUTS_DIR, f"copd_grey_zone_{config_name}")
            state.audit_log.save_to_folder(run_folder)
            print(f"  Output: {run_folder}/")

    # comparative summary table
    print("\n" + "=" * 80)
    print("COMPARATIVE SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Config':<20} {'Total Billed':>15} {'Total Paid':>15} {'Final Status':<20} {'Iterations':>10}")
    print("-" * 80)

    for result in results:
        print(f"{result['config']:<20} ${result['total_billed']:>14.2f} ${result['total_paid']:>14.2f} {result['final_status']:<20} {result['iterations']:>10}")

    print()
    print("KEY FINDINGS:")

    # find most restrictive
    min_paid = min(results, key=lambda x: x['total_paid'])
    max_paid = max(results, key=lambda x: x['total_paid'])

    print(f"  Most restrictive: {min_paid['config']} (${min_paid['total_paid']:.2f} paid)")
    print(f"  Most permissive: {max_paid['config']} (${max_paid['total_paid']:.2f} paid)")
    print(f"  Payment variance: ${max_paid['total_paid'] - min_paid['total_paid']:.2f}")

    # count denials
    denied_count = sum(1 for r in results if "Denied" in r['final_status'] or "Rejected" in r['final_status'] or "Abandoned" in r['final_status'])
    print(f"  Denial rate: {denied_count}/{len(results)} ({denied_count/len(results)*100:.0f}%)")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
