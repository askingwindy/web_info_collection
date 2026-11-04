"""Explicit per-check semantic rules; source snapshots are engineering evidence.

Bump the affected rule when its meaning changes. Review identities bind the
sample ID and every annotation/image/tree byte, never their filesystem location.
"""
from copy import deepcopy
import hashlib
import json

RULE_VERSIONS = {
    'visual_alignment': 'all-original-frames-actions-trees-1',
    'terminal_semantics': 'truthful-fragment-five-eight-and-verified-login-download-return-4',
    'language': 'page-control-language-consistency-and-chinese-narratives-2',
    'privacy': 'all-original-frames-sensitive-content-1',
    'substantive_difference': 'actual-trajectories-bound-pair-coverage-and-terminal-images-3',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def rule_ids():
    return {name: digest({'semantic_rule': name, 'version': version})
            for name, version in RULE_VERSIONS.items()}


def sample_identity(candidate):
    return {key: deepcopy(candidate[key]) for key in
            ('sample_id', 'annotation_sha256', 'evidence_sha256')}


def invalidate_record(record):
    """Derive pending states without rewriting the supplied original record."""
    current = rule_ids(); saved = record.get('semantic_rule_ids')
    if saved is None:
        return record
    if (not isinstance(saved, dict) or set(saved) != set(current)
            or any(not isinstance(value, str) or len(value) != 64 for value in saved.values())):
        raise ValueError('Malformed per-check semantic rule identities')
    result = deepcopy(record); invalidated = []
    for name in current:
        if saved[name] != current[name]:
            invalidated.append({'check': name, 'reason': 'semantic_rule_changed',
                                'reviewed_rule_id': saved[name], 'current_rule_id': current[name]})
            result['checks'][name] = {
                'status': 'REVIEW_REQUIRED', 'note': 'Relevant semantic rule changed; original decision retained in source review.',
                'evidence_steps': [], 'invalidation_reason': 'semantic_rule_changed'}
    result['semantic_reuse'] = {
        'source_record_sha256': digest(record),
        'reused_checks': [name for name in current if saved[name] == current[name]],
        'invalidated_checks': invalidated, 'original_record_modified': False}
    return result
