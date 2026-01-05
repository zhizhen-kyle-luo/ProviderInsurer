"""
Run hypothesis testing experiment with 5 configurations (A, B, C, C', D)

usage:
  python examples/run_experiment.py                # Run all runs
  python examples/run_experiment.py A              # Run specific run
  python examples/run_experiment.py A B C          # Run multiple runs
  python examples/run_experiment.py infliximab     # Use infliximab case (default: infliximab_crohns_2015)

This implements the 5-run hypothesis design from EXPERIMENT_CONFIGS.md:
- Run A: Baseline (both weak copilot, high effort)
- Run B: Asymmetric Offense (insurer strong/low, provider weak/high)
- Run C: Arms Race High Effort (both strong copilot, high effort)
- Run C': Arms Race Low Effort (both strong copilot, low effort)
- Run D: Governance (both strong copilot, both high effort)
"""
import sys
import os
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from src.simulation.game_runner import UtilizationReviewSimulation
from src.data.case_registry import get_case
from src.data.case_converter import convert_case_to_models
from src.utils.mermaid_audit_generator import MermaidAuditGenerator


# ============================================================================
# EXPERIMENT PARAMETER DEFINITIONS (from EXPERIMENT_CONFIGS.md)
# ============================================================================

# Behavioral parameters for effort levels
HIGH_EFFORT_PARAMS = {
    'oversight_intensity': 'high',  # thorough review, extensive editing allowed
    'reasoning_depth': 'thorough',
    'documentation_quality': 'comprehensive'
}

LOW_EFFORT_PARAMS = {
    'oversight_intensity': 'low',   # minimal review, accept with minor tweaks
    'reasoning_depth': 'minimal',
    'documentation_quality': 'brief'
}

EXPERIMENT_CONFIGS = {
    'A': {
        'name': 'Baseline',
        'description': 'Both agents use weak copilots, high effort',
        'provider_llm': 'azure',
        'payor_llm': 'azure',
        'provider_copilot_llm': 'azure',    # weak copilot
        'payor_copilot_llm': 'azure',       # weak copilot
        'provider_params': HIGH_EFFORT_PARAMS,
        'payor_params': HIGH_EFFORT_PARAMS,
        'hypothesis': 'H0: Baseline - both agents strong, high effort'
    },
    'B': {
        'name': 'Asymmetric Offense',
        'description': 'Insurer offense: strong copilot & low effort | Provider: weak copilot & high effort',
        'provider_llm': 'azure',
        'payor_llm': 'azure',
        'provider_copilot_llm': 'azure',    # weak copilot
        'payor_copilot_llm': None,          # strong copilot (use base)
        'provider_params': HIGH_EFFORT_PARAMS,
        'payor_params': LOW_EFFORT_PARAMS,
        'hypothesis': 'H1: If insurer has strong copilot + low effort, denials/pends increase'
    },
    'C': {
        'name': 'Arms Race High Effort',
        'description': 'Both agents use strong copilots, high effort',
        'provider_llm': 'azure',
        'payor_llm': 'azure',
        'provider_copilot_llm': None,       # strong copilot (use base)
        'payor_copilot_llm': None,          # strong copilot (use base)
        'provider_params': HIGH_EFFORT_PARAMS,
        'payor_params': HIGH_EFFORT_PARAMS,
        'hypothesis': 'H2: Arms race - approval recovers but admin volume explodes'
    },
    "C'": {
        'name': 'Arms Race Low Effort',
        'description': 'Both agents use strong copilots, low effort',
        'provider_llm': 'azure',
        'payor_llm': 'azure',
        'provider_copilot_llm': None,       # strong copilot (use base)
        'payor_copilot_llm': None,          # strong copilot (use base)
        'provider_params': LOW_EFFORT_PARAMS,
        'payor_params': LOW_EFFORT_PARAMS,
        'hypothesis': 'H3: AI does not save you if you do not put in effort'
    },
    'D': {
        'name': 'Governance',
        'description': 'Both agents use strong copilots, both high effort (governance backstop)',
        'provider_llm': 'azure',
        'payor_llm': 'azure',
        'provider_copilot_llm': None,       # strong copilot (use base)
        'payor_copilot_llm': None,          # strong copilot (use base)
        'provider_params': HIGH_EFFORT_PARAMS,
        'payor_params': HIGH_EFFORT_PARAMS,
        'hypothesis': 'Optional: Governance lever - high effort from both sides'
    }
}


def print_config_header(run_id, config):
    """print configuration header"""
    print("\n" + "=" * 80)
    print(f"RUN {run_id}: {config['name'].upper()}")
    print("=" * 80)
    print(f"Description: {config['description']}")
    print(f"Hypothesis: {config['hypothesis']}")
    print(f"Provider Copilot: {'Strong (base)' if config['provider_copilot_llm'] is None else 'Weak (azure)'}")
    print(f"Provider Effort: {config['provider_params']['oversight_intensity'].upper()}")
    print(f"Payor Copilot: {'Strong (base)' if config['payor_copilot_llm'] is None else 'Weak (azure)'}")
    print(f"Payor Effort: {config['payor_params']['oversight_intensity'].upper()}")
    print()


def print_results(result):
    """print simulation results"""
    print("\n" + "-" * 80)
    print("RESULTS")
    print("-" * 80)

    # Phase 2: Prior Authorization
    print("\nPHASE 2: PRIOR AUTHORIZATION")
    if result.authorization_request:
        print(f"  Service: {result.authorization_request.service_name}")
        print(f"  Type: {result.authorization_request.request_type}")
        status = result.authorization_request.authorization_status
        print(f"  PA Status: {status.upper()}")
        if result.authorization_request.denial_reason:
            print(f"  Denial Reason: {result.authorization_request.denial_reason[:100]}...")

    # Phase 3: Claims Adjudication
    print("\nPHASE 3: CLAIMS ADJUDICATION")
    if result.authorization_request and result.authorization_request.authorization_status == "approved":
        print("  Claim Submitted: YES")
        if result.claim_pended:
            print("  Claim Status: PENDED")
        elif result.claim_rejected:
            print("  Claim Status: REJECTED")
        else:
            print("  Claim Status: APPROVED")

        if result.appeal_filed:
            print(f"  Appeal Filed: YES")
            print(f"  Appeal Successful: {result.appeal_successful}")
    else:
        print("  Claim Submitted: NO (PA denied)")

    # Metrics
    print("\nMETRICS")
    if result.friction_metrics:
        fm = result.friction_metrics
        print(f"  Provider Actions: {fm.provider_actions}")
        print(f"  Payor Actions: {fm.payor_actions}")
        print(f"  Total Iterations: {fm.provider_actions + fm.payor_actions}")
        print(f"  Probing Tests: {fm.probing_tests_count}")
        print(f"  Escalation Depth: {fm.escalation_depth}")

    # Financial
    print("\nFINANCIAL SETTLEMENT")
    if result.financial_settlement:
        fin = result.financial_settlement
        print(f"  Total Billed: ${fin.total_billed_charges:,.2f}")
        print(f"  Payer Payment: ${fin.payer_payment:,.2f}")
        print(f"  Patient Responsibility: ${fin.patient_responsibility:,.2f}")


def collect_metrics(result):
    """collect key metrics from result"""
    return {
        'case_id': result.admission.case_id if hasattr(result.admission, 'case_id') else 'unknown',
        'pa_status': result.authorization_request.authorization_status if result.authorization_request else 'denied',
        'pa_level_reached': result.current_level,
        'claim_status': 'N/A',  # Not tracked in Phase 3 result yet
        'claim_pended': result.claim_pended,
        'claim_rejected': result.claim_rejected,
        'appeal_filed': result.appeal_filed,
        'appeal_successful': result.appeal_successful,
        'total_iterations': (result.friction_metrics.provider_actions + result.friction_metrics.payor_actions) if result.friction_metrics else 0,
        'provider_actions': result.friction_metrics.provider_actions if result.friction_metrics else 0,
        'payor_actions': result.friction_metrics.payor_actions if result.friction_metrics else 0,
        'probing_tests': result.friction_metrics.probing_tests_count if result.friction_metrics else 0,
        'escalation_depth': result.friction_metrics.escalation_depth if result.friction_metrics else 0,
        'total_billed': result.financial_settlement.total_billed_charges if result.financial_settlement else 0.0,
        'payer_payment': result.financial_settlement.payer_payment if result.financial_settlement else 0.0
    }


def run_experiment_config(run_id, config, case_id, output_dir="experiment_results"):
    """run a single experiment configuration"""
    print_config_header(run_id, config)

    try:
        # Load case
        case = get_case(case_id)
        case = convert_case_to_models(case)

        # Create simulation with config parameters
        sim = UtilizationReviewSimulation(
            provider_llm=config['provider_llm'],
            payor_llm=config['payor_llm'],
            provider_copilot_llm=config['provider_copilot_llm'],
            payor_copilot_llm=config['payor_copilot_llm'],
            provider_params=config['provider_params'],
            payor_params=config['payor_params'],
            enable_cache=True,
            master_seed=42  # deterministic for reproducibility
        )

        # Run simulation
        result = sim.run_case(case)

        # Print results
        print_results(result)

        # Save outputs
        os.makedirs(output_dir, exist_ok=True)

        # Save audit log
        if result.audit_log:
            audit_path = f"{output_dir}/run_{run_id}_audit_log.md"
            result.audit_log.save_to_markdown(audit_path)
            print(f"\nAudit Log: {audit_path}")

        # Collect metrics
        metrics = collect_metrics(result)
        metrics['run_id'] = run_id
        metrics['config'] = {
            'name': config['name'],
            'provider_copilot': config['provider_copilot_llm'],
            'provider_effort': config['provider_params']['oversight_intensity'],
            'payor_copilot': config['payor_copilot_llm'],
            'payor_effort': config['payor_params']['oversight_intensity']
        }

        return metrics

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Run hypothesis testing experiment with 5 configurations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python examples/run_experiment.py                # Run all runs (A, B, C, C', D)
  python examples/run_experiment.py A B C          # Run specific runs
  python examples/run_experiment.py A case_id      # Run A with specific case
        """
    )
    parser.add_argument('items', nargs='*', help='runs (A/B/C/C\'/D) or case ID')
    parser.add_argument('--output-dir', default='experiment_results', help='output directory')
    args = parser.parse_args()

    # Parse arguments
    runs_to_execute = []
    case_id = 'infliximab_crohns_2015'  # default case

    if args.items:
        for item in args.items:
            if item in EXPERIMENT_CONFIGS:
                runs_to_execute.append(item)
            else:
                # Treat as case ID
                case_id = item

    # Default to all runs if none specified
    if not runs_to_execute:
        runs_to_execute = ['A', 'B', 'C', "C'", 'D']

    print("=" * 80)
    print("HYPOTHESIS TESTING EXPERIMENT")
    print("=" * 80)
    print(f"\nExecution Plan:")
    print(f"  Case: {case_id}")
    print(f"  Runs: {', '.join(runs_to_execute)}")
    print(f"  Output Dir: {args.output_dir}")

    # Run experiment configurations
    results = []
    for run_id in runs_to_execute:
        if run_id not in EXPERIMENT_CONFIGS:
            print(f"\nERROR: Unknown run '{run_id}'")
            continue

        config = EXPERIMENT_CONFIGS[run_id]
        metrics = run_experiment_config(run_id, config, case_id, args.output_dir)
        if metrics:
            results.append(metrics)

    # Summary
    print("\n" + "=" * 80)
    print("EXPERIMENT SUMMARY")
    print("=" * 80)

    if results:
        print(f"\nCompleted {len(results)}/{len(runs_to_execute)} runs\n")
        print("RUN | CONFIG | PA | ITERATIONS | TESTS | CLAIM | APPEAL")
        print("-" * 70)
        for r in results:
            pa = r['pa_status'][:4].upper()
            claim = 'PEND' if r['claim_pended'] else ('DENY' if r['claim_rejected'] else 'APP')
            appeal = 'YES' if r['appeal_filed'] else 'NO'
            print(f"{r['run_id']:3} | {r['config']['name']:20} | {pa:4} | {r['total_iterations']:3} | {r['probing_tests']:2} | {claim:4} | {appeal:3}")

        # Save summary
        summary_path = f"{args.output_dir}/experiment_summary.json"
        with open(summary_path, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'case_id': case_id,
                'runs': results
            }, f, indent=2)
        print(f"\nSummary: {summary_path}")
    else:
        print("No results to summarize")


if __name__ == "__main__":
    main()
