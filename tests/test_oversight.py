"""
tests for oversight functionality and metrics tracking
"""
import pytest
from unittest.mock import MagicMock

from src.utils.oversight import apply_oversight_edit, _compute_diff_metrics
from src.utils.prompts import OVERSIGHT_GUIDANCE


class TestDiffMetrics:
    """test diff computation"""

    def test_identical_text(self):
        """identical texts should have 0 changes"""
        text = "This is a test sentence with some words."
        metrics = _compute_diff_metrics(text, text)
        assert metrics["changed_word_count"] == 0
        assert metrics["diff_ratio"] < 0.01  # approximately 0

    def test_word_replacement(self):
        """single word replacement should show 1 changed word"""
        original = "The quick brown fox jumps"
        revised = "The quick red fox jumps"
        metrics = _compute_diff_metrics(original, revised)
        assert metrics["changed_word_count"] >= 1

    def test_word_addition(self):
        """adding words should increase changed count"""
        original = "The fox jumps"
        revised = "The quick brown fox jumps high"
        metrics = _compute_diff_metrics(original, revised)
        assert metrics["changed_word_count"] >= 3


class TestOversightGuidance:
    """test oversight guidance definitions"""

    def test_guidance_defined(self):
        """ensure guidance is defined for all levels"""
        assert "low" in OVERSIGHT_GUIDANCE
        assert "medium" in OVERSIGHT_GUIDANCE
        assert "high" in OVERSIGHT_GUIDANCE

    def test_guidance_keys(self):
        """ensure each guidance has required keys"""
        for level in ["low", "medium", "high"]:
            guidance = OVERSIGHT_GUIDANCE[level]
            assert "instruction" in guidance
            assert "typical_behavior" in guidance


class TestApplyOversightEdit:
    """test oversight edit function"""

    @pytest.fixture
    def mock_llm_with_edits(self):
        """create a mock LLM that returns edited text"""
        llm = MagicMock()
        response = MagicMock()
        response.content = """{
            "needs_editing": true,
            "review_notes": "fixed grammar",
            "revised_text": "The patient presents with mild symptoms.",
            "changes_made": ["minor grammar fix"]
        }"""
        llm.invoke.return_value = response
        return llm

    @pytest.fixture
    def mock_llm_no_edits(self):
        """create a mock LLM that approves as-is"""
        llm = MagicMock()
        response = MagicMock()
        response.content = """{
            "needs_editing": false,
            "review_notes": "draft is acceptable",
            "revised_text": null,
            "changes_made": []
        }"""
        llm.invoke.return_value = response
        return llm

    @pytest.fixture
    def sample_evidence(self):
        return {
            "vitals": {"bp": "120/80", "hr": 72},
            "labs": {"wbc": 8.5},
            "icd10_codes": ["J44.1"]
        }

    def test_with_edits(self, mock_llm_with_edits, sample_evidence):
        """oversight with edits should track changes"""
        draft = "The patient presents with symptoms."
        revised, metadata, prompt, llm_response = apply_oversight_edit(
            role="provider",
            oversight_level="medium",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm_with_edits
        )

        assert isinstance(revised, str)
        assert isinstance(prompt, str)
        assert isinstance(llm_response, str)
        assert metadata["oversight_level"] == "medium"
        assert metadata["needs_editing"] == True
        assert metadata["tokens_changed"] > 0
        assert "oversight_llm_tokens" in metadata

    def test_approve_as_is(self, mock_llm_no_edits, sample_evidence):
        """oversight can approve draft without changes"""
        draft = "The patient presents with symptoms."
        revised, metadata, prompt, llm_response = apply_oversight_edit(
            role="provider",
            oversight_level="low",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm_no_edits
        )

        assert revised == draft  # unchanged
        assert metadata["needs_editing"] == False
        assert metadata["tokens_changed"] == 0
        assert len(metadata["changes_made"]) == 0

    def test_metadata_tracking(self, mock_llm_with_edits, sample_evidence):
        """should track oversight metrics"""
        draft = "The patient presents with symptoms."
        _, metadata, _, _ = apply_oversight_edit(
            role="provider",
            oversight_level="high",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm_with_edits
        )

        # check new metrics
        assert "tokens_changed" in metadata
        assert "oversight_llm_tokens" in metadata
        assert "needs_editing" in metadata
        assert "review_notes" in metadata

        # old budget fields should not exist
        assert "max_tokens_changed" not in metadata
        assert "max_edit_passes" not in metadata
        assert "budget_enforced" not in metadata

    def test_parse_error_returns_original(self, sample_evidence):
        """if LLM returns invalid JSON, should return original text"""
        llm = MagicMock()
        llm.invoke.return_value.content = "This is not valid JSON at all"

        draft = "Original text should be preserved."

        final_text, metadata, _, _ = apply_oversight_edit(
            role="provider",
            oversight_level="medium",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=llm
        )

        assert final_text == draft
        assert metadata.get("parse_error") is True
