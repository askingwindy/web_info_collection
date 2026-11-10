"""Result-source integration cases for the single authorized integration run."""
import json
from copy import deepcopy
from types import SimpleNamespace

from webcollect.numeric_result_evidence import match_result
from webcollect.plan_evidence import facts
from webcollect.result_execution import VERSION, page_feedback


def _session(tmp_path, *, static=False, invalid=False, same=False):
    def state(result):
        elements=[{'element_id':'input','native_role':'input','text':'','visible':True,'inputable':True},
                  {'element_id':'submit','native_role':'button','text':'计算','visible':True,'clickable':True}]
        if result is not None:elements.append({'element_id':'result','native_role':'td' if static else 'output','text':result,'visible':True})
        controls=[{'element_id':'input','form_selector':'form:1','selector':'form:1 > input:1'},
                  {'element_id':'submit','form_selector':'form:1','selector':'form:1 > button:1','input_type':'submit'},
                  {'element_id':'result','form_selector':'form:1','selector':'form:1 > table:1 > td:1' if static else 'form:1 > output:1','result_region_selector':'form:1 > table:1' if static else 'form:1 > output:1'}]
        if invalid:controls[0]['validation_message']='请输入有效数字'
        return {'url':'https://www.muxtly.com/calc','document_identity':'d1','visible_text':result or '',
                'elements':elements,'capture_controls':controls,'values':[]}
    observations={}
    for i,result in enumerate(['62,500.00' if static or same else None,'62,500.00' if static or same else None,'62,500.00']):
        st=state(result);path=tmp_path/f'o{i}.json';path.write_text(json.dumps(st))
        observations[f'o{i}']={'url':st['url'],'capture_verified':True,'evidence':{'state':{'path':str(path)},'image':{}}}
    trajectory=[{'operation_id':'input1','action':'type','target':{'control_id':'input'},'arguments':{'text':'50000'},
                 'before_observation_id':'o0','after_observation_id':'o1','effective':True},
                {'operation_id':'submit1','action':'click','target':{'control_id':'submit'},'arguments':{},
                 'before_observation_id':'o1','after_observation_id':'o2','effective':True}]
    return SimpleNamespace(task={'fragment':{'result_execution_policy':VERSION,'numeric_result_evidence_policy':'webcollect-numeric-result-evidence-1',
             'ending_policy':'webcollect-five-ten-effective-ending-5'}},requested_goal='计算生活费',working_goal='计算生活费',
             trajectory=trajectory,observation_records=observations)


def _facts(s):
    return facts(s,{'checks':[{'field':'生活费','page':'p0','region':'结果区','visible_text':'62500'}]},
                 page_urls={'p0':'https://www.muxtly.com/calc'})


def test_real_submission_and_same_result_are_allowed(tmp_path):
    for same in (False,True):
        result=_facts(_session(tmp_path,same=same))
        assert result['business_goal_status']=='VERIFIED'
        assert result['checks'][0]['evidence'][0]['result_execution_binding']['submission']['operation_id']=='submit1'


def test_static_table_missing_submission_and_validation_are_rejected(tmp_path):
    assert _facts(_session(tmp_path,static=True))['verified']==0
    assert _facts(_session(tmp_path,invalid=True))['verified']==0
    s=_session(tmp_path);s.trajectory.pop()
    assert _facts(s)['verified']==0


def test_literal_escapes_only_reject_critical_ui():
    state={'elements':[{'element_id':'code','visible':True,'native_role':'pre','text':r'const x="\u4e2d";'},
                       {'element_id':'button','visible':True,'native_role':'button','text':r'\u8ba1\u7b97','clickable':True}]}
    assert [row['node'] for row in page_feedback(state)['unreadable_critical_ui']]==['button']


def test_numeric_formatting_keeps_units_and_value():
    assert match_result('62500','62,500.00',field='',result_bound=True)
    assert match_result('62500','62,500.01',field='',result_bound=True) is None


def test_required_checks_include_missing_execution_binding():
    from webcollect.plan_evidence import unverified_required_checks
    checks={'checks':[{'field':'静态标签','status':'VERIFIED'}]}
    assert unverified_required_checks(checks)==[]
    checks['result_execution_status']='UNVERIFIED'
    missing=unverified_required_checks(checks)
    assert len(missing)==1 and missing[0]['binding']=='result_execution_status'
