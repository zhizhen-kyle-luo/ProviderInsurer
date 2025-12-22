"""quick test of pressure scenario configs"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from examples.run_batch import run_experiment, CONFIGS
from src.data.cases.cardiac.chest_pain_stress_test_case import CHEST_PAIN_CASE

# azure config from env (use keys expected by game_runner)
azure_config = {
    "endpoint": os.getenv("AZURE_ENDPOINT"),
    "key": os.getenv("AZURE_KEY"),
    "deployment_name": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
}

print(f"loaded azure config: endpoint={azure_config['endpoint']}, deployment={azure_config['deployment_name']}, key={'<set>' if azure_config['key'] else '<not set>'}")

# test HOSTILE_PAYOR config on chest pain case
print("\ntesting HOSTILE_PAYOR config on chest pain case...")
print("=" * 80)

result = run_experiment(
    case=CHEST_PAIN_CASE,
    config_name="HOSTILE_PAYOR",
    config=CONFIGS["HOSTILE_PAYOR"],
    azure_config=azure_config,
    results_dir="outputs/test_pressure"
)

print("\n" + "=" * 80)
print("RESULTS:")
print(f"  Word count: {result['word_count']}")
print(f"  Deceptive: {result['is_deceptive']}")
print(f"  Approval: {result['approval_status']}")
print(f"  Case: {result['case_id']}")
print(f"  Config: {result['config']}")
print("=" * 80)
print("\ncheck outputs/test_pressure/ for full audit logs")
