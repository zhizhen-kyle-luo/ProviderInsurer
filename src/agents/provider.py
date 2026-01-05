from typing import Dict, Any
from src.agents.game_agent import GameAgent


class ProviderAgent(GameAgent):
    """provider agent - wraps LLM for prompt invocation in game_runner"""

    def __init__(self, llm, config: Dict[str, Any] = None):
        super().__init__(llm, "Provider", config)
