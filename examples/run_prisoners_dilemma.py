"""
Prisoner's Dilemma simulation for npj Digital Medicine paper

Runs COPD grey zone case through 2x2 game theory matrix:
- Provider axis: "Cares" (high patient_care_weight) vs "Defects" (low patient_care_weight)
- Insurer axis: "Cares" (low cost_focus) vs "Defects" (high cost_focus)

Quadrants:
  CC: both cooperate (patient-centered care)
  CD: provider cares, insurer defects (adversarial insurer)
  DC: provider defects, insurer cares (profit-maximizing provider)
  DD: both defect (adversarial system)
"""

import sys
import os
import csv

# project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# outputs directory
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

from dotenv import load_dotenv
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.grey_zones import COPD_RESPIRATORY_FAILURE_GREY

# game theory configurations
GAME_CONFIGS = {
    "CC": {
        "name": "Cooperate/Cooperate",
        "description": "Both prioritize patient welfare",
        "provider_params": {
            "patient_care_weight": "high",
            "documentation_style": "moderate",
            "risk_tolerance": "moderate",
            "ai_adoption": "moderate"
        },
        "payor_params": {
            "cost_focus": "low",
            "denial_threshold": "low",
            "ai_reliance": "moderate",
            "time_horizon": "long-term"
        }
    },
    "CD": {
        "name": "Cooperate/Defect",
        "description": "Provider cares, Insurer aggressive",
        "provider_params": {
            "patient_care_weight": "high",
            "documentation_style": "moderate",
            "risk_tolerance": "moderate",
            "ai_adoption": "moderate"
        },
        "payor_params": {
            "cost_focus": "high",
            "denial_threshold": "high",
            "ai_reliance": "high",
            "time_horizon": "short-term"
        }
    },
    "DC": {
        "name": "Defect/Cooperate",
        "description": "Provider profit-focused, Insurer lenient",
        "provider_params": {
            "patient_care_weight": "low",
            "documentation_style": "minimal",
            "risk_tolerance": "high",
            "ai_adoption": "moderate"
        },
        "payor_params": {
            "cost_focus": "low",
            "denial_threshold": "low",
            "ai_reliance": "moderate",
            "time_horizon": "long-term"
        }
    },
    "DD": {
        "name": "Defect/Defect",
        "description": "Both adversarial",
        "provider_params": {
            "patient_care_weight": "low",
            "documentation_style": "minimal",
            "risk_tolerance": "high",
            "ai_adoption": "moderate"
        },
        "payor_params": {
            "cost_focus": "high",
            "denial_threshold": "high",
            "ai_reliance": "high",
            "time_horizon": "short-term"
        }
    }
}


def count_phase_iterations(state):
    """count iterations in phase 2 and phase 3"""
    phase_2_turns = 0
    phase_3_turns = 0

    if state.audit_log:
        for interaction in state.audit_log.interactions:
            if interaction.phase == "phase_2_pa":
                phase_2_turns += 1
            elif interaction.phase == "phase_3_claims":
                phase_3_turns += 1

    # each turn has provider + payor, so divide by 2
    return phase_2_turns // 2, phase_3_turns // 2


def run_quadrant(quadrant_key, config):
    """run simulation for one quadrant of the game matrix"""
    print(f"\n{'='*60}")
    print(f"QUADRANT: {quadrant_key} - {config['name']}")
    print(f"  {config['description']}")
    print(f"{'='*60}")

    sim = UtilizationReviewSimulation(
        provider_llm="azure",
        payor_llm="azure",
        provider_params=config["provider_params"],
        payor_params=config["payor_params"],
        enable_cache=True,
        master_seed=42
    )

    state = sim.run_case(COPD_RESPIRATORY_FAILURE_GREY)

    # count phase iterations
    phase_2_turns, phase_3_turns = count_phase_iterations(state)

    # extract financials
    total_billed = state.phase_3_billed_amount if state.phase_3_billed_amount else 0.0
    total_paid = state.medication_financial.payer_payment if state.medication_financial else 0.0
    unpaid = total_billed - total_paid

    # diagnosis code
    dx_code = state.phase_3_diagnosis_code if state.phase_3_diagnosis_code else "N/A"

    # determine final status
    pa_status = state.medication_authorization.authorization_status if state.medication_authorization else "N/A"
    if pa_status == "denied":
        final_status = "DENIED"
    elif state.claim_pended and state.claim_abandoned_via_pend:
        final_status = "ABANDONED"
    elif state.claim_rejected:
        final_status = "REJECTED"
    elif pa_status in ["approved", "pending_info"]:
        final_status = "APPROVED"
    else:
        final_status = pa_status.upper()

    print(f"\n  Phase 2 (PA) turns: {phase_2_turns}")
    print(f"  Phase 3 (Claims) turns: {phase_3_turns}")
    print(f"  Final Status: {final_status}")
    print(f"  Diagnosis Code: {dx_code}")
    print(f"  Provider Billed: ${total_billed:,.2f}")
    print(f"  Provider Paid: ${total_paid:,.2f}")
    print(f"  Unpaid/Denied: ${unpaid:,.2f}")

    # save audit log
    if state.audit_log:
        run_folder = os.path.join(OUTPUTS_DIR, f"prisoners_dilemma_{quadrant_key}")
        state.audit_log.save_to_folder(run_folder)
        print(f"  Audit Log: {run_folder}/")

    return {
        "quadrant": quadrant_key,
        "name": config["name"],
        "final_status": final_status,
        "dx_code": dx_code,
        "phase_2_turns": phase_2_turns,
        "phase_3_turns": phase_3_turns,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "unpaid": unpaid
    }


def print_summary_table(results):
    """print summary table"""
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()
    print(f"{'Quadrant':<12} {'Status':<12} {'DX Code':<10} {'P2 Turns':>10} {'P3 Turns':>10} {'Billed':>12} {'Paid':>12} {'Unpaid':>12}")
    print("-" * 100)

    for r in results:
        print(f"{r['quadrant']:<12} {r['final_status']:<12} {r['dx_code']:<10} {r['phase_2_turns']:>10} {r['phase_3_turns']:>10} ${r['total_billed']:>10,.2f} ${r['total_paid']:>10,.2f} ${r['unpaid']:>10,.2f}")

    print("-" * 100)


def save_results_csv(results, filepath):
    """save results to CSV"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    fieldnames = [
        "quadrant", "name", "final_status", "dx_code",
        "phase_2_turns", "phase_3_turns",
        "total_billed", "total_paid", "unpaid"
    ]

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nCSV saved to: {filepath}")


def main():
    print("=" * 80)
    print("PRISONER'S DILEMMA SIMULATION")
    print("=" * 80)
    print()
    print("Case: COPD Respiratory Failure Grey Zone")
    print("  - Coding options: J96.01 ($7,800) vs J44.1 ($5,200)")
    print()
    print("Game Structure:")
    print("  Provider: COOPERATE = high patient_care_weight")
    print("            DEFECT = low patient_care_weight")
    print("  Insurer:  COOPERATE = low cost_focus, low denial_threshold")
    print("            DEFECT = high cost_focus, high denial_threshold")
    print()

    # ensure outputs directory exists
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    results = []

    for quadrant_key, config in GAME_CONFIGS.items():
        result = run_quadrant(quadrant_key, config)
        results.append(result)

    print_summary_table(results)

    csv_path = os.path.join(PROJECT_ROOT, "experiments", "results", "prisoners_dilemma_results.csv")
    save_results_csv(results, csv_path)

    print()
    print("=" * 80)
    print("COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
