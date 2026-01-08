"""
oversight module for AI arms race experiment

implements metered editing + checking budget applied to AI-generated drafts
"""
from typing import Literal, Tuple, Dict, Any
import difflib
import json
from langchain_core.messages import HumanMessage

from src.utils.prompts import OVERSIGHT_GUIDANCE
from src.utils.json_parsing import extract_json_from_text


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
    if evidence_packet.get('policy_content'):
        policy_content = json.dumps(evidence_packet['policy_content'])
        parts.append(f"Policy content: {policy_content}")
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
    rng_seed: int = 42
) -> Tuple[str, Dict[str, Any]]:
    """
    apply human oversight review to an AI-generated draft

    args:
        role: "provider" or "payor"
        oversight_level: "low", "medium", or "high"
        draft_text: the AI copilot's generated draft
        evidence_packet: structured evidence dict (vitals, labs, codes, etc)
        llm: the reviewer LLM (base provider/payor LLM)
        rng_seed: seed for reproducibility

    returns:
        tuple of (final_text, edit_metadata_dict)

    workflow:
        1. review draft against evidence
        2. decide if editing is needed
        3. if needed, provide revised text; otherwise approve as-is

    metrics tracked:
        - tokens_changed: actual word count difference
        - oversight_llm_tokens: token count of oversight call (proxy for review time)
        - needs_editing: whether changes were made
    """
    guidance = OVERSIGHT_GUIDANCE.get(oversight_level, OVERSIGHT_GUIDANCE['medium'])
    evidence_summary = _build_evidence_summary(evidence_packet)

    # construct oversight prompt
    prompt = f"""You are reviewing an AI-generated {role} draft.

OVERSIGHT LEVEL: {oversight_level}
GUIDANCE: {guidance['instruction']}
TYPICAL BEHAVIOR: {guidance['typical_behavior']}

DRAFT TO REVIEW:
{draft_text}

AVAILABLE EVIDENCE:
{evidence_summary}

TASK:
1. Review the draft against the available evidence
2. Decide if editing is needed based on your oversight level
3. If editing is needed, provide revised text
4. If draft is acceptable as-is, set needs_editing to false

OUTPUT JSON:
{{
    "needs_editing": true or false,
    "review_notes": "brief assessment of draft quality",
    "revised_text": "full revised text if needs_editing=true, otherwise null",
    "changes_made": ["list of changes if any, otherwise empty array"]
}}

IMPORTANT: If needs_editing is false, set revised_text to null and leave changes_made empty.
"""

    # invoke LLM
    messages = [HumanMessage(content=prompt)]
    response = llm.invoke(messages)
    response_text = response.content

    # parse response
    try:
        parsed = extract_json_from_text(response_text)
    except Exception as e:
        # fallback: return original with error metadata
        return draft_text, {
            'oversight_level': oversight_level,
            'needs_editing': None,
            'tokens_changed': 0,
            'oversight_llm_tokens': len(prompt.split()),
            'diff_ratio': 0.0,
            'parse_error': True,
            'parse_error_message': str(e)
        }

    needs_editing = parsed.get('needs_editing', True)
    review_notes = parsed.get('review_notes', '')
    revised_text = parsed.get('revised_text')
    changes_made = parsed.get('changes_made', [])

    # if no editing needed, use original
    if not needs_editing or revised_text is None:
        revised_text = draft_text

    # safety check: if revised_text is not a string, use draft_text
    if not isinstance(revised_text, str):
        revised_text = draft_text

    # compute actual diff metrics
    diff_metrics = _compute_diff_metrics(draft_text, revised_text)

    # build metadata
    metadata = {
        'oversight_level': oversight_level,
        'needs_editing': needs_editing,
        'tokens_changed': diff_metrics['changed_word_count'],
        'oversight_llm_tokens': len(prompt.split()),
        'diff_ratio': diff_metrics['diff_ratio'],
        'changes_made': changes_made,
        'review_notes': review_notes,
    }

    return revised_text, metadata