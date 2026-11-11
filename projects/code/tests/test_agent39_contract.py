"""Disposable, credential-free checks for the consumer v3 contract."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from jsonschema import validate, ValidationError
from webcollect.react_protocol import native_tools, VERSION
from webcollect.react_session import ALLOWED_TOOL_ACTIONS
from webcollect.react_context import project
from webcollect.batch_core import BatchLedger, load_json, validate_config
from webcollect.model_credentials import account_id


class AgentContract(unittest.TestCase):
    def test_oversized_closed_reasoning_rounds_leave_latest_host_facts_and_no_orphan_tool(self):
        base = {'system':'rules','tools':[],'observation':{'id':'latest'},'requested_goal':{'x':10},
                'host_facts':{'actions':['click'],'unresolved':['original']},'last_tool_result':{'summary':'no dispatch'}}
        def pair(cid,size):
            return [{'role':'assistant','reasoning_content':'x'*size,'tool_calls':[{'id':cid}]},
                    {'role':'tool','tool_call_id':cid,'content':'{"data":{}}'}]
        for tail,expected in [(17000,1),(34000,0)]:
            source = {**base,'_history':pair('first',17000)+pair('last',tail)}
            before = deepcopy(source)
            wire = project(source)
            self.assertEqual(source,before)
            self.assertEqual(wire['host_facts'],source['host_facts'])
            self.assertEqual(wire['last_tool_result'],source['last_tool_result'])
            self.assertEqual(wire['context_metering']['history_closed_rounds'],expected)
            self.assertEqual(wire['context_metering']['history_rounds_omitted_for_size'],2-expected)
            self.assertEqual([m['role'] for m in wire['_history']],['assistant','tool']*expected)
            if expected:self.assertEqual(wire['_history'][0],source['_history'][2])
        with self.assertRaisesRegex(ValueError,'CONTEXT_PENDING_TOOL'):
            project({**base,'_history':pair('unclosed',36000)[:1]})

    def test_wechat_article_exclusion_is_frozen_and_leaves_other_destinations_available(self):
        from webcollect.react_session import build_url_task,validate_task
        from webcollect.candidate_navigation import extend,excluded_article
        origin = 'https://example.org/'
        article = 'https://mp.weixin.qq.com/s/example'
        task = build_url_task(url=origin,task_version='scope',skip_wechat_articles=True)
        ordinary = build_url_task(url=origin,task_version='scope')
        self.assertNotEqual(task['task_id'],ordinary['task_id'])
        self.assertFalse(excluded_article(ordinary,article))
        self.assertTrue(excluded_article(task,'https://MP.WEIXIN.QQ.COM/s?id=1'))
        self.assertFalse(excluded_article(task,'https://mp.weixin.qq.com/logo.png'))
        other = 'https://other.example.org/article'
        state = {'url':origin,'capture_controls':[{'href':article},{'href':other}]}
        self.assertEqual(extend(task,[origin],state),[origin,other])
        with self.assertRaisesRegex(ValueError,'ARTICLE_OUTSIDE_RUN_SCOPE'):
            extend(task,[origin],{'url':article},{'action_type':'click'})
        task['fragment'].pop('skip_wechat_articles')
        with self.assertRaises(ValueError):
            validate_task(task)

    def test_observed_external_navigation_keeps_distinct_hosts_and_trigger_required(self):
        from webcollect.react_session import build_url_task
        from webcollect.candidate_navigation import extend,verify_path
        from webcollect.candidate_contract import same_application
        task=build_url_task(url='https://example.org/',task_version='navigation')
        self.assertEqual(task['site_category'],'UNKNOWN')
        task['candidate_binding']={'candidate':{'entry_url':'https://example.org/'}}
        home={'url':'https://example.org/','capture_controls':[{'href':'https://external.example/details'}]}
        pages=extend(task,['https://example.org/'],home)
        self.assertIn('https://external.example/details',pages)
        self.assertFalse(same_application(task,'https://external.example/details'))
        with self.assertRaisesRegex(ValueError,'triggering action'):
            extend(task,['https://example.org/'],{'url':'https://unobserved.example/'})
        self.assertEqual(verify_path(task,[home,{'url':'https://external.example/details'},home],
            [{'action_type':'click'},{'action_type':'back'}]),pages)
        with self.assertRaises(ValueError):
            extend(task,pages,{'url':'http://127.0.0.1/'},{'action_type':'click'})

    def test_inspect_root_declares_provider_fields_and_reports_empty_arguments(self):
        from jsonschema import Draft202012Validator
        schema=next(t['function']['parameters'] for t in native_tools(ALLOWED_TOOL_ACTIONS) if t['function']['name']=='inspect')
        self.assertIn('kind',schema['properties'])
        self.assertIn('query',schema['properties'])
        self.assertIn('decision_summary',schema['required'])
        errors=list(Draft202012Validator(schema).iter_errors({}))
        self.assertIn("'kind' is a required property",errors[0].message)
        validate({'kind':'search','query':'单位','observation_id':'obs','decision_summary':'查找单位控件'},schema)
        with self.assertRaises(ValidationError):
            validate({'kind':'html','target_id':'not-applicable','observation_id':'obs','decision_summary':'读取材料'},schema)

    def test_optional_update_and_unicode_length_boundaries(self):
        tools={t['function']['name']:t['function']['parameters'] for t in native_tools(ALLOWED_TOOL_ACTIONS)}
        args={'decision_summary':'查看分支','observation_id':'obs','step':{'action':'back','goal':'返回','expected':'列表可见'}}
        validate(args,tools['act'])
        args['goal_update']={'description':'中'*300,'basis_observation_id':'obs','reason':'当前列表'}
        validate(args,tools['act'])
        args['goal_update']['description']+='中'
        with self.assertRaises(ValidationError):validate(args,tools['act'])
        with self.assertRaises(ValidationError):validate({**args,'rogue':True},tools['act'])

    def test_context_window_preserves_facts_and_pairs_at_25_rounds(self):
        history=[];sizes=[]
        prompt={'system':'fixed rules','tools':native_tools(ALLOWED_TOOL_ACTIONS),
                'observation':{'observation_id':'now','image_ref':'current.png'},
                'requested_goal':{'parameter':'精确值'*2000},
                'host_facts':{'visited':['A','back','B'], 'unknown':True,'failed':['A/blocked']}}
        for n in range(25):
            history.extend([{'role':'user','content':'old HTML'*4000},
                {'role':'assistant','reasoning_content':'opaque','tool_calls':[{'id':str(n)}]},
                {'role':'tool','tool_call_id':str(n),'content':json.dumps({'data':{'observation':{'html':'old'*9000}},'status':'ok'})}])
            original=deepcopy(history)
            wire=project({**prompt,'_history':history})
            self.assertEqual(history,original)
            self.assertEqual(wire['requested_goal'],prompt['requested_goal'])
            self.assertEqual(wire['host_facts'],prompt['host_facts'])
            self.assertEqual(len(wire['_history']),min(n+1,2)*2)
            for a,t in zip(wire['_history'][::2],wire['_history'][1::2]):
                self.assertEqual(a['tool_calls'][0]['id'],t['tool_call_id'])
                self.assertEqual(a['reasoning_content'],'opaque')
            sizes.append(len(json.dumps(wire)))
        self.assertLess(max(sizes[2:])-min(sizes[2:]),200)

    def test_session_binding_concurrent_reordered_and_removed_account(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);token=root/'token.yaml'
            token.write_text('glm: [offline-first, offline-second, offline-first]')
            from test_model_provider_protocols import ProviderProtocolTests
            config=ProviderProtocolTests.config(self,'glm',vision=True)
            config['model']['api_key_file']=str(token)
            config['model']['request_overhead_tokens']=1
            ledger=BatchLedger(root/'jobs.sqlite3',config,initialize=True)
            with patch.dict('os.environ',{},clear=True):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    values=list(executor.map(lambda _:ledger.bind_model_session('attempt'),range(2)))
                self.assertEqual(values,['offline-first']*2)
                self.assertEqual(BatchLedger(ledger.path,config).bind_model_session('second-attempt'),'offline-second')
                self.assertEqual(ledger.bind_model_session('third-attempt'),'offline-first')
                token.write_text('glm: [offline-second, offline-first]')
                self.assertEqual(ledger.bind_model_session('attempt'),'offline-first')
                token.write_text('glm: [offline-second]')
                with self.assertRaisesRegex(ValueError,'suppressed'):
                    ledger.bind_model_session('attempt')
                self.assertEqual(ledger.summary()['model_requests'],0)
                for secret in ('offline-first','offline-second'):
                    self.assertNotIn(secret.encode(),ledger.path.read_bytes())

    def test_token_config_has_no_rates_and_settles_usage_without_money(self):
        with tempfile.TemporaryDirectory() as temp:
            config=load_json(Path(__file__).resolve().parents[1]/'config/batch-synthetic.json')
            config['model']['accounting_mode']='tokens-1'
            config['model'].pop('rates');config['model'].pop('reserve_cost_micros')
            config['budget'].pop('currency')
            self.assertEqual(validate_config(config),config)
            ledger=BatchLedger(Path(temp)/'jobs.sqlite3',config,initialize=True)
            job=ledger.claim('offline',job_id=ledger.enqueue('offline',{'test':True}))
            request=ledger.reserve_request(job,'test',0,{'accounting_mode':'tokens-1'})
            ledger.settle_request(request['id'],state='succeeded',usage={'input_tokens':10,'output_tokens':5,'cached_input_tokens':3})
            report=ledger.summary()
            self.assertEqual(report['usage_covered_requests'],1)
            self.assertEqual(report['stages']['offline']['input_tokens'],10)
            self.assertNotIn('cost',json.dumps(report))
            from webcollect.model_audit import token_audit
            audit=token_audit(ledger.path)
            self.assertEqual(audit['totals']['input_tokens'],10)
            self.assertEqual(audit['totals']['cached_input_tokens'],3)
            self.assertNotIn('cost',json.dumps(audit))
