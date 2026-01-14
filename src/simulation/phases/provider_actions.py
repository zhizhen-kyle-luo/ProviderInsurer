"""provider action decision logic after payor decisions"""
from typing import Dict, Any, TYPE_CHECKING
from langchain_core.messages import HumanMessage

from src.models import EncounterState
from src.utils.prompts import (
    create_provider_prompt,
    create_treatment_decision_after_phase2_denial_prompt,
    PROVIDER_ACTIONS_GUIDE,
    PROVIDER_RESPONSE_MATRIX,
    VALID_PROVIDER_ACTIONS,
    VALID_TREATMENT_DECISIONS,
)
from src.utils.json_parsing import extract_json_from_text

if TYPE_CHECKING:
    from src.simulation.game_runner import UtilizationReviewSimulation


def get_provider_action_after_payor_decision(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    payor_decision: Dict[str, Any],
    request_type: str,
    phase: str,
    current_level: int
) -> str:
    """
    ask provider to choose action (CONTINUE/APPEAL/ABANDON) after payor decision.

    returns: "continue", "appeal", or "abandon"
    """
    if "action" not in payor_decision:
        raise ValueError("payor_decision missing required field 'action'")
    payor_action = payor_decision["action"]
    decision_reason = payor_decision.get("decision_reason", "")

    # build prompt explaining situation and asking for action
    prompt = f"""PROVIDER ACTION DECISION

You just received a payor decision. You must choose your next action.

PAYOR DECISION: {payor_action}
Request Type: {request_type}
Current Review Level: {current_level}
{f"Denial/Pend Reason: {decision_reason}" if decision_reason else ""}

{PROVIDER_RESPONSE_MATRIX}

{PROVIDER_ACTIONS_GUIDE}

IMPORTANT: Based on the payor decision and request type above, only certain actions are valid (see matrix).

TASK: Choose your action and explain your reasoning.

RESPONSE FORMAT (JSON):
{{
    "provider_action": "continue" or "appeal" or "abandon",
    "reasoning": "<brief explanation of why you chose this action>"
}}

Return ONLY valid JSON."""

    provider_system_prompt = create_provider_prompt(sim.provider_params)
    full_prompt = f"{provider_system_prompt}\n\n{prompt}"
    messages = [HumanMessage(content=full_prompt)]

    # use provider base LLM (this is a strategic decision, not a draft)
    response = sim.provider_base_llm.invoke(messages)
    response_text = response.content.strip()

    try:
        action_data = extract_json_from_text(response_text)

        # validate provider_action field exists
        if "provider_action" not in action_data:
            raise ValueError(
                f"provider action response missing required field 'provider_action'. "
                f"must be one of: {VALID_PROVIDER_ACTIONS}"
            )

        provider_action = action_data["provider_action"]
        reasoning = action_data.get("reasoning", "")

        # validate action is in allowed set
        if provider_action not in VALID_PROVIDER_ACTIONS:
            raise ValueError(
                f"invalid provider_action '{provider_action}'. "
                f"must be one of: {VALID_PROVIDER_ACTIONS}"
            )

        # log the action decision
        sim.audit_logger.log_interaction(
            phase=phase,
            agent="provider",
            action="action_decision",
            system_prompt=provider_system_prompt,
            user_prompt=prompt,
            llm_response=response_text,
            parsed_output={"provider_action": provider_action, "reasoning": reasoning},
            metadata={
                "payor_decision": payor_action,
                "request_type": request_type,
                "current_level": current_level
            }
        )

        return provider_action

    except ValueError as e:
        # validation error - re-raise (no defaults)
        raise
    except Exception as e:
        # JSON parsing failed - raise error to surface the bug
        raise ValueError(
            f"failed to parse provider action decision: {e}\n"
            f"Response: {response_text}"
        )


def provider_treatment_decision_after_phase2_denial(
    sim: "UtilizationReviewSimulation",
    state: EncounterState,
    case: Dict[str, Any]
) -> str:
    """
    After Phase 2 denial, provider decides whether to treat patient anyway.

    Returns: "treat_anyway" or "no_treat"

    This captures the financial-legal tension documented in utilization review literature:
    - Treat anyway = risk nonpayment (OOP/charity/hope for retro approval)
    - No treat = risk medical abandonment (legal liability)

    This is a conditional branch after ABANDON action, not a new action in action space.
    """
    # summarize denial reasons from all service lines
    decision_reason = "Phase 2 exhausted without approval"
    if state.service_lines:
        statuses = [line.authorization_status for line in state.service_lines if line.authorization_status]
        if statuses:
            decision_reason = f"Phase 2 {', '.join(set(statuses))}"

    prompt = create_treatment_decision_after_phase2_denial_prompt(
        state=state,
        decision_reason=decision_reason,
    )

    response = sim.provider.llm.invoke([HumanMessage(content=prompt)])
    response_text = response.content.strip()

    # parse decision
    try:
        decision_data = extract_json_from_text(response_text)

        # validate decision field exists
        if "decision" not in decision_data:
            raise ValueError(
                f"treatment decision response missing required field 'decision'. "
                f"must be one of: {VALID_TREATMENT_DECISIONS}"
            )

        decision = decision_data["decision"]

        # validate decision is valid
        if decision not in VALID_TREATMENT_DECISIONS:
            raise ValueError(
                f"invalid treatment decision '{decision}'. "
                f"must be one of: {VALID_TREATMENT_DECISIONS}"
            )

        return decision

    except ValueError as e:
        # validation error - re-raise (no defaults)
        raise
    except Exception as e:
        # JSON parsing failed - raise error to surface the bug
        raise ValueError(f"failed to parse provider treatment decision after Phase 2 denial: {e}\nResponse: {response_text}")