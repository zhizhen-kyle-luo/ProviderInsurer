from __future__ import annotations

import json
from typing import Any, Dict

from .workflow_prompts import WORKFLOW_ACTION_DEFINITIONS

"""
Phase 3: Claim adjudication.
Similar action vocab to Phase 2, reuse the workflow definitions.
"""

def create_phase3_payor_system_prompt(payor_params: object = None) -> str:
    _ = payor_params
    return (
        "PHASE 3 PAYOR SYSTEM PROMPT\n"
        "You are adjudicating a clinical claim.\n"
        "Focus on match between billed services and documentation.\n"
        "Return only valid JSON matching the schema for claim response.\n"
        "Be concise and criteria-based.\n"
        f"{WORKFLOW_ACTION_DEFINITIONS}"
    )


def create_phase3_payor_user_prompt(
    state: object,
    claim_obj: Dict[str, Any],
    *,
    turn: int
) -> str:
    claim_text = json.dumps(claim_obj, ensure_ascii=False)
    return (
        f"PHASE 3 PAYOR USER PROMPT\n"
        f"Turn: {turn}\n\n"
        "CLAIM DATA:\n"
        f"{claim_text}\n\n"
        "TASK\n"
        "Adjudicate billed service lines.\n"
        "Return only valid JSON with line-level adjudication fields (allow/deny/mod docs).\n"
        "Use workflow tokens exactly as defined."
    )
