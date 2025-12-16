"""run single case with all configs for quick testing"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from examples.run_batch import run_experiment, CONFIGS
from src.data.cases.cardiac.chest_pain_stress_test_case import CHEST_PAIN_CASE

# azure config
azure_config = {
    "endpoint": os.getenv("AZURE_ENDPOINT"),
    "key": os.getenv("AZURE_KEY"),
    "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
}

# create output directory
output_dir = "outputs/single_case_test"
os.makedirs(output_dir, exist_ok=True)

print("=" * 80)
print("SINGLE CASE TEST - ALL CONFIGS")
print("=" * 80)
print(f"Case: {CHEST_PAIN_CASE['case_id']}")
print(f"Configs: {len(CONFIGS)}")
print("=" * 80)

results = []

for config_name, provider_params in CONFIGS.items():
    print(f"\n{config_name}...", end=" ", flush=True)
    
    result = run_experiment(
        case=CHEST_PAIN_CASE,
        config_name=config_name,
        provider_params=provider_params,
        azure_config=azure_config,
        results_dir=output_dir
    )
    
    print(f"Done (deceptive={result['is_deceptive']}, words={result['word_count']})")
    results.append(result)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"{'Config':<20} {'Words':>8} {'Deceptive':>12} {'Approval':>12}")
print("-" * 80)

for r in results:
    print(f"{r['config']:<20} {r['word_count']:>8} {str(r['is_deceptive']):>12} {r['approval_status']:>12}")

print("=" * 80)
print(f"\ncheck {output_dir}/ for full audit logs")
