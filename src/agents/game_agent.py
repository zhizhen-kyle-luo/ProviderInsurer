from typing import Dict, Any
from src.models.schemas import EncounterState


class GameAgent:
    """base class for all game agents - wraps LLM for prompt invocation"""

    def __init__(self, llm, agent_name: str, config: Dict[str, Any] = None):
        self.llm = llm
        self.agent_name = agent_name
        self.config = config or {}
