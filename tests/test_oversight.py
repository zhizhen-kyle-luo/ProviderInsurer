"""
tests for oversight budget enforcement and action space constraints
"""
import pytest
from unittest.mock import MagicMock

from src.utils.oversight import apply_oversight_edit, _compute_diff_metrics
from src.utils.prompts import (
    OVERSIGHT_BUDGETS as PROMPT_BUDGETS,
    PROVIDER_ACTIONS,
    PAYOR_ACTIONS,
    MAX_REQUEST_INFO_PER_LEVEL,
    WORKFLOW_LEVELS,
    create_provider_claim_appeal_decision_prompt,
    create_provider_pend_response_prompt,
    create_payor_claim_resubmission_review_prompt
)


class TestDiffMetrics:
    """test diff computation"""

    def test_identical_text(self):
        """identical texts should have 0 changes"""
        text = "This is a test sentence with some words."
        metrics = _compute_diff_metrics(text, text)
        assert metrics["changed_word_count"] == 0
        assert metrics["diff_ratio"] == 0.0

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

    def test_word_deletion(self):
        """deleting words should increase changed count"""
        original = "The quick brown fox jumps over the lazy dog"
        revised = "The fox jumps"
        metrics = _compute_diff_metrics(original, revised)
        assert metrics["changed_word_count"] >= 6


class TestOversightBudgets:
    """test budget definitions"""

    def test_budgets_defined_in_prompts(self):
        """ensure budgets are defined in prompts module"""
        assert "low" in PROMPT_BUDGETS
        assert "medium" in PROMPT_BUDGETS
        assert "high" in PROMPT_BUDGETS

    def test_budget_keys(self):
        """ensure each budget has required keys"""
        for level in ["low", "medium", "high"]:
            budget = PROMPT_BUDGETS[level]
            assert "max_edit_passes" in budget
            assert "max_tokens_changed" in budget
            assert "max_evidence_checks" in budget

    def test_budget_ordering(self):
        """low < medium < high for tokens changed"""
        low = PROMPT_BUDGETS["low"]["max_tokens_changed"]
        medium = PROMPT_BUDGETS["medium"]["max_tokens_changed"]
        high = PROMPT_BUDGETS["high"]["max_tokens_changed"]
        assert low < medium < high


class TestApplyOversightEdit:
    """test oversight edit function"""

    @pytest.fixture
    def mock_llm(self):
        """create a mock LLM that returns minimal changes"""
        llm = MagicMock()
        response = MagicMock()
        response.content = """{
            "revised_text": "The patient presents with mild symptoms.",
            "edits_made": ["minor grammar fix"],
            "tokens_changed_estimate": 2
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

    def test_low_oversight_minimal_changes(self, mock_llm, sample_evidence):
        """low oversight should not substantially change text"""
        draft = "The patient presents with symptoms."

        final_text, metadata = apply_oversight_edit(
            role="provider",
            oversight_level="low",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm,
            rng_seed=42
        )

        assert metadata["oversight_level"] == "low"
        assert metadata["max_tokens_changed"] == 50
        # should call LLM once
        assert mock_llm.invoke.called

    def test_high_oversight_allows_more_changes(self, mock_llm, sample_evidence):
        """high oversight should have larger budget"""
        mock_llm.invoke.return_value.content = """{
            "revised_text": "The patient presents with severe respiratory symptoms requiring immediate attention and inpatient admission for monitoring.",
            "edits_made": ["expanded clinical details", "added severity", "added care level"],
            "tokens_changed_estimate": 50,
            "evidence_checks_performed": 5
        }"""

        draft = "The patient presents with symptoms."

        final_text, metadata = apply_oversight_edit(
            role="provider",
            oversight_level="high",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm,
            rng_seed=42
        )

        assert metadata["oversight_level"] == "high"
        assert metadata["max_tokens_changed"] == 600
        assert metadata["max_edit_passes"] == 2

    def test_budget_enforcement(self, mock_llm, sample_evidence):
        """if LLM returns too many changes, should revert"""
        # LLM claims to change lots of text
        mock_llm.invoke.return_value.content = """{
            "revised_text": "Completely different text that is nothing like the original at all and has been entirely rewritten from scratch with new content.",
            "edits_made": ["complete rewrite"],
            "tokens_changed_estimate": 500
        }"""

        draft = "Original short text."

        final_text, metadata = apply_oversight_edit(
            role="provider",
            oversight_level="low",  # low budget = 50 tokens
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm,
            rng_seed=42
        )

        # with low oversight, the massive change should be reverted
        # budget is 50 tokens, but changed ~20 words > 50*1.5 = 75
        assert "budget_enforced" in metadata

    def test_parse_error_returns_original(self, mock_llm, sample_evidence):
        """if LLM returns invalid JSON, should return original text"""
        mock_llm.invoke.return_value.content = "This is not valid JSON at all"

        draft = "Original text should be preserved."

        final_text, metadata = apply_oversight_edit(
            role="provider",
            oversight_level="medium",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm,
            rng_seed=42
        )

        assert final_text == draft
        assert metadata.get("parse_error") is True

    def test_payor_role(self, mock_llm, sample_evidence):
        """test payor role works the same"""
        mock_llm.invoke.return_value.content = """{
            "revised_text": "Authorization denied due to insufficient documentation.",
            "edits_made": ["clarified denial"],
            "tokens_changed_estimate": 3
        }"""

        draft = "Denied."

        final_text, metadata = apply_oversight_edit(
            role="payor",
            oversight_level="medium",
            draft_text=draft,
            evidence_packet=sample_evidence,
            llm=mock_llm,
            rng_seed=42
        )

        assert metadata["oversight_level"] == "medium"
        mock_llm.invoke.assert_called_once()


class TestOversightMetadataFields:
    """test that metadata contains all required fields"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        response = MagicMock()
        response.content = """{
            "revised_text": "Test text.",
            "edits_made": ["test edit"],
            "tokens_changed_estimate": 5,
            "evidence_checks_performed": 2,
            "removed_unsupported_claims": ["claim1"]
        }"""
        llm.invoke.return_value = response
        return llm

    def test_metadata_fields(self, mock_llm):
        """ensure all required metadata fields are present"""
        final_text, metadata = apply_oversight_edit(
            role="provider",
            oversight_level="medium",
            draft_text="Original.",
            evidence_packet={},
            llm=mock_llm,
            rng_seed=42
        )

        required_fields = [
            "oversight_level",
            "max_edit_passes",
            "max_tokens_changed",
            "changed_word_count",
            "changed_char_count",
            "diff_ratio",
            "edits_made_count",
            "evidence_checks_count",
            "removed_unsupported_claims_count"
        ]

        for field in required_fields:
            assert field in metadata, f"Missing field: {field}"


class TestActionSpaceConstraints:
    """test discrete action space definitions"""

    def test_provider_actions_defined(self):
        """provider has exactly 3 discrete actions"""
        assert len(PROVIDER_ACTIONS) == 3
        assert "CONTINUE" in PROVIDER_ACTIONS
        assert "APPEAL" in PROVIDER_ACTIONS
        assert "ABANDON" in PROVIDER_ACTIONS

    def test_payor_actions_defined(self):
        """payor has exactly 3 discrete actions"""
        assert len(PAYOR_ACTIONS) == 3
        assert "APPROVE" in PAYOR_ACTIONS
        assert "DENY" in PAYOR_ACTIONS
        assert "REQUEST_INFO" in PAYOR_ACTIONS

    def test_no_numeric_actions(self):
        """actions should be string labels, not numeric values"""
        for action in PROVIDER_ACTIONS:
            assert isinstance(action, str)
            assert not action.isdigit()
        for action in PAYOR_ACTIONS:
            assert isinstance(action, str)
            assert not action.isdigit()


class TestBoundedPendLoops:
    """test bounded REQUEST_INFO constraints"""

    def test_max_request_info_defined(self):
        """max REQUEST_INFO cycles per level should be defined"""
        assert MAX_REQUEST_INFO_PER_LEVEL == 2

    def test_workflow_levels_defined(self):
        """3-level workflow should be defined"""
        assert len(WORKFLOW_LEVELS) == 3
        assert 0 in WORKFLOW_LEVELS
        assert 1 in WORKFLOW_LEVELS
        assert 2 in WORKFLOW_LEVELS

    def test_level_2_terminal(self):
        """level 2 (independent_review) should be terminal"""
        assert WORKFLOW_LEVELS[2]["terminal"] is True
        assert WORKFLOW_LEVELS[2]["can_pend"] is False

    def test_levels_0_and_1_can_pend(self):
        """levels 0 and 1 can use REQUEST_INFO"""
        assert WORKFLOW_LEVELS[0]["can_pend"] is True
        assert WORKFLOW_LEVELS[1]["can_pend"] is True

    def test_level_2_no_copilot(self):
        """level 2 should have copilot_active = False"""
        assert WORKFLOW_LEVELS[2]["copilot_active"] is False
        # levels 0 and 1 have copilot active
        assert WORKFLOW_LEVELS[0]["copilot_active"] is True
        assert WORKFLOW_LEVELS[1]["copilot_active"] is True

    def test_level_2_no_internal_notes(self):
        """level 2 (independent review) should NOT see internal notes"""
        assert WORKFLOW_LEVELS[2]["sees_internal_notes"] is False
        # levels 0 and 1 can see internal notes
        assert WORKFLOW_LEVELS[0]["sees_internal_notes"] is True
        assert WORKFLOW_LEVELS[1]["sees_internal_notes"] is True

    def test_level_2_independent(self):
        """level 2 should be marked as independent"""
        assert WORKFLOW_LEVELS[2]["independent"] is True
        assert WORKFLOW_LEVELS[0]["independent"] is False
        assert WORKFLOW_LEVELS[1]["independent"] is False


class TestProviderPromptActionSpace:
    """test provider prompts use discrete action space"""

    @pytest.fixture
    def mock_state(self):
        state = MagicMock()
        state.authorization_request = MagicMock()
        state.authorization_request.authorization_status = "approved"
        return state

    def test_claim_appeal_decision_prompt_has_3_actions(self, mock_state):
        """claim appeal decision prompt should offer 3 discrete actions"""
        prompt = create_provider_claim_appeal_decision_prompt(
            state=mock_state,
            denial_reason="Insufficient documentation",
            service_request={"medication_name": "TestMed", "dosage": "100mg"},
            pa_type="specialty_medication"
        )

        assert "CONTINUE" in prompt
        assert "APPEAL" in prompt
        assert "ABANDON" in prompt
        assert '"action"' in prompt

    def test_pend_response_prompt_has_limited_actions(self, mock_state):
        """pend response prompt should offer CONTINUE and ABANDON only"""
        pend_decision = {"pend_reason": "Need more docs", "requested_documents": ["doc1"]}
        prompt = create_provider_pend_response_prompt(
            state=mock_state,
            pend_decision=pend_decision,
            service_request={"medication_name": "TestMed", "dosage": "100mg"},
            pend_iteration=1,
            pa_type="specialty_medication"
        )

        assert "CONTINUE" in prompt
        assert "ABANDON" in prompt
        assert '"action"' in prompt


class TestPayorPromptActionSpace:
    """test payor prompts enforce bounded pend loops"""

    @pytest.fixture
    def mock_state(self):
        state = MagicMock()
        state.authorization_request = MagicMock()
        state.authorization_request.authorization_status = "approved"
        state.authorization_request.criteria_used = "Medical necessity"
        return state

    def test_resubmission_review_at_limit_no_pend_option(self, mock_state):
        """at max pend iteration, payor should NOT have pend option"""
        prompt = create_payor_claim_resubmission_review_prompt(
            state=mock_state,
            resubmission_packet={"cover_letter": "Test"},
            pend_decision={"pend_reason": "Need more", "requested_documents": ["doc"]},
            service_request={"medication_name": "TestMed", "dosage": "100mg"},
            cost_ref={"drug_acquisition_cost": 5000, "administration_fee": 100},
            pend_iteration=MAX_REQUEST_INFO_PER_LEVEL,  # at limit
            pa_type="specialty_medication"
        )

        assert "FINAL DECISION REQUIRED" in prompt
        assert '"approved" | "rejected"' in prompt
        # pended should NOT be an option at the limit
        assert '"pended"' not in prompt or "NOT available" in prompt

    def test_resubmission_review_before_limit_has_pend_option(self, mock_state):
        """before max pend iteration, payor should have pend option"""
        prompt = create_payor_claim_resubmission_review_prompt(
            state=mock_state,
            resubmission_packet={"cover_letter": "Test"},
            pend_decision={"pend_reason": "Need more", "requested_documents": ["doc"]},
            service_request={"medication_name": "TestMed", "dosage": "100mg"},
            cost_ref={"drug_acquisition_cost": 5000, "administration_fee": 100},
            pend_iteration=1,  # before limit
            pa_type="specialty_medication"
        )

        assert '"approved" | "rejected" | "pended"' in prompt
        assert "REQUEST_INFO" in prompt
