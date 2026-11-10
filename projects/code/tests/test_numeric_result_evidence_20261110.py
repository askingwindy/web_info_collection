"""Integration suite includes these cases; no live browser/model required."""
import json
from types import SimpleNamespace

import pytest

from webcollect.numeric_result_evidence import VERSION, match_result
from webcollect.plan_evidence import facts


@pytest.mark.parametrize('expected,observed', [
    ('约66.7%', '66.666667%'),
    ('约66.7%', '毛利率：66.666667%'),
    ('１，０００．００元', '1000人民币元'),
    ('1000 USD', '$1,000'),
    ('2公斤', '2千克'),
])
def test_normalized_result(expected, observed):
    result = match_result(expected, observed, field='毛利率', result_bound=True)
    assert result and result['observed_visible_text'] == observed


@pytest.mark.parametrize('expected,observed', [
    ('约66.7%', '66.5%'), ('约66.7%', '166.7%'),
    ('66.7%', '66.666667%'), ('约66.7%', '66.666667元'),
    ('约66.7%', '66.666667'), ('约66.7%', '输入66.666667%'),
    ('约66.7%', '66.666667% / 50%'), ('约66.7%', '66.666667未知单位'),
    ('$', '$'), ('结果', '结果'), ('1000元', '1,00元'),
])
def test_reject_wrong_or_ambiguous(expected, observed):
    assert match_result(expected, observed, field='毛利率', result_bound=True) is None


def test_source_preconditions():
    assert match_result('约66.7%', '66.666667%', field='毛利率', result_bound=False) is None
    assert match_result('约66.7%', '66.666667%', field='毛利率', result_bound=True, input_node=True) is None


def session(tmp_path, *, policy=True, url='https://example.test/calc', role='output'):
    state = {'url': url, 'document_identity':'doc', 'elements':[
        {'element_id':'n1','visible':True,'native_role':role,'text':'66.666667%'}],
        'values':[], 'capture_controls':[]}
    path = tmp_path / 'state.json'
    path.write_text(json.dumps(state))
    return SimpleNamespace(task={'fragment':{'ending_policy':'webcollect-five-ten-effective-ending-5',
            **({'numeric_result_evidence_policy':VERSION} if policy else {})}},
        requested_goal='毛利率',working_goal='毛利率',trajectory=[],
        observation_records={'o1':{'capture_verified':True,'evidence':{'state':{'path':str(path)},'image':{}}}})


def test_facts_keeps_page_region_and_legacy(tmp_path):
    plan = {'checks':[{'field':'毛利率','page':'p0','region':'结果区','visible_text':'约66.7%'}]}
    s = session(tmp_path)
    result = facts(s,plan,page_urls={'p0':'https://example.test/calc'})
    assert result['checks'][0]['status'] == 'VERIFIED'
    assert result['checks'][0]['observed_visible_text'] == '66.666667%'
    assert facts(s,plan,page_urls={'p0':'https://elsewhere.test/'})['verified'] == 0
    assert facts(session(tmp_path,role='input'),plan,page_urls={'p0':'https://example.test/calc'})['verified'] == 0
    assert facts(session(tmp_path,policy=False),plan,page_urls={'p0':'https://example.test/calc'})['verified'] == 0
