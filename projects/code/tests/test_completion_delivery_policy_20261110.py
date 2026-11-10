"""New completion gate never reinterprets historical fragment policy."""
from copy import deepcopy
from webcollect.closing_policy import COMPLETED_GOAL_DELIVERY, completion_delivery_decision


def completed(count=5):
    annotation = {'completion_status':'success', 'steps':[
        {'action':{'action_type':'scroll'}} for _ in range(count)] + [{'action':{'action_type':'complete'}}]}
    raw = {'stop_reason':'ready', 'collection_ending':{'kind':'HOST_PLAN_ENDPOINT',
        'safe_for_pending_sample':True, 'flagged':False, 'external_effect_unknown':False,
        'endpoint_evidence':{'image':{'sha256':'sealed'},
            'session_objective_evidence':{'status':'VERIFIED'}}}}
    raw['goal_evidence'] = {'checks':[{'field':'original result','status':'VERIFIED'}]}
    return annotation, raw


def test_bound_original_goal_and_real_count():
    annotation, raw = completed()
    decision = completion_delivery_decision(annotation, raw)
    assert decision['delivery_policy'] == COMPLETED_GOAL_DELIVERY
    assert decision['delivery_eligible'] and not decision['QC_approval']
    annotation, raw = completed(3)
    assert completion_delivery_decision(annotation, raw)['original_goal_completed']
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_success_string_and_missing_goal_never_grant_eligibility():
    annotation, raw = completed()
    assert not completion_delivery_decision(annotation, {})['delivery_eligible']
    raw['goal_evidence']['checks'][0]['status'] = 'UNVERIFIED'
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_internal_fragments_unknown_and_incomplete_are_excluded():
    annotation, raw = completed()
    for key, value in [('trusted_prefix', {'source_interval':{}}),
                       ('stop_reason','blocked')]:
        changed = deepcopy(raw);changed[key] = value
        assert not completion_delivery_decision(annotation, changed)['delivery_eligible']
    for key in ('flagged','external_effect_unknown'):
        changed = deepcopy(raw);changed['collection_ending'][key] = True
        assert not completion_delivery_decision(annotation, changed)['delivery_eligible']
    annotation['completion_status'] = 'controlled_exception'
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_above_effective_ceiling_is_not_ordinary_delivery():
    annotation, raw = completed(11)
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_new_wiki_completion_supersedes_only_legacy_placeholder_checks():
    from webcollect.postprocess import ready_requires_prefix
    objective = {'status':'VERIFIED', 'completion':{'decision':{'sha256':'sealed'}}}
    terminal = {'stop_reason':'ready', 'goal_evidence':{
        'checks':[{'field':'original question','status':'UNVERIFIED'}],
        'session_objective':objective}, 'collection_ending':{
            'kind':'HOST_PLAN_ENDPOINT', 'safe_for_pending_sample':True, 'flagged':False,
            'endpoint_evidence':{'session_objective_evidence':deepcopy(objective)}}}
    task = {'fragment':{'ending_policy':'webcollect-five-ten-effective-ending-5',
        'wiki_reading_completion_protocol':'webcollect-wiki-reading-completion-2'}}
    assert not ready_requires_prefix(task, terminal)
    task['fragment']['wiki_reading_completion_protocol'] = 'webcollect-wiki-reading-completion-1'
    assert ready_requires_prefix(task, terminal)
    task['fragment']['wiki_reading_completion_protocol'] = 'webcollect-wiki-reading-completion-2'
    terminal['collection_ending']['endpoint_evidence']['session_objective_evidence']['status'] = 'UNVERIFIED'
    assert ready_requires_prefix(task, terminal)


def test_weak_rendered_keyword_cannot_replace_original_checks():
    annotation, raw = completed()
    raw['collection_ending']['endpoint_evidence'].update(
        source='host_rendered_state', predicate={'kind':'visible_text','text':'FAQ'})
    raw['goal_evidence']['checks'][0]['status'] = 'UNVERIFIED'
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']
    raw['goal_evidence'] = {}
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_new_wiki_requires_bound_original_questions_and_all_answers():
    annotation, raw = completed()
    completion = {'schema_version':'webcollect-wiki-reading-completion-2',
        'decision':{'sha256':'sealed'}, 'original_working_goal':'fixed question',
        'original_plan_sha256':'frozen', 'original_checks':[{'field':'original question'}],
        'answer':{'check_answers':[{'check_index':0,'answer':'answer with bound citations'}]}}
    objective = {'protocol':'webcollect-wiki-reading-completion-2',
        'status':'VERIFIED', 'completion':completion}
    raw['goal_evidence'] = {'checks':[{'status':'UNVERIFIED'}], 'session_objective':objective}
    raw['collection_ending']['endpoint_evidence']['session_objective_evidence'] = deepcopy(objective)
    assert completion_delivery_decision(annotation, raw)['delivery_eligible']
    raw['collection_ending']['endpoint_evidence']['session_objective_evidence']['completion']['answer']['check_answers'] = []
    assert not completion_delivery_decision(annotation, raw)['delivery_eligible']


def test_saved_internal_fragment_without_candidate_leaves_pending_queue(tmp_path, monkeypatch):
    """Use real saved annotation/receipt bytes; no customer export exists."""
    import json
    from webcollect import consumer_campaign as campaign, candidate_consumer
    from webcollect.batch_core import file_sha
    sample = tmp_path/'execution'/'capture'/'samples'/'sample-internal'
    evidence = tmp_path/'execution'/'capture'/'evidence'/'sample-internal'
    sample.mkdir(parents=True);evidence.mkdir(parents=True)
    annotation, raw = completed()
    annotation['completion_status'] = 'controlled_exception'
    raw['collection_ending']['flagged'] = True
    annotation_path = sample/'annotation.json'
    annotation_path.write_text(json.dumps(annotation))
    receipt = evidence/'saved_sample.json'
    receipt.write_text(json.dumps({'sample_id':'sample-internal',
        'sample_files_sha256':{'annotation.json':file_sha(annotation_path)}, 'raw_execution':raw}))
    saved = {'sample_id':'sample-internal', 'result_location':str(sample),
        'save_receipt':{'path':str(receipt), 'sha256':file_sha(receipt)}}
    monkeypatch.setattr(candidate_consumer, 'verified_saved', lambda claim: saved)
    class Pool:
        def get_claim(self, identity):return {'claim_id':identity}
    state_path = tmp_path/'campaign.json'
    state_path.write_text(json.dumps({'schema_version':campaign.SITE_CAMPAIGN_VERSION,
        'counting_policy':COMPLETED_GOAL_DELIVERY, 'pending_deliveries':[{'claim_id':'claim'}],
        'deliveries':[], 'delivery_root':str(tmp_path/'customer'),
        'evidence_root':str(tmp_path/'campaign-evidence')}))
    assert not (tmp_path/'execution'/'candidate').exists()
    campaign.publish_pending(state_path, Pool())
    state = json.loads(state_path.read_text())
    assert state['pending_deliveries'] == [] and state['deliveries'] == []
    assert len(state['internal_retained']) == 1
    assert state['internal_retained'][0]['save_receipt'] == saved['save_receipt']
    assert state['internal_retained'][0]['delivery_eligible'] is False
    assert not (tmp_path/'customer').exists()
