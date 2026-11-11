"""Semantic-check names; review identities bind sample and annotation bytes.

Each check name below is the current single implementation. Rules are fixed
directly in their owning module; there is no per-rule version registry.
"""
from copy import deepcopy
import hashlib
import json

CHECKS = ('visual_alignment', 'terminal_semantics', 'language', 'privacy',
          'substantive_difference')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def sample_identity(candidate):
    return {key: deepcopy(candidate[key]) for key in
            ('sample_id', 'annotation_sha256', 'evidence_sha256')}
