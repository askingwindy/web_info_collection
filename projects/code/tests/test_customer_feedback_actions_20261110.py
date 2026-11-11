"""Small action-contract fixtures for the single related integration run.

No live requests or production ledger are opened by these cases.
"""
from copy import deepcopy
import pytest
from webcollect.plan_protocol import PLAN_PROTOCOL
from webcollect.banded_plan import (
    bind_reply_scope, plan_schema,
    strip_v13_wire, validate_plan,
)
V12_VERSION = 'webcollect-conditional-plan-12'  # historical literal used only as a mismatched protocol
V13_VERSION = PLAN_PROTOCOL
from webcollect.agent_controller import compile_step
from webcollect.react_protocol import atomic_effect


def mixed_plan():
    target={'text':'原目标控件'}
    expected={'kind':'visible_text','text':'业务状态'}
    rows=[{'action':action,'target':deepcopy(target),'purpose':'操作页面已有业务控件',
           'expected':deepcopy(expected)} for action in ('click','double_click','right_click','drag')]
    rows[-1]['end_target']={'text':'已观察目标区域'}
    rows.insert(1,{'action':'wait','duration_ms':50,'purpose':'等待页面已触发的加载',
                   'expected':deepcopy(expected)})
    rows.append({'action':'scroll','direction':'down','purpose':'查看原目标结果区域',
                 'expected':{'kind':'scroll_changed'}})
    for step in rows:
        step['rationale']='按原目标规划，此步骤用于核对必要的页面状态。'
        step['expected_result']='操作后出现该步骤预期的可见变化，便于继续核对原目标。'
    return {'goal':'核对页面原有业务状态','band':'long','steps':rows,
            'checks':[{'field':'业务状态','page':'p0','region':'正文','visible_text':'业务状态'}],
            'finish_when':deepcopy(expected)}


def prompt(protocol=V13_VERSION):
    return {'protocol':protocol,'attempt_id':'a','phase':'first_plan',
            'observation':{'observation_id':'o','rendered_dom':[]},
            'registered_pages':[{'page_id':'p0','url':'https://example.test/'}]}


def test_mixed_plan_derives_band_and_wait_is_zero():
    plan=bind_reply_scope(mixed_plan(),prompt())
    assert plan['band']=='five'
    actions=[step['action'] for step in plan['steps']]
    validate_plan(plan,'a','o',actions,max_steps=10,ordinary_minimum=True,extended_actions=True)
    shorter=deepcopy(plan);shorter['steps'].pop()
    with pytest.raises(ValueError,match='FIVE_TO_TEN'):
        validate_plan(shorter,'a','o',actions,max_steps=10,ordinary_minimum=True,extended_actions=True)
    with pytest.raises(ValueError,match='PLAN_BAND_CONFLICT'):
        bind_reply_scope({**mixed_plan(),'band':'five'},prompt(V12_VERSION))


def test_new_wire_omits_host_fields_and_offers_real_actions():
    wire=strip_v13_wire(plan_schema(wire=True,max_steps=10),wiki=True)
    assert 'band' not in wire['properties']
    assert 'finish_when' not in wire['properties']
    variants=wire['properties']['steps']['items']['oneOf']
    assert {'double_click','right_click','drag','wait'} <= {
        row['properties']['action']['const'] for row in variants}


def test_drag_requires_current_endpoints_and_real_target_effect():
    controls={'source':{'actions':{'drag':{'status':'PROVEN'}},
                        'element':{'visible':True},'binding':{'selector':'#source'}},
              'dest':{'element':{'visible':True},'binding':{'selector':'#dest'}}}
    task={'fragment':{'allowed_actions':['drag']}}
    step={'action':'drag','control_id':'source','end_control_id':'dest',
          'goal':'将现有项目拖至指定区域','expected':'项目位置改变'}
    compiled=compile_step(task,[],step,{'controls':controls})
    assert compiled[0]['end_control_id']=='dest'
    with pytest.raises(ValueError,match='destination'):
        compile_step(task,[],{**step,'end_control_id':'absent'},{'controls':controls})
    before={'document_identity':{'id':'same'},'elements':[
        {'element_id':'source','bbox':[0,0,20,20],'parent_id':'a','state':'default'}]}
    after=deepcopy(before);after['elements'][0]['bbox']=[100,0,120,20]
    # Legacy effect rule omits dynamic-region fixture requirements; drag had
    # no archived controller path, and this checks only action-specific effects.
    effect=atomic_effect(before,after,'drag',{},'source',rule_version='fixture')
    assert effect['verified'] and 'target.position' in effect['fields']
    assert not atomic_effect(before,before,'wait',{},'source',rule_version='fixture')['verified']
