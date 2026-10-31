"""Synthetic handoff samples for the consumer agent.

Builds a disposable pool containing one legacy candidate and the three
candidate-producer-3 kinds, then records read/claim examples over both
protocols, the expected frozen snapshots and a protocol/version-mismatch
result. No network, no real search/model, no consumer execution.
"""
import argparse
import json
from pathlib import Path
from webcollect.batch_core import load_json, save_json
from .candidate_pool import CandidatePool, VERSION, VERSION2
from .candidate_discovery import PROTOCOL3, reference
from .site_pool import SitePool


def build_samples(pool_path, output):
    pool_path = Path(pool_path).resolve()
    if pool_path.exists():
        raise ValueError('Handoff samples need a fresh disposable pool path')
    root = Path(output).resolve(); root.mkdir(parents=True, exist_ok=True)
    SitePool(pool_path, initialize=True)
    pool = CandidatePool(pool_path, install=True)

    proof = root / 'handoff-evidence.json'
    save_json(proof, {'CONTROLLED': 'synthetic handoff evidence only', 'protocol': PROTOCOL3})
    search_raw = root / 'search-original.json'
    save_json(search_raw, {'search_result': [
        {'link': 'https://example.org/catalog#/search', 'title': '公共图书馆 馆藏检索', 'content': '检索入口'},
        {'link': 'https://convert.example.org/units?from=C&to=F', 'title': '单位换算 在线换算器', 'content': '换算工具'}]})
    goals = root / 'caller-goals.json'
    save_json(goals, {'schema_version': 'webcollect-caller-goals-1', 'goals': [
        {'uri': 'https://convert.example.org/units',
         'requested_goal': {'kind': 'unit_convert', 'entity': 'temperature',
                            'parameters': {'value': '25', 'from': '摄氏度', 'to': '华氏度'}}}]})
    search_source = {'origin': 'glm_agent', 'run_id': 'handoff-synthetic',
                     'search_request_id': 'search-handoff-1', 'raw_hit_index': 0, 'source_index': 0,
                     'references': [reference(search_raw), reference(proof)]}

    legacy = pool.put({'schema_version': VERSION, 'entry_url': 'https://legacy.example.org/',
                       'name': '旧协议候选', 'parent_category': '图书文化', 'business_kind': '检索',
                       'description': '旧结构化目标候选',
                       'target': {'kind': 'search', 'entity': 'book', 'parameters': {'query': '三国'}}},
                      {'origin': 'codex_session', 'run_id': 'handoff-synthetic',
                       'references': [reference(proof)]})
    entry_plain = pool.put({'schema_version': VERSION2, 'candidate_kind': 'entry',
                            'entry_url': 'https://example.org/catalog#/search', 'requested_goal': None},
                           {**search_source, 'category_hint': None, 'business_kind': None})
    entry_suggested = pool.put({'schema_version': VERSION2, 'candidate_kind': 'entry',
                                'entry_url': 'https://convert.example.org/units?from=C&to=F', 'requested_goal': None},
                               {**search_source, 'raw_hit_index': 1, 'source_index': 1,
                                'category_hint': '在线工具', 'business_kind': '单位换算', 'source_type': 'tool',
                                'suggested_goal': {'kind': 'unit_convert', 'entity': 'temperature',
                                                   'parameters': {'value': '100', 'from': '摄氏度', 'to': '华氏度'}}})
    target = pool.put({'schema_version': VERSION2, 'candidate_kind': 'target',
                       'entry_url': 'https://convert.example.org/units',
                       'requested_goal': load_json(goals)['goals'][0]['requested_goal']},
                      {'origin': 'codex_session', 'run_id': 'handoff-synthetic', 'protocol': PROTOCOL3,
                       'goal_origin': 'caller', 'goal_frozen': load_json(goals)['goals'][0]['requested_goal'],
                       'caller_input': reference(goals), 'references': [reference(goals), reference(proof)]})

    legacy_rows = pool.rows()
    entry_rows = pool.rows(protocols=(VERSION2,))
    legacy_claim = pool.claim_next('legacy-worker', 'handoff-legacy-claim')
    entry_claim = pool.claim_next('entry-worker', 'handoff-entry-claim', protocols=(VERSION2,))
    entry_replay = pool.claim_next('entry-worker', 'handoff-entry-claim', protocols=(VERSION2,))
    mismatch_new_claimer_old_id = pool.claim_next('entry-worker', 'handoff-mismatch-1',
                                                  protocols=(VERSION2,), candidate_id=legacy)
    mismatch_legacy_claimer_new_id = pool.claim_next('legacy-worker', 'handoff-mismatch-2', candidate_id=entry_plain)
    try:
        pool.claim_next('entry-worker', 'handoff-mismatch-3', protocols=('webcollect-data-candidate-3',))
        unsupported = {'error': 'missing'}
    except ValueError as error:
        unsupported = {'error_type': 'ValueError', 'reason': str(error)}

    samples = {'schema_version': 'webcollect-candidate-handoff-samples-1',
        'pool': str(pool_path), 'producer_protocol': PROTOCOL3,
        'candidate_bodies': {'legacy_v1': VERSION, 'entry_or_target_v2': VERSION2},
        'candidates': {'legacy': legacy, 'entry_plain_goal_null': entry_plain,
                       'entry_with_optional_suggestion': entry_suggested, 'explicit_target': target},
        'read': {
            'legacy_caller_rows(protocols unset)': [{'candidate_id': r['candidate_id'],
                'candidate': r['candidate']} for r in legacy_rows],
            'entry_caller_rows(protocols=(webcollect-data-candidate-2,))': [
                {'candidate_id': r['candidate_id'], 'candidate': r['candidate'],
                 'sources': r['sources']} for r in entry_rows]},
        'claim': {
            'legacy_claim_of_old_candidate': legacy_claim,
            'entry_claim_expected_snapshot': {
                'candidate_id': entry_claim['candidate_id'], 'version': entry_claim['version'],
                'snapshot_body': entry_claim['snapshot'],
                'frozen_sources_at_claim': entry_claim['sources'],
                'note': 'snapshot keeps the exact body and source references visible at claim time; '
                        'later producer suggestions only append sources and never alter this lease'},
            'replay_same_request_returns_original': {'same_claim': entry_replay['claim_id'] == entry_claim['claim_id'],
                'same_token': entry_replay['token'] == entry_claim['token']},
            'version_mismatch': {
                'new_protocol_claimer_requesting_legacy_id': mismatch_new_claimer_old_id,
                'legacy_claimer_requesting_entry_id': mismatch_legacy_claimer_new_id,
                'unsupported_protocol_declaration': unsupported,
                'note': 'a caller only ever claims the body protocol it declared; '
                        'a legacy worker scanning pending never sees webcollect-data-candidate-2 rows'}},
        'lease': {'lease_seconds_default': 300,
                  'expiry': 'an expired lease moves the candidate to reconcile and the old token cannot submit'},
        'notes': 'All evidence files are synthetic fixtures; production stays STOPPED_BY_USER.'}
    save_json(root / 'handoff-samples.json', samples)
    return samples


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(build_samples(args.pool, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
