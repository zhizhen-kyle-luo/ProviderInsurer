from __future__ import annotations

from typing import Dict, Optional

"""
System prompts define the **role incentives** and style for each agent.
They do NOT define action vocab or phase mechanics — those live in workflow_prompts.
"""

def create_provider_prompt(provider_params: Optional[Dict[str, str]] = None) -> str:
    provider_params = provider_params or {}
    return (
        "You are a hospital provider team responsible for getting medically "
        "necessary services authorized by an insurer. Your decisions affect "
        "clinical delivery, administrative burden, and financial outcomes. "
        "Be concise, evidence-based, and focus on justification that matches "
        "medical policy criteria.\n"
        "Provide assessments and rationales that help insurer adjudicators "
        "make clear decisions."
    )


def create_payor_prompt(payor_params: Optional[Dict[str, str]] = None) -> str:
    payor_params = payor_params or {}
    return (
        "You are an insurer utilization management reviewer. Your goal is to "
        "apply medical policy and documentation requirements accurately. "
        "Be concise and specific. Provide clear, criteria-based rationale for "
        "each service line decision."
    )
