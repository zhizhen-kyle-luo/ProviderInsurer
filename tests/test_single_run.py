"""
minimal test: run one case, see what happens
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.cases.grey_zones import COPD_RESPIRATORY_FAILURE_GREY

def main():
    print("=" * 60)
    print("SINGLE RUN TEST")
    print("=" * 60)

    # show config
    base = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "not set")
    copilot = os.getenv("AZURE_COPILOT_DEPLOYMENT_NAME", base)
    print(f"Base LLM: {base}")
    print(f"Copilot LLM: {copilot}")
    print()

    # run simulation with defaults
    sim = UtilizationReviewSimulation(
        provider_llm="azure",
        payor_llm="azure",
        provider_copilot_llm=None,  # use base
        payor_copilot_llm=None,     # use base
        enable_cache=True,
        master_seed=42
    )

    print("Running case...")
    state = sim.run_case(COPD_RESPIRATORY_FAILURE_GREY)

    # print results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    # PA status
    if state.authorization_request:
        print(f"PA Status: {state.authorization_request.authorization_status}")
        if state.authorization_request.denial_reason:
            print(f"Denial Reason: {state.authorization_request.denial_reason}")

    # level reached
    print(f"Final Level: {state.current_level}")
    print(f"Independent Review Reached: {state.independent_review_reached}")

    # friction
    if state.friction_metrics:
        print(f"Provider Actions: {state.friction_metrics.provider_actions}")
        print(f"Payor Actions: {state.friction_metrics.payor_actions}")
        print(f"Total Friction: {state.friction_metrics.total_friction}")
        print(f"Escalation Depth: {state.friction_metrics.escalation_depth}")

    # phase 3
    print(f"Claim Pended: {state.claim_pended}")
    print(f"Claim Rejected: {state.claim_rejected}")
    print(f"Appeal Filed: {state.appeal_filed}")

    # billing
    if state.phase_3_billed_amount:
        print(f"Billed Amount: ${state.phase_3_billed_amount:,.2f}")
    if state.financial_settlement:
        print(f"Paid Amount: ${state.financial_settlement.payer_payment:,.2f}")


if __name__ == "__main__":
    main()
