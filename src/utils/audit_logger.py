from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.models.audit import AuditLog, AuditEvent
from src.utils.audit_events import make_event, now_iso

class AuditLogger:
    def __init__(
        self,
        *,
        case_id: str,
        run_id: str,
        agent_configs: Optional[Dict[str, Any]] = None,
        provider_policy: Optional[Dict[str, Any]] = None,
        payor_policy: Optional[Dict[str, Any]] = None,
        environment_config: Optional[Dict[str, Any]] = None,
        context_mode: Optional[str] = None,
    ):
        self.audit_log = AuditLog(
            case_id=case_id,
            run_id=run_id,
            simulation_start=now_iso(),
            agent_configs=agent_configs or {},
            provider_policy=provider_policy,
            payor_policy=payor_policy,
            environment_config=environment_config,
            context_mode=context_mode,
        )

    def add(self, event: AuditEvent) -> None:
        self.audit_log.events.append(event)

    def log(
        self,
        *,
        phase: str,
        turn: int,
        kind: str,
        payload: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = None,
    ) -> None:
        self.add(make_event(phase=phase, turn=turn, kind=kind, payload=payload, actor=actor))

    def log_llm_interaction(
        self,
        *,
        phase: str,
        turn: int,
        actor: str,
        action: str,
        system_prompt: str,
        user_prompt: str,
        llm_response: str,
        parsed_output: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "action": action,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "llm_response": llm_response,
            "parsed_output": parsed_output or {},
            "meta": meta or {},
        }
        self.log(phase=phase, turn=turn, kind="llm_interaction", payload=payload, actor=actor)

    def finalize(self, summary: Optional[Dict[str, Any]] = None) -> None:
        self.audit_log.simulation_end = now_iso()
        if summary is not None:
            self.audit_log.summary = summary

    def to_dict(self) -> Dict[str, Any]:
        return self.audit_log.model_dump()

    def save_json(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
