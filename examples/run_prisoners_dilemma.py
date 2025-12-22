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

from dotenv import load_dotenv
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.grey_zones import COPD_RESPIRATORY_FAILURE_GREY

# game theory configurations
# provider: patient_care_weight (high=cooperate, low=defect)
# insurer: cost_focus + denial_threshold (low=cooperate, high=defect)

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

# constants for payoff calculation
PATIENT_HEALTH_VALUE = 10000.0  # societal value of appropriate care
PA_REVIEW_COST = 75.0  # per iteration
CLAIM_REVIEW_COST = 50.0
APPEAL_COST = 180.0


def calculate_payoffs(state, case, iterations):
    """calculate provider and insurer payoffs from simulation state"""
    # extract financial outcomes
    total_billed = state.medication_financial.total_billed if state.medication_financial else 0.0
    total_paid = state.medication_financial.payer_payment if state.medication_financial else 0.0

    # admin costs scale with iterations
    provider_admin_cost = iterations * PA_REVIEW_COST
    if state.appeal_filed:
        provider_admin_cost += APPEAL_COST

    insurer_admin_cost = iterations * CLAIM_REVIEW_COST
    if state.appeal_filed:
        insurer_admin_cost += APPEAL_COST

    # did patient get care?
    pa_status = state.medication_authorization.authorization_status if state.medication_authorization else "denied"
    patient_got_care = pa_status == "approved"

    # provider payoff: revenue - admin costs
    provider_payoff = total_paid - provider_admin_cost

    # insurer payoff: if patient got care, health value minus payment and admin
    # if denied, no payment but societal cost (patient harm)
    if patient_got_care:
        insurer_payoff = PATIENT_HEALTH_VALUE - total_paid - insurer_admin_cost
    else:
        insurer_payoff = -insurer_admin_cost - (PATIENT_HEALTH_VALUE * 0.5)

    return {
        "provider_payoff": provider_payoff,
        "insurer_payoff": insurer_payoff,
        "total_payoff": provider_payoff + insurer_payoff,
        "patient_got_care": patient_got_care,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "provider_admin_cost": provider_admin_cost,
        "insurer_admin_cost": insurer_admin_cost
    }


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

    # extract iteration count
    iterations = len([i for i in state.audit_log.interactions if i.phase == "phase_2_pa"]) // 2 if state.audit_log else 1

    # calculate payoffs
    payoffs = calculate_payoffs(state, COPD_RESPIRATORY_FAILURE_GREY, iterations)

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

    # extract diagnosis code if available
    dx_code = state.phase_3_diagnosis_code if hasattr(state, 'phase_3_diagnosis_code') and state.phase_3_diagnosis_code else "N/A"

    print(f"\n  Results:")
    print(f"    Final Status: {final_status}")
    print(f"    Patient Got Care: {'Yes' if payoffs['patient_got_care'] else 'No'}")
    print(f"    Diagnosis Code: {dx_code}")
    print(f"    Iterations: {iterations}")
    print(f"    Total Billed: ${payoffs['total_billed']:,.2f}")
    print(f"    Total Paid: ${payoffs['total_paid']:,.2f}")
    print(f"  Payoffs:")
    print(f"    Provider: ${payoffs['provider_payoff']:,.2f}")
    print(f"    Insurer: ${payoffs['insurer_payoff']:,.2f}")
    print(f"    Total (Social Welfare): ${payoffs['total_payoff']:,.2f}")

    return {
        "quadrant": quadrant_key,
        "name": config["name"],
        "final_status": final_status,
        "patient_got_care": payoffs["patient_got_care"],
        "dx_code": dx_code,
        "iterations": iterations,
        "total_billed": payoffs["total_billed"],
        "total_paid": payoffs["total_paid"],
        "provider_payoff": payoffs["provider_payoff"],
        "insurer_payoff": payoffs["insurer_payoff"],
        "total_payoff": payoffs["total_payoff"]
    }


def print_game_matrix(results):
    """print 2x2 game theory matrix"""
    print("\n")
    print("=" * 80)
    print("PRISONER'S DILEMMA PAYOFF MATRIX")
    print("=" * 80)
    print()
    print("                          INSURER")
    print("                    Cooperate    |    Defect")
    print("                   (Low Cost)    |   (High Cost)")
    print("-" * 60)

    cc = next((r for r in results if r["quadrant"] == "CC"), None)
    cd = next((r for r in results if r["quadrant"] == "CD"), None)
    dc = next((r for r in results if r["quadrant"] == "DC"), None)
    dd = next((r for r in results if r["quadrant"] == "DD"), None)

    # row 1: provider cooperates
    print("PROVIDER  Cooperate |")
    print("          (High     |", end="")
    if cc:
        print(f"  P: ${cc['provider_payoff']:>8,.0f}  |", end="")
    else:
        print("       N/A        |", end="")
    if cd:
        print(f"  P: ${cd['provider_payoff']:>8,.0f}")
    else:
        print("       N/A")

    print("           Care)    |", end="")
    if cc:
        print(f"  I: ${cc['insurer_payoff']:>8,.0f}  |", end="")
    else:
        print("       N/A        |", end="")
    if cd:
        print(f"  I: ${cd['insurer_payoff']:>8,.0f}")
    else:
        print("       N/A")

    print("                    |", end="")
    if cc:
        print(f"  [{cc['final_status'][:8]:^8}]  |", end="")
    else:
        print("       N/A        |", end="")
    if cd:
        print(f"  [{cd['final_status'][:8]:^8}]")
    else:
        print("       N/A")

    print("-" * 60)

    # row 2: provider defects
    print("          Defect    |")
    print("          (Low      |", end="")
    if dc:
        print(f"  P: ${dc['provider_payoff']:>8,.0f}  |", end="")
    else:
        print("       N/A        |", end="")
    if dd:
        print(f"  P: ${dd['provider_payoff']:>8,.0f}")
    else:
        print("       N/A")

    print("           Care)    |", end="")
    if dc:
        print(f"  I: ${dc['insurer_payoff']:>8,.0f}  |", end="")
    else:
        print("       N/A        |", end="")
    if dd:
        print(f"  I: ${dd['insurer_payoff']:>8,.0f}")
    else:
        print("       N/A")

    print("                    |", end="")
    if dc:
        print(f"  [{dc['final_status'][:8]:^8}]  |", end="")
    else:
        print("       N/A        |", end="")
    if dd:
        print(f"  [{dd['final_status'][:8]:^8}]")
    else:
        print("       N/A")

    print("-" * 60)
    print()
    print("Legend: P = Provider Payoff, I = Insurer Payoff")
    print()


def analyze_game_theory(results):
    """perform game theory analysis on results"""
    print("=" * 80)
    print("GAME THEORY ANALYSIS")
    print("=" * 80)
    print()

    cc = next((r for r in results if r["quadrant"] == "CC"), None)
    cd = next((r for r in results if r["quadrant"] == "CD"), None)
    dc = next((r for r in results if r["quadrant"] == "DC"), None)
    dd = next((r for r in results if r["quadrant"] == "DD"), None)

    if not all([cc, cd, dc, dd]):
        print("  Incomplete results - cannot perform analysis")
        return

    print("Dominant Strategy Analysis:")

    # provider: compare CC vs DC (insurer cooperates) and CD vs DD (insurer defects)
    provider_prefers_defect_vs_coop = dc["provider_payoff"] > cc["provider_payoff"]
    provider_prefers_defect_vs_defect = dd["provider_payoff"] > cd["provider_payoff"]

    if provider_prefers_defect_vs_coop and provider_prefers_defect_vs_defect:
        print("  - Provider has DOMINANT STRATEGY: Defect (Low Care)")
    elif not provider_prefers_defect_vs_coop and not provider_prefers_defect_vs_defect:
        print("  - Provider has DOMINANT STRATEGY: Cooperate (High Care)")
    else:
        print("  - Provider has NO dominant strategy")

    # insurer: compare CC vs CD (provider cooperates) and DC vs DD (provider defects)
    insurer_prefers_defect_vs_coop = cd["insurer_payoff"] > cc["insurer_payoff"]
    insurer_prefers_defect_vs_defect = dd["insurer_payoff"] > dc["insurer_payoff"]

    if insurer_prefers_defect_vs_coop and insurer_prefers_defect_vs_defect:
        print("  - Insurer has DOMINANT STRATEGY: Defect (High Cost Focus)")
    elif not insurer_prefers_defect_vs_coop and not insurer_prefers_defect_vs_defect:
        print("  - Insurer has DOMINANT STRATEGY: Cooperate (Low Cost Focus)")
    else:
        print("  - Insurer has NO dominant strategy")

    # social welfare comparison
    print()
    print("Social Welfare (Total Payoff):")
    welfare_ranked = sorted(results, key=lambda x: x["total_payoff"], reverse=True)
    for i, r in enumerate(welfare_ranked, 1):
        print(f"  {i}. {r['quadrant']} ({r['name']}): ${r['total_payoff']:,.2f}")

    # nash equilibrium check
    print()
    print("Nash Equilibrium Check:")
    cc_is_ne = cc["provider_payoff"] >= dc["provider_payoff"] and cc["insurer_payoff"] >= cd["insurer_payoff"]
    dd_is_ne = dd["provider_payoff"] >= cd["provider_payoff"] and dd["insurer_payoff"] >= dc["insurer_payoff"]

    if dd_is_ne and not cc_is_ne:
        print("  - DD (Defect/Defect) is Nash Equilibrium - PRISONER'S DILEMMA CONFIRMED")
        print("  - Both parties would be better off cooperating but individually incentivized to defect")
    elif cc_is_ne and not dd_is_ne:
        print("  - CC (Cooperate/Cooperate) is Nash Equilibrium - ALIGNED INCENTIVES")
    elif cc_is_ne and dd_is_ne:
        print("  - Multiple Nash Equilibria exist (CC and DD)")
    else:
        print("  - No pure strategy Nash Equilibrium found")


def save_results_csv(results, filepath):
    """save results to CSV"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    fieldnames = [
        "quadrant", "name", "final_status", "patient_got_care", "dx_code",
        "iterations", "total_billed", "total_paid",
        "provider_payoff", "insurer_payoff", "total_payoff"
    ]

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to: {filepath}")


def main():
    print("=" * 80)
    print("PRISONER'S DILEMMA SIMULATION")
    print("Healthcare Prior Authorization Game Theory Analysis")
    print("=" * 80)
    print()
    print("Case: COPD Respiratory Failure Grey Zone")
    print("  - Coding ambiguity: J96.01 ($7,800) vs J44.1 ($5,200)")
    print("  - Tests strategic behavior under different incentive structures")
    print()
    print("Game Structure:")
    print("  Provider: COOPERATE = High patient care weight")
    print("            DEFECT = Low patient care weight (profit-focused)")
    print("  Insurer:  COOPERATE = Low cost focus, lenient approvals")
    print("            DEFECT = High cost focus, aggressive denials")
    print()

    results = []

    for quadrant_key, config in GAME_CONFIGS.items():
        result = run_quadrant(quadrant_key, config)
        results.append(result)

    print_game_matrix(results)
    analyze_game_theory(results)

    csv_path = os.path.join(PROJECT_ROOT, "experiments", "results", "prisoners_dilemma_results.csv")
    save_results_csv(results, csv_path)

    print()
    print("=" * 80)
    print("SIMULATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
