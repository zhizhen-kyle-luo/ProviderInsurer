#!/usr/bin/env python3
"""verify oversight prompts are captured in audit log"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock
from src.utils.oversight import apply_oversight_edit
from src.utils.audit_logger import AuditLogger


def test_oversight_prompt_capture():
    """verify that apply_oversight_edit returns the prompt"""
    # setup mock llm
    llm = MagicMock()
    response = MagicMock()
    response.content = """{
        "needs_editing": false,
        "review_notes": "draft is acceptable",
        "revised_text": null,
        "changes_made": []
    }"""
    llm.invoke.return_value = response

    # call oversight edit
    draft = "Patient presents with symptoms."
    evidence = {"vitals": {"bp": "120/80"}}

    revised, metadata, prompt, llm_response = apply_oversight_edit(
        role="provider",
        oversight_level="low",
        draft_text=draft,
        evidence_packet=evidence,
        llm=llm
    )

    # verify prompt is returned
    assert isinstance(prompt, str), "prompt should be returned as string"
    assert len(prompt) > 0, "prompt should not be empty"
    assert "OVERSIGHT LEVEL: low" in prompt, "prompt should contain oversight level"
    assert "DRAFT TO REVIEW:" in prompt, "prompt should contain draft marker"
    assert draft in prompt, "prompt should contain the draft text"
    assert "AVAILABLE EVIDENCE:" in prompt, "prompt should contain evidence marker"

    # verify llm response is returned
    assert isinstance(llm_response, str), "llm_response should be returned as string"
    assert "needs_editing" in llm_response, "llm_response should contain JSON"

    print("oversight prompt capture test passed")


def test_audit_log_integration():
    """verify oversight prompts can be logged in audit log"""
    # setup
    audit_logger = AuditLogger(case_id="test_case")

    llm = MagicMock()
    response = MagicMock()
    response.content = """{
        "needs_editing": true,
        "review_notes": "minor edit",
        "revised_text": "Patient presents with mild symptoms.",
        "changes_made": ["added severity"]
    }"""
    llm.invoke.return_value = response

    # call oversight edit
    evidence = {"vitals": {"bp": "120/80"}, "icd10_codes": ["J44.1"]}
    revised, metadata, prompt, llm_response = apply_oversight_edit(
        role="provider",
        oversight_level="medium",
        draft_text="Patient presents with symptoms.",
        evidence_packet=evidence,
        llm=llm
    )

    # log to audit
    interaction_id = audit_logger.log_interaction(
        phase="phase_2_pa",
        agent="provider",
        action="oversight_edit",
        system_prompt="",
        user_prompt=prompt,
        llm_response=llm_response,
        parsed_output=metadata,
        metadata={"evidence_packet": evidence}
    )

    # verify audit log contains the data
    interactions = audit_logger.get_audit_log().interactions
    assert len(interactions) == 1, "should have one interaction logged"

    logged = interactions[0]
    assert logged.user_prompt == prompt, "should log the oversight prompt"
    assert logged.llm_response == llm_response, "should log the llm response"
    assert "evidence_packet" in logged.metadata, "should include evidence in metadata"
    assert logged.metadata["evidence_packet"] == evidence, "evidence should match"

    # verify prompt content
    assert "OVERSIGHT LEVEL: medium" in logged.user_prompt
    assert "AVAILABLE EVIDENCE:" in logged.user_prompt
    assert "bp" in logged.user_prompt or "J44.1" in logged.user_prompt

    print("audit log integration test passed")


if __name__ == "__main__":
    test_oversight_prompt_capture()
    test_audit_log_integration()
    print("\nall audit oversight prompt tests passed!")
