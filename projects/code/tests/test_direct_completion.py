from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from PIL import Image,ImageDraw
from webcollect.direct_completion import VERSION,terminal_bridge,completion,validate_plan,schema
from webcollect.agent_controller import exclusive
from webcollect.banded_plan import choice_schema,plan_schema
from jsonschema import Draft202012Validator,ValidationError

class DirectCompletion(unittest.TestCase):
    def setUp(self):
        self.task={'fragment':{'plan_protocol':'webcollect-banded-conditional-plan-8','direct_completion_protocol':VERSION,
            'session_objective':{'objective':{'evidence_contract':{'version':'webcollect-direct-article-reading-1'}}}}}
        self.state={'url':'https://example.org/wiki/A','title':'Article','document_identity':{'nonce':1},'scroll':[0,300],
            'screen_resolution':[300,200],'device_pixel_ratio':1,'values':[],'visible_text':'visible original body',
            'capture_readiness':{'document_ready':'complete','fonts_ready':True,'images_ready':True},
            'elements':[{'element_id':'main','native_role':'main','visible':True,'bbox':[30,0,295,200]},
                {'element_id':'p','native_role':'p','visible':True,'text':'visible original body','bbox':[30,30,230,120],'parent_id':'main'},
                {'element_id':'icon','native_role':'img','visible':True,'text':'','bbox':[270,160,290,180],'parent_id':'root'}],
            'capture_controls':[{'element_id':'icon','selector':'html:nth-of-type(1) > body:nth-of-type(1) > img:nth-of-type(1)'}],
            'geometry_witnesses':[],'text_blocks':[],'paint_borders':[],'capture_media':[],'capture_images':[]}
        self.after=deepcopy(self.state);self.after['elements'].pop();self.after['capture_controls']=[]
    def png(self,state,extra=None):
        im=Image.new('RGB',(300,200),'white');d=ImageDraw.Draw(im)
        for e in state['elements']:
            if e['native_role']=='img':x0,y0,x1,y1=e['bbox'];d.rectangle((x0,y0,x1-1,y1-1),fill='blue')
        if extra:d.point(extra,fill='red')
        b=BytesIO();im.save(b,format='PNG');return b.getvalue()
    def test_strict_disappearing_widget_bridge_and_negative_boundaries(self):
        def proof(a=None,b=None,**kw):
            a=a or self.state;b=b or self.after
            return terminal_bridge(self.task,a,b,self.png(a),self.png(b),**kw)
        self.assertTrue(proof()['accepted'])
        self.assertFalse(proof(unverified_tail=1)['accepted'])
        self.assertFalse(proof(target_ids=['icon'])['accepted'])
        for field,value in [('bbox',[200,80,220,100]),('parent_id','main'),('native_role','div')]:
            changed=deepcopy(self.state);changed['elements'][-1][field]=value
            self.assertFalse(proof(changed)['accepted'],field)
        changed=deepcopy(self.after);changed['elements'][1]['text']='changed body'
        self.assertFalse(proof(b=changed)['accepted'])
        for point in ((50,50),(269,160),(290,160)):
            self.assertFalse(terminal_bridge(self.task,self.state,self.after,self.png(self.state),self.png(self.after,point))['accepted'])
        changed=deepcopy(self.after);changed['capture_readiness']['images_ready']=False
        self.assertFalse(proof(b=changed)['accepted'])
    def test_new_schema_requires_declared_checks_and_answer(self):
        ps=schema(plan_schema(True,pending_checks=True));self.assertEqual(ps['properties']['checks']['minItems'],1)
        check=ps['properties']['checks']['items']
        Draft202012Validator(check).validate({'field':'new body','evidence_kind':'reading','required_step_indices':[]})
        for kind,indices in [('reading',[0]),('reading',[2]),('actions',[])]:
            with self.assertRaises(ValidationError):Draft202012Validator(check).validate({'field':'required evidence','evidence_kind':kind,'required_step_indices':indices})
        with self.assertRaises(ValueError):validate_plan({'checks':[]})
        with self.assertRaises(ValueError):validate_plan({'checks':[{'field':'click','evidence_kind':'actions','required_step_indices':[]}],'steps':[]})
        cs=schema(choice_schema(True,inherited=True));Draft202012Validator.check_schema(cs)
        with self.assertRaises(ValidationError):Draft202012Validator(cs).validate({'choice':'finish_reading'})
        with self.assertRaises(ValidationError):Draft202012Validator(cs).validate({'choice':'cite:p','reading_answer':{}})
    def test_completion_binds_question_checks_original_read_and_actual_actions(self):
        with TemporaryDirectory() as d:
            root=Path(d);state={'elements':[{'element_id':'a','text':'keyword'}],
                'capture_controls':[{'element_id':'a','href':'https://example.org/wiki/Keyword'}]}
            source=exclusive(root/'state.json',state)
            observations={'initial':{'capture_verified':True,'evidence':{'state':source}},'read':{'capture_verified':True,'evidence':{'state':source}}}
            checks=[{'field':'origin','evidence_kind':'reading','required_step_indices':[]},
                {'field':'keyword visit and return','evidence_kind':'actions','required_step_indices':[1,2]}]
            plan={'goal':'read origin and visit the keyword then return','checks':checks,'steps':[{'action':'scroll'},
                {'action':'click','target':{'text':'keyword','node':'a','observation_id':'initial'}},{'action':'back'}]}
            validate_plan(plan)
            rows=[{'operation_id':str(i),'action':action,'before_observation_id':'initial','after_observation_id':'read',
                'target':{'control_id':'a'}} for i,action in enumerate(('scroll','click','back'))]
            passage={'observation_id':'read','node':'p','quote':'actual new paragraph','operation_id':'0'}
            answer={'working_goal':plan['goal'],'answer':'answer based on original paragraph and actual return',
                'check_answers':[{'check_index':0,'answer':'origin explanation','passages':[{k:passage[k] for k in ('observation_id','node','quote')}],'operation_ids':['0']},
                    {'check_index':1,'answer':'visited and returned','passages':[],'operation_ids':['1','2']}]}
            session=SimpleNamespace(plan_controller=SimpleNamespace(frozen_plan=plan),attempt_id='attempt',binding={'bound':True},
                observation_records=observations,trajectory=rows)
            evidence={'new_visible_body':[passage],'selected_passage':passage,'return_required':False}
            counter=0
            def run(value):
                nonlocal counter
                counter+=1;reply={'attempt_id':'attempt','observation_id':'read','choice':'finish_reading','reading_answer':value}
                session.reading_completion=exclusive(root/f'event-{counter}.json',{'kind':'plan-branch','boundary':session.binding,
                    'response':reply,'provider_reply':deepcopy(reply),'options':[{'choice':'finish_reading'}]})
                return completion(session,evidence)
            self.assertEqual(run(answer)['original_checks'],checks)
            plan['checks'][0]['required_step_indices']=[0]
            with self.assertRaisesRegex(ValueError,'Reading check'):run(answer)
            plan['checks'][0]['required_step_indices']=[]
            wrong=deepcopy(answer);wrong['working_goal']='smaller changed question'
            with self.assertRaises(ValueError):run(wrong)
            wrong=deepcopy(answer);wrong['check_answers'][1].update(passages=wrong['check_answers'][0]['passages'],operation_ids=['0'])
            with self.assertRaisesRegex(ValueError,'REQUIRED_ACTION_NOT_EXECUTED'):run(wrong)
            wrong=deepcopy(answer);wrong['check_answers']=wrong['check_answers'][:1]
            with self.assertRaises(ValueError):run(wrong)
            wrong=deepcopy(answer);wrong['check_answers'][0]['passages'][0]['quote']='invented paragraph'
            with self.assertRaises(ValueError):run(wrong)
            # Same visible label with a different original href cannot substitute.
            other=deepcopy(state);other['capture_controls'][0]['href']='https://example.org/wiki/Other'
            observations['other']={'capture_verified':True,'evidence':{'state':exclusive(root/'other.json',other)}}
            session.trajectory[1]['before_observation_id']='other'
            with self.assertRaisesRegex(ValueError,'REQUIRED_ACTION_NOT_EXECUTED'):run(answer)
    def proposal(self):
        return {'goal':'read new original body','band':'short','short_reason':'one natural reading action',
            'steps':[{'action':'scroll','direction':'down','purpose':'read a new paragraph','expected':{'kind':'scroll_changed'}}],
            'checks':[{'field':'new body explanation','evidence_kind':'reading','required_step_indices':[]}],
            'finish_when':{'kind':'goal_evidence'},'replan_when':'new evidence differs'}
    def test_initial_plan_issues_aggregate_current_bindings_and_required_actions(self):
        from webcollect.direct_completion import initial_plan_issues
        contract={'version':'webcollect-direct-article-reading-1','entry_url':'https://example.org/wiki/A'}
        ob={'observation_id':'current','controls':{'link':{'element':{'visible':True,'text':'keyword'},'binding':{'href':'https://example.org/wiki/B'}}}}
        plan=self.proposal();plan['checks'][0]['required_step_indices']=[0]
        plan['checks'].append({'field':'visit and return','evidence_kind':'actions','required_step_indices':[3,0,1]})
        plan['steps'].append({'action':'click','purpose':'visit keyword','target':{'node':'link','text':'wrong','href':'https://example.org/wiki/C','observation_id':'old'},'expected':{'kind':'document_changed'}})
        plan['steps'].append({'action':'scroll','direction':'down','purpose':'not allowed on other page','expected':{'kind':'scroll_changed'}})
        issues=initial_plan_issues(plan,ob,contract);details='\n'.join(i['detail'] for i in issues)
        for text in ('empty','ordered','Index 3','Index 0','label differs','href differs','original observation only','immediately next'):
            self.assertIn(text,details)
        self.assertEqual(initial_plan_issues(self.proposal(),ob,contract),[])
    def test_first_proposal_feedback_is_bounded_and_unknown_does_not_retry(self):
        import asyncio
        from unittest.mock import patch
        from webcollect.banded_plan import Controller
        from webcollect.react_session import OutcomeUnknown,ReactStop,SessionGLMCallLimit
        task=deepcopy(self.task);task['fragment']['allowed_actions']=['scroll','click','back']
        task['fragment']['session_objective']['objective']['evidence_contract']['entry_url']='https://example.org/wiki/A'
        def make(replies):
            events=[];calls=[];controller=Controller()
            current={'observation_id':'current','controls':{},'visible_text':'body','document_identity':{'nonce':1}}
            session=SimpleNamespace(task=task,current=current,attempt_id='attempt',unknown=False,actual_dispatches=0,
                used={'max_decisions':0},context={},tool_call_ids=set(),page_urls=[],goal_updates=[])
            def budget():
                if len(calls)>=25:raise SessionGLMCallLimit('attempt',25)
            async def choose(prompt):
                calls.append(prompt)
                reply=replies[min(len(calls)-1,len(replies)-1)]
                if isinstance(reply,Exception):raise reply
                return {'name':'submit_plan','tool_call_id':'call'+str(len(calls)),'arguments':deepcopy(reply)}
            session.choose=choose;session._check_request_budget=budget
            session._consume=lambda key:session.used.__setitem__(key,session.used[key]+1)
            session._strip_prompt=lambda p:p
            session.event=lambda kind,**data:events.append({'kind':kind,**data}) or {'event':len(events)}
            controller.prompt=lambda s,options=None:{'attempt_id':'attempt','observation':{'observation_id':'current','rendered_dom':[]},'registered_pages':[],
                'initial_plan_feedback':deepcopy(controller.initial_feedback)}
            return controller,session,calls,events
        invalid=self.proposal();invalid['checks'][0]['required_step_indices']=[0]
        c,s,calls,events=make([invalid,self.proposal()])
        asyncio.run(c.request(s));self.assertFalse(c.submitted);self.assertEqual(s.actual_dispatches,0)
        asyncio.run(c.request(s));self.assertTrue(c.submitted);self.assertEqual(c.frozen_plan['goal'],self.proposal()['goal'])
        self.assertTrue(calls[1]['initial_plan_feedback']['errors']);self.assertEqual(events[1]['kind'],'plan-validation-feedback')
        c,s,calls,events=make([invalid])
        for _ in range(25):asyncio.run(c.request(s))
        with self.assertRaises(SessionGLMCallLimit):asyncio.run(c.request(s))
        self.assertEqual(len(calls),25);self.assertFalse(c.submitted);self.assertEqual(s.actual_dispatches,0)
        c,s,calls,events=make([OutcomeUnknown('original request unresolved')])
        with self.assertRaises(ReactStop):asyncio.run(c.request(s))
        self.assertTrue(s.unknown);self.assertEqual(len(calls),1);self.assertIsNone(c.initial_feedback)

