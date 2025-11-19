from typing import Any, List, Dict, Optional
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from src.utils.worm_cache import WORMCache


class CachedLLM:
    """wrapper around langchain llm that uses worm cache for deterministic responses"""

    def __init__(self, llm: Any, cache: WORMCache, agent_name: str = "unknown"):
        self.llm = llm
        self.cache = cache
        self.agent_name = agent_name

    def invoke(self, messages: List[BaseMessage], **kwargs) -> AIMessage:
        """invoke llm with caching. maintains langchain message interface"""
        system_prompt, user_prompt = self._extract_prompts(messages)

        metadata = {
            'agent': self.agent_name,
            'model': getattr(self.llm, 'model_name', 'unknown')
        }

        def compute_fn():
            response = self.llm.invoke(messages, **kwargs)
            if response and hasattr(response, 'content'):
                return response.content if response.content else ""
            return ""

        content, is_cache_hit = self.cache.get_or_compute(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            compute_fn=compute_fn,
            metadata=metadata
        )

        return AIMessage(content=content, additional_kwargs={
            'cache_hit': is_cache_hit,
            'agent': self.agent_name
        })

    def _extract_prompts(self, messages: List[BaseMessage]) -> tuple[str, str]:
        """extract system and user prompts from message list"""
        system_prompt = ""
        user_prompt = ""

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_prompt += msg.content + "\n"
            elif isinstance(msg, HumanMessage):
                user_prompt += msg.content + "\n"

        return system_prompt.strip(), user_prompt.strip()

    def __getattr__(self, name: str):
        """delegate unknown attributes to underlying llm"""
        return getattr(self.llm, name)
