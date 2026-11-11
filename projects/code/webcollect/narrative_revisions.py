"""Evidence-cited narrative revisions without changing captured evidence or actions."""
import copy
import hashlib
import json
from pathlib import Path


def load_plan(path):
    if path is None:
        return None
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not all(isinstance(plan.get(k), str) and plan[k].strip() for k in ('prompt', 'author')) or
            not isinstance(plan.get('samples'), list)):
        raise ValueError('Invalid evidence-cited narrative revision plan')
    ids = [r.get('sample_id') for r in plan['samples']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate narrative revision sample')
    return plan


def apply(sample, revision):
    sample = Path(sample); path = sample / 'annotation.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != revision.get('annotation_sha256'):
        raise ValueError('Narrative revision source annotation hash differs')
    evidence_hashes = revision.get('evidence_sha256')
    if not isinstance(evidence_hashes, dict) or not evidence_hashes:
        raise ValueError('Narrative revision requires image/tree SHA256 bindings')
    data = json.loads(path.read_text(encoding='utf-8')); original = copy.deepcopy(data); seen = set()
    delivered = {step[k] for step in data['steps'] for k in ('image_path', 'ui_tree_path')}
    for edit in revision.get('edits', []):
        name = edit.get('path', ''); parts = name.split('/')
        allowed = name in {'task_instruction', 'final_result', 'completion_judgement'} or (
            len(parts) == 3 and parts[0] == 'steps' and parts[1].isdigit() and
            parts[2] in {'page_name', 'user_goal', 'next_step_rationale', 'step_result'}) or (
            len(parts) == 4 and parts[0] == 'steps' and parts[1].isdigit() and parts[2] == 'action' and
            parts[3] in {'precondition', 'expected_result'})
        if not allowed or name in seen:
            raise ValueError('Only distinct narrative fields may be revised: ' + name)
        seen.add(name); node = data
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        key = parts[-1]
        if node[key] != edit.get('before') or not isinstance(edit.get('after'), str) or not edit['after'].strip():
            raise ValueError('Narrative revision old value or replacement differs: ' + name)
        evidence = edit.get('evidence', [])
        if not evidence:
            raise ValueError('Narrative edit requires delivered image/tree evidence')
        for relative in evidence:
            p = sample / relative
            if (relative not in delivered or p.is_symlink() or
                    not p.is_file() or not p.resolve().is_relative_to(sample.resolve())):
                raise ValueError('Narrative evidence must be an existing delivered image/tree')
            if evidence_hashes.get(relative) != hashlib.sha256(p.read_bytes()).hexdigest():
                raise ValueError('Narrative revision image/tree evidence hash differs')
        node[key] = edit['after']
    for before, after in zip(original['steps'], data['steps']):
        old = {k: v for k, v in before['action'].items() if k not in {'precondition', 'expected_result'}}
        new = {k: v for k, v in after['action'].items() if k not in {'precondition', 'expected_result'}}
        if old != new or before['tool_call'] != after['tool_call']:
            raise ValueError('Narrative revision changed an executed action')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return data
