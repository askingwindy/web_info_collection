"""Chinese-language exclusion wiring; disposable original ledgers, no real IO."""
import json
import asyncio
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_producer_v10 as producer_fixture
import test_candidate_entry_engineering as entry_fixture
import test_react_native as native_fixture
from webcollect.page_language import assess, validate_range, VERSION
from webcollect.collect import chinese_ratio
from webcollect.batch_core import load_json, file_sha
from webcollect.postprocess import session_record, effective_trajectory, process
from webcollect.trusted_prefix import project_prefix, V2_VERSION
from webcollect.candidate_consumer import consume
from site_planner import producer_observation
from site_planner.candidate_discovery import _publish_entry

ENGLISH = 'Convert documents to PDF online. Choose files and read the detailed conversion guide below.'


def english_surface(surface):
    surface.state['title'] = 'Convert documents to PDF'
    surface.state['visible_text'] = ENGLISH
    for element in surface.state['elements']:
        element['text'] = 'Quantity and price'


class LanguageIntegration(unittest.IsolatedAsyncioTestCase):
    def producer(self):
        f = producer_fixture.ProducerV10('test_same_observation_supplies_dom_and_publication_without_get')
        f.setUp(); self.addCleanup(f.doCleanups)
        return f

    def native(self):
        f = native_fixture.NativeSessionTests('test_native_tool_round_trip_filters_permissions_keeps_private_history')
        f.setUp(); self.addCleanup(f.doCleanups)
        return f

    async def test_negative_gate_preserves_chinese_technical_mixture_without_ratio_waiver(self):
        self.assertTrue(assess({'visible_text': ENGLISH})['excluded'])
        self.assertTrue(assess({'visible_text': ENGLISH+'\n简体中文\n繁體中文'})['excluded'])
        mixed = '这里介绍中文技术文档' * 10 + ' JavaScriptTypeScript ' * 5
        self.assertLess(chinese_ratio(mixed), .7)
        result = assess({'visible_text':mixed})
        self.assertFalse(result['excluded'])
        self.assertEqual(result['language_QC'], 'NOT_RUN')
        self.assertFalse(assess({'visible_text':'公开中文功能页面：数量、单价、计算结果'})['excluded'])
        self.assertEqual(assess({'visible_text':''})['reason'], 'insufficient_readable_text')
        self.assertFalse(assess({'visible_text':'\U00020000 Unicode extension character'})['excluded'])

    async def test_producer_filters_original_english_before_purpose_model_with_no_new_get(self):
        f = self.producer(); link=f.link()
        original=f.observation(link['uri'], '<main><p>'+ENGLISH+'</p></main>')
        before=file_sha(original['observation']['path'])
        with patch('site_planner.producer_observation.DiscoveryBrowser.__aenter__', side_effect=AssertionError('no replacement browser')):
            admitted, records=await asyncio.to_thread(producer_observation.screen,f.pool,f.ledger,[link],f.root)
        self.assertEqual(admitted, [])
        self.assertEqual(records[0]['decision']['policy'], VERSION)
        self.assertEqual(records[0]['decision']['status'], 'REJECTED')
        self.assertEqual(file_sha(original['observation']['path']), before)
        with f.ledger.connect() as con:
            self.assertEqual(con.execute('select count(*) from model_requests').fetchone()[0],0)
            self.assertEqual(con.execute('select count(*) from top_level_visits').fetchone()[0],1)

    async def test_publication_rejects_english_and_keeps_historical_published_row(self):
        f=self.producer();uri=f.link()['uri'];f.observation(uri,'<main>'+ENGLISH+'</main>')
        candidate=f.f.entry(uri);source=f.f.source
        header={'row_id':'new-en','run_id':'language-fixture','batch':0,'request_id':'original',
                'response_sha256':'original-response','raw_index':0}
        result=_publish_entry(f.pool,f.ledger,'language-fixture',f.root,header,candidate,source,{})
        self.assertEqual(result['result'],'REJECTED')
        self.assertEqual(result['row']['language_exclusion']['policy'],VERSION)
        self.assertEqual(f.pool.rows(protocols=('webcollect-data-candidate-2',)),[])
        old_header={**header,'row_id':'historical-en'}
        historical=f.pool.publish_row(old_header,candidate,source)
        before=deepcopy(f.pool.rows(protocols=('webcollect-data-candidate-2',)))
        repeated=_publish_entry(f.pool,f.ledger,'language-fixture',f.root,old_header,candidate,source,{})
        self.assertEqual(repeated,historical)
        self.assertEqual(f.pool.rows(protocols=('webcollect-data-candidate-2',)),before)

    async def test_consumer_english_entry_stops_before_model_and_formal_attempt(self):
        f=entry_fixture.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
        f.setUp();self.addCleanup(f.doCleanups);english_surface(f.surface)
        with f.io_boundaries():
            result=await consume(f.pool,f.claim,f.ledger,output=f.output,registry=f.registry,
                policy=f.policy_path,history_set=f.chain)
        self.assertEqual(result['reason'],'rendered_chinese_not_evidenced')
        self.assertEqual(result['formal_attempts'],0)
        self.assertEqual(f.prompts,[]);self.assertEqual(f.surface.executed,[])
        self.assertTrue(list(f.output.glob('*/first.png')))
        self.assertNotEqual(f.pool.get_claim(f.claim['claim_id'])['state'],'succeeded')

    async def test_new_language_marker_does_not_reclassify_old_raw_contract(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';state.write_text(json.dumps({'visible_text':ENGLISH}))
            record={'boundary':{},'terminal':{'final_observation_id':'en'},'trajectory':[],
                    'observations':{'en':{'state_path':str(state)}}}
            validate_range(record)
            record['boundary']['language_exclusion_policy']=VERSION
            with self.assertRaisesRegex(ValueError,'NON_CHINESE_SAVED_RANGE'):validate_range(record)
            record['boundary']['language_exclusion_policy']='unsupported'
            with self.assertRaisesRegex(ValueError,'Unknown'):validate_range(record)

    async def test_chinese_to_english_stops_and_only_chinese_prefix_can_be_saved(self):
        f=self.native();session,evidence,_=f.recorded([native_fixture.scroll('阅读中文正文'),native_fixture.scroll(),native_fixture.finish()])
        original=f.surface.execute_action;calls=0
        def execute(*args,**kwargs):
            nonlocal calls
            original(*args,**kwargs);calls+=1
            if calls==2:english_surface(f.surface)
        f.surface.execute_action=execute
        result=await session.run()
        self.assertEqual(result['effective_steps'],1,result)
        self.assertEqual(result['actual_actions'],2)
        raw=evidence/'raw';before=file_sha(raw/'raw-receipt.json')
        record=session_record(raw,allow_unknown_for_prefix=True)
        with self.assertRaisesRegex(ValueError,'NON_CHINESE_SAVED_RANGE'):effective_trajectory(record)
        prefix=project_prefix(record,raw,1,f.ids,rule=V2_VERSION)
        self.assertEqual(len(effective_trajectory(prefix)),1)
        derived=process(evidence,f.root/'delivery'/f.ids['sample_id'],f.ids,f.manifest,
            prefix_end_step=1,prefix_rule=V2_VERSION)
        self.assertEqual(derived['status'],'derived_saved',derived)
        self.assertEqual(file_sha(raw/'raw-receipt.json'),before)
        annotation=load_json(f.root/'delivery'/f.ids['sample_id']/'annotation.json')
        self.assertEqual(len(annotation['steps']),2)

    async def test_normal_chinese_full_consumer_still_formally_saves(self):
        f=entry_fixture.EntryEngineering('test_entry_cli_to_original_save_and_same_page')
        f.setUp();self.addCleanup(f.doCleanups)
        with f.io_boundaries():
            result=await consume(f.pool,f.claim,f.ledger,output=f.output,registry=f.registry,
                policy=f.policy_path,history_set=f.chain)
        self.assertTrue(result.get('saved'),result)
        self.assertEqual(f.pool.get_claim(f.claim['claim_id'])['state'],'succeeded')

    async def test_qc_chinese_rule_invalidates_only_old_language_check(self):
        from quality_inspector import semantic, ai_worker
        import test_semantic_reuse as reuse
        f=reuse.SemanticReuseTests('test_language_clarification_invalidates_only_language_and_keeps_original')
        f.setUp();self.addCleanup(f.doCleanups)
        with patch.dict(semantic.RULE_VERSIONS, {'language':'page-control-language-consistency-and-chinese-narratives-2'}):
            old_run=f.prepare_run('old-consistency-only')
        old=deepcopy(f.ledger.get(old_run['jobs'][0]['visual_job']))
        current=f.prepare_run('chinese-page-required')
        self.assertEqual(f.calls[-1][1]['properties']['checks']['required'],['language'])
        prompt=json.loads(f.calls[-1][2])['instruction']
        self.assertIn('business page must be Chinese-dominant',prompt)
        self.assertIn('Fail an English-dominant page',prompt)
        self.assertIn('Do not impose a numeric Chinese-character ratio',prompt)
        saved=f.ledger.get(current['jobs'][0]['visual_job'])
        for name in ('visual_alignment','terminal_semantics','privacy'):
            self.assertEqual(saved['result']['semantic_check_sources'][name],old['id'])
        self.assertEqual(f.ledger.get(old['id']),old)
