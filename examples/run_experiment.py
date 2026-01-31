"""
experiment runner for MASH simulation

2x2 game-theoretic experimental design:
- CP_CI: provider cooperate, insurer cooperate
- CP_DI: provider cooperate, insurer defect
- DP_CI: provider defect, insurer cooperate
- DP_DI: provider defect, insurer defect

strategy definitions:
- cooperate: good-faith, access-preserving; minimum clinically defensible
- defect: strict/aggressive; maximum plausibly defensible

usage:
  python examples/run_experiment.py --quick
  python examples/run_experiment.py --case infliximab_crohns_2015
  python examples/run_experiment.py --conditions CP_CI DP_DI
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv
from src.sim.run_full_simulation import run_full_simulation
from src.utils.audit_logger import AuditLogger
from src.utils.environment import Environment
from src.data.case_registry import get_case, list_cases
from src.data.policies.infliximab_policies import InfliximabCrohnsPolicies

# 2x2 game-theoretic experiment configs
CONFIGS = {
    'CP_CI': {'name': 'Cooperate-Cooperate', 'provider_strategy': 'cooperate', 'payor_strategy': 'cooperate'},
    'CP_DI': {'name': 'Cooperate-Defect', 'provider_strategy': 'cooperate', 'payor_strategy': 'defect'},
    'DP_CI': {'name': 'Defect-Cooperate', 'provider_strategy': 'defect', 'payor_strategy': 'cooperate'},
    'DP_DI': {'name': 'Defect-Defect', 'provider_strategy': 'defect', 'payor_strategy': 'defect'},
}

# infliximab case policies
PROVIDER_POLICY = InfliximabCrohnsPolicies.PROVIDER_GUIDELINES["aga_2021"]
PAYOR_POLICY = InfliximabCrohnsPolicies.PAYOR_POLICIES["cigna_ip0660_2026"] # "uhc_commercial_2025" | "cigna_ip0660_2026"


def run_single(case, case_id, condition, llms, output_dir):
    run_id = f"{case_id}_{condition}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    config = CONFIGS[condition]

    # prepare policy metadata
    provider_policy_meta = {
        "policy_id": PROVIDER_POLICY.get("policy_id"),
        "issuer": PROVIDER_POLICY.get("issuer"),
        "source": PROVIDER_POLICY.get("source"),
    }
    payor_policy_meta = {
        "policy_id": PAYOR_POLICY.get("policy_id"),
        "issuer": PAYOR_POLICY.get("issuer"),
        "source": PAYOR_POLICY.get("source"),
    }

    # prepare environment config metadata
    environment_config = {
        "allow_synthesis": True,
        "synthesis_model": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") if llms.get("synthesis") else None,
    }

    audit_logger = AuditLogger(
        case_id=case_id,
        run_id=run_id,
        provider_policy=provider_policy_meta,
        payor_policy=payor_policy_meta,
        environment_config=environment_config,
    )
    environment = Environment(synthesis_llm=llms["synthesis"], allow_synthesis=True)

    provider_params: Dict[str, Any] = {
        "policy": PROVIDER_POLICY,
        "strategy": config["provider_strategy"],
    }
    payor_params: Dict[str, Any] = {
        "policy": PAYOR_POLICY,
        "strategy": config["payor_strategy"],
    }

    print(f"  running: {run_id} ({config['name']})")
    print(f"    provider_strategy={config['provider_strategy']}, payor_strategy={config['payor_strategy']}")

    try:
        state = run_full_simulation(
            case=case,
            provider_llm=llms["main"],
            payor_llm=llms["main"],
            provider_params=provider_params,
            payor_params=payor_params,
            audit_logger=audit_logger,
            environment=environment,
        )

        metrics = state.friction_metrics.model_dump()

        # add policy and environment info to metrics
        metrics_with_context = {
            **metrics,
            "provider_policy": provider_policy_meta,
            "payor_policy": payor_policy_meta,
            "environment_config": environment_config,
        }

        audit_file = output_dir / f"{run_id}_audit.json"
        audit_logger.save_json(str(audit_file))

        metrics_file = output_dir / f"{run_id}_metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(metrics_with_context, f, indent=2)

        print("  completed")
        print(f"    phase2_turns={metrics['phase2_turns']} lines={metrics['total_lines_requested']} "
              f"approved={metrics['lines_approved_phase2']} denied={metrics['lines_denied_phase2']}")
        print(f"    provider_tokens={metrics['provider_review_tokens']} provider_edits={metrics['provider_edit_ops']} "
              f"insurer_tokens={metrics['insurer_review_tokens']} insurer_edits={metrics['insurer_edit_ops']}")
        print(f"    audit: {audit_file}")

        return {
            "run_id": run_id,
            "condition": condition,
            "config_name": config["name"],
            "success": True,
            "metrics": metrics,
            "provider_policy": provider_policy_meta,
            "payor_policy": payor_policy_meta,
            "environment_config": environment_config,
        }
    except Exception as e:
        print(f"  failed: {str(e)}")
        import traceback
        traceback.print_exc()
        audit_file = output_dir / f"{run_id}_audit_FAILED.json"
        audit_logger.save_json(str(audit_file))
        print(f"    audit: {audit_file}")
        return {"run_id": run_id, "condition": condition, "success": False, "error": str(e)}


def run_batch(case_ids=None, conditions=None, output_dir="outputs/experiments"):
    load_dotenv()

    # only infliximab case for now
    if case_ids is None:
        case_ids = ["infliximab_crohns_2015"]
    if conditions is None:
        conditions = list(CONFIGS.keys())

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    )
    llms = {"main": llm, "synthesis": llm}

    results = []

    all_case_ids = set(list_cases())
    for case_id in case_ids:
        if case_id not in all_case_ids:
            print(f"warning: {case_id} not found")
            continue

        case = get_case(case_id)
        print(f"\ncase: {case_id}")

        for cond in conditions:
            if cond not in CONFIGS:
                continue
            result = run_single(case, case_id, cond, llms, output_path)
            results.append(result)

    summary_file = output_path / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nbatch complete: {len(results)} runs")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--case", type=str, default="infliximab_crohns_2015")
    parser.add_argument("--conditions", nargs="+")
    parser.add_argument("--output", default="outputs/experiments")

    args = parser.parse_args()

    if args.quick:
        run_batch(case_ids=[args.case], conditions=["CP_CI"], output_dir="outputs/quick_test")
    else:
        run_batch(case_ids=[args.case], conditions=args.conditions, output_dir=args.output)
