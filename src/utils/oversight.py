"""
oversight module for AI arms race experiment

implements metered editing + checking budget applied to AI-generated drafts
"""
from typing import Literal, Tuple, Dict, Any
import difflib
import json
from langchain_core.messages import HumanMessage

from src.utils.prompts import OVERSIGHT_BUDGETS


def _count_words(text: str) -> int:
    """count words in text"""
    return len(text.split())


def _compute_diff_metrics(original: str, revised: str) -> Dict[str, Any]:
    """compute diff metrics between original and revised text"""
    orig_words = original.split()
    rev_words = revised.split()

    # use SequenceMatcher for word-level diff
    matcher = difflib.SequenceMatcher(None, orig_words, rev_words)

    # count changed words
    changed_words = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            changed_words += max(i2 - i1, j2 - j1)
        elif tag == 'delete':
            changed_words += i2 - i1
        elif tag == 'insert':
            changed_words += j2 - j1

    # char-level diff
    orig_chars = len(original)
    rev_chars = len(revised)
    char_diff = abs(rev_chars - orig_chars)

    # diff ratio (0 = identical, 1 = completely different)
    diff_ratio = 1.0 - matcher.ratio()

    return {
        'changed_word_count': changed_words,
        'changed_char_count': char_diff,
        'diff_ratio': round(diff_ratio, 4),
        'original_word_count': len(orig_words),
        'revised_word_count': len(rev_words)
    }


def _build_evidence_summary(evidence_packet: Dict[str, Any]) -> str:
    """build a summary of available evidence for the oversight prompt"""
    parts = []

    if evidence_packet.get('vitals'):
        parts.append(f"Vitals: {json.dumps(evidence_packet['vitals'])}")
    if evidence_packet.get('labs'):
        parts.append(f"Labs: {json.dumps(evidence_packet['labs'])}")
    if evidence_packet.get('icd10_codes'):
        parts.append(f"Diagnoses: {', '.join(evidence_packet['icd10_codes'])}")
    if evidence_packet.get('cpt_codes'):
        parts.append(f"Procedures: {', '.join(evidence_packet['cpt_codes'])}")
    if evidence_packet.get('policy_criteria'):
        criteria = json.dumps(evidence_packet['policy_criteria'])
        parts.append(f"Policy criteria: {criteria}")
    if evidence_packet.get('missing_items'):
        parts.append(f"Missing items: {', '.join(evidence_packet['missing_items'])}")
    if evidence_packet.get('prior_denials'):
        parts.append(f"Prior denials: {json.dumps(evidence_packet['prior_denials'])}")
    if evidence_packet.get('test_results'):
        parts.append(f"Test results: {json.dumps(evidence_packet['test_results'])}")

    return '\n'.join(parts) if parts else 'No structured evidence available'


def apply_oversight_edit(
    role: Literal["provider", "payor"],
    oversight_level: str,
    draft_text: str,
    evidence_packet: Dict[str, Any],
    llm,
    rng_seed: int = 42  # reserved for future stochastic editing
) -> Tuple[str, Dict[str, Any]]:
    """
    apply metered oversight editing to an AI-generated draft

    args:
        role: "provider" or "payor"
        oversight_level: "low", "medium", or "high"
        draft_text: the AI copilot's generated draft
        evidence_packet: structured evidence dict (vitals, labs, codes, etc)
        llm: the reviewer LLM (base provider/payor LLM)
        rng_seed: seed for reproducibility

    returns:
        tuple of (final_text, edit_metadata_dict)

    behavior by level:
        low: minimal/no edits, strictly obey small budget
        medium: can fix contradictions, add missing required items
        high: extensive editing, remove unsupported claims, verify all
    """
    budgets = OVERSIGHT_BUDGETS.get(oversight_level, OVERSIGHT_BUDGETS['medium'])
    max_tokens = budgets['max_tokens_changed']
    max_passes = budgets['max_edit_passes']
    max_checks = budgets['max_evidence_checks']

    evidence_summary = _build_evidence_summary(evidence_packet)

    # for low oversight, do minimal editing
    if oversight_level == 'low':
        # very light touch - only fix obvious errors
        prompt = f"""You are reviewing a {role} draft. Make MINIMAL changes only.

BUDGET CONSTRAINTS (STRICT):
- Maximum words to change: {max_tokens}
- Only fix obvious typos or formatting issues
- Do NOT add new content or remove claims
- If draft is acceptable, return it unchanged

DRAFT TO REVIEW:
{draft_text}

AVAILABLE EVIDENCE (reference only):
{evidence_summary}

Return JSON:
{{
    "revised_text": "<your minimally edited text or original if no changes needed>",
    "edits_made": ["<edit 1>", ...],
    "tokens_changed_estimate": <number>
}}"""

    elif oversight_level == 'medium':
        prompt = f"""You are reviewing a {role} draft with standard oversight.

BUDGET CONSTRAINTS:
- Maximum words to change: {max_tokens}
- Maximum evidence checks: {max_checks}
- One editing pass only

ALLOWED EDITS:
1. Fix factual contradictions with evidence
2. Add missing required items from evidence packet
3. Improve clarity without changing meaning
4. Remove obviously unsupported claims

DO NOT:
- Completely rewrite the draft
- Add speculative content not in evidence
- Change the core argument or conclusion

DRAFT TO REVIEW:
{draft_text}

AVAILABLE EVIDENCE:
{evidence_summary}

Return JSON:
{{
    "revised_text": "<your edited text>",
    "edits_made": ["<description of edit 1>", "<description of edit 2>", ...],
    "tokens_changed_estimate": <number>,
    "evidence_checks_performed": <number>,
    "removed_unsupported_claims": ["<claim 1>", ...]
}}"""

    else:  # high oversight
        prompt = f"""You are performing THOROUGH oversight review of a {role} draft.

BUDGET CONSTRAINTS:
- Maximum words to change: {max_tokens}
- Maximum evidence checks: {max_checks}
- Up to {max_passes} editing passes allowed

REQUIRED CHECKS:
1. Verify ALL factual claims against evidence
2. Fix any contradictions with evidence
3. Add all missing required documentation items
4. Remove any unsupported or speculative claims
5. Ensure clinical/policy accuracy
6. Improve clarity and completeness

DRAFT TO REVIEW:
{draft_text}

AVAILABLE EVIDENCE:
{evidence_summary}

Return JSON:
{{
    "revised_text": "<your thoroughly reviewed text>",
    "edits_made": ["<description of edit 1>", "<description of edit 2>", ...],
    "tokens_changed_estimate": <number>,
    "evidence_checks_performed": <number>,
    "removed_unsupported_claims": ["<claim 1>", ...],
    "added_evidence_items": ["<item 1>", ...]
}}"""

    # invoke LLM
    messages = [HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    response_text = response.content

    # parse response
    try:
        clean_response = response_text
        if "```json" in clean_response:
            clean_response = clean_response.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_response:
            clean_response = clean_response.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean_response)
    except (json.JSONDecodeError, IndexError):
        # fallback: return original with error metadata
        return draft_text, {
            'oversight_level': oversight_level,
            'max_edit_passes': max_passes,
            'max_tokens_changed': max_tokens,
            'changed_word_count': 0,
            'changed_char_count': 0,
            'diff_ratio': 0.0,
            'edits_made_count': 0,
            'evidence_checks_count': 0,
            'removed_unsupported_claims_count': 0,
            'parse_error': True
        }

    revised_text = parsed.get('revised_text', draft_text)

    # safety check: if revised_text is not a string, use draft_text
    if not isinstance(revised_text, str):
        revised_text = draft_text

    edits_made = parsed.get('edits_made', [])
    llm_token_estimate = parsed.get('tokens_changed_estimate', 0)
    evidence_checks = parsed.get('evidence_checks_performed', 0)
    removed_claims = parsed.get('removed_unsupported_claims', [])

    # compute actual diff metrics
    diff_metrics = _compute_diff_metrics(draft_text, revised_text)

    # enforce budget: if over limit, use original
    if diff_metrics['changed_word_count'] > max_tokens * 1.5:  # 50% tolerance
        # over budget - revert to original with minimal edits
        revised_text = draft_text
        diff_metrics = _compute_diff_metrics(draft_text, draft_text)
        edits_made = ['reverted: exceeded edit budget']

    # build metadata
    metadata = {
        'oversight_level': oversight_level,
        'max_edit_passes': max_passes,
        'max_tokens_changed': max_tokens,
        'changed_word_count': diff_metrics['changed_word_count'],
        'changed_char_count': diff_metrics['changed_char_count'],
        'diff_ratio': diff_metrics['diff_ratio'],
        'edits_made_count': len(edits_made),
        'edits_made': edits_made,
        'evidence_checks_count': min(evidence_checks, max_checks),
        'removed_unsupported_claims_count': len(removed_claims),
        'llm_token_estimate': llm_token_estimate,
        'budget_enforced': diff_metrics['changed_word_count'] <= max_tokens * 1.5
    }

    return revised_text, metadata
