"""
Protocol / interface for adapter
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

Delta = Dict[str, Any]

class SimAdapter:
    phase_name: str

    def build_submission(self, state) -> Dict[str, Any]:
        raise NotImplementedError

    def build_response(self, state, submission: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def apply_response(self, state, response: Dict[str, Any]) -> List[Delta]:
        raise NotImplementedError

    def choose_provider_action(self, state, submission: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def apply_provider_action(self, state, provider_action: Dict[str, Any]) -> Tuple[List[Delta], bool, Optional[str]]:
        raise NotImplementedError

    def is_terminal(self, state) -> bool:
        return False

    def append_submission(self, state, submission: Dict[str, Any]) -> None:
        raise NotImplementedError

    def append_response(self, state, response: Dict[str, Any]) -> None:
        raise NotImplementedError
