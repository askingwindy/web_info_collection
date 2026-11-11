"""Explicit original search-failure facts; never effective steps or delivery.

Only a sealed click/type/Enter search whose exact diagnostic was reviewed may
release its own closed attempt's occupancy. No URL or synchronous post-state is
invented. The original UNKNOWN and all outcome fields remain unchanged.
"""
import base64
import hashlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit
from .batch_core import load_json,file_sha
from .planning import verify_evidence,object_sha256

VERSION='readonly-search-capture-audit'
ACTION='account_original_readonly_search_capture_failure'

class _Forms(HTMLParser):
    def __init__(self):super().__init__();self.forms=[];self.current=None
    def handle_starttag(self,tag,attrs):
        if tag=='form':self.current={'attributes':dict(attrs),'inputs':[]};self.forms.append(self.current)
        elif tag=='input' and self.current is not None:self.current['inputs'].append(dict(attrs))
    def handle_endtag(self,tag):
        if tag=='form':self.current=None

def search_capture_audit(raw_root,authorization):
    from .postprocess import session_record,_observation_state
    from .react_protocol import atomic_effect,RULE_VERSION
    from .candidate_contract import validate_task_binding
    raw=Path(raw_root).resolve();verify_evidence([authorization]);allowed=load_json(authorization['path'])
    def ref(p):return {'path':str(p.resolve()),'sha256':file_sha(p)}
    if allowed.get('action')!=ACTION or allowed.get('raw_receipt')!=ref(raw/'raw-receipt.json'):
        raise ValueError('Exact original search capture authorization required')
    record=session_record(raw,allow_unknown_for_prefix=True);terminal=record['terminal'];binding=validate_task_binding(record['task'])
    aid=record['boundary'].get('attempt_id')
    if (not aid or allowed.get('attempt_id')!=aid or allowed.get('claim_id')!=binding['claim_id']
            or allowed.get('candidate_id')!=binding['candidate_id'] or allowed.get('goal_completion')!='NOT_CLAIMED'
            or allowed.get('allow_delivery') is not False or allowed.get('preserve_original_unknown') is not True):
        raise ValueError('Search authorization differs from original attempt/claim/candidate')
    if ({p.relative_to(raw).as_posix() for p in raw.rglob('*') if p.is_file()} != set(record['receipt']['files_sha256'])|{'raw-receipt.json'}
            or terminal.get('unknown') is not True or terminal.get('actual_actions')!=3
            or terminal.get('effective_steps')!=2 or len(record['trajectory'])!=2):
        raise ValueError('Search audit requires exact sealed three-dispatch/two-verified original chain')
    failure_ref=ref(raw.parent/'failure.json');failure=load_json(failure_ref['path'])
    if (failure.get('attempt_id')!=aid or failure.get('failure_class')!='interrupted'
            or failure.get('error')!='react_raw_ending_pending:CAPTURE_AFTER_ACTION_UNVERIFIED: Reading region not fully loaded'):
        raise ValueError('Only original post-search loading capture failure is covered')
    businesses=sorted(raw.glob('*-business-attempt.json'));intents=sorted(raw.glob('*-dispatch-intent.json'))
    rejects=list(raw.glob('*-capture-rejected.json'));step_paths=set((raw.parent/'action-attempts').glob('*.json'))
    if len(businesses)!=3 or len(intents)!=3 or len(rejects)!=1 or len(step_paths)!=3:
        raise ValueError('Unmatched or additional original browser dispatch')
    steps=[];sources=[];refs=[]
    for index,(business_path,intent_path) in enumerate(zip(businesses,intents)):
        business=load_json(business_path);intent=load_json(intent_path);raw_refs=business.get('raw_steps',[])
        if len(raw_refs)!=1:raise ValueError('Exactly one primitive per original search business step required')
        verify_evidence(raw_refs);step=load_json(raw_refs[0]['path']);operation=step.get('operation',{});refs+=raw_refs
        before_id=step.get('react',{}).get('before_observation_id');source=_observation_state(record,before_id)
        if (Path(raw_refs[0]['path']) not in step_paths or step.get('controller_dispatch')!=ref(intent_path)
                or operation!=intent.get('operation') or step.get('state')!=source
                or operation.get('evidence',{}).get('state_sha256')!=object_sha256(source)
                or step.get('dispatched') is not True or step.get('action_executed') is not True
                or step.get('phase')!='post_dispatch' or step.get('execution_error')
                or business.get('actual_dispatches_delta')!=1
                or operation.get('action_type')!=('click','type','hotkey')[index]):
            raise ValueError('Original search primitive/dispatch/state binding differs')
        if index<2:
            row=record['trajectory'][index];after_id=step.get('react',{}).get('after_observation_id')
            if (row.get('raw_step')!=raw_refs[0] or row.get('dispatch')!=ref(intent_path)
                    or row.get('before_observation_id')!=before_id or row.get('after_observation_id')!=after_id
                    or step.get('postconditions_checked') is not True or business.get('outcome')!='VERIFIED'
                    or business.get('effective_steps_delta')!=1):raise ValueError('Search prefix is not originally verified')
            effect=atomic_effect(source,_observation_state(record,after_id),operation['action_type'],operation['arguments'],
                operation.get('evidence',{}).get('anchor_element_id') or operation.get('evidence',{}).get('focused_element_id'),
                rule_version=record['task']['fragment'].get('effective_action_rule',RULE_VERSION))
            if not effect['verified']:raise ValueError('Original search prefix effect is not reproducible')
        elif (business.get('outcome')!='EFFECT_UNKNOWN' or business.get('effective_steps_delta')!=0
                or step.get('postconditions_checked') or step.get('react',{}).get('after_observation_id')
                or operation.get('arguments',{}).get('keys')!=['enter']):
            raise ValueError('Tail must remain the original unverified Enter, not another operation')
        steps.append(step);sources.append(source)
    if len({r['path'] for r in refs})!=3:raise ValueError('Original raw steps are not unique')
    query=allowed.get('query')
    if not isinstance(query,str) or not query.strip() or steps[1]['operation']['arguments'].get('text')!=query:
        raise ValueError('Original typed search query differs from reviewed authorization')
    first_node=steps[0]['operation']['evidence'].get('anchor_element_id')
    first_control=next((c for c in sources[0]['capture_controls'] if c['element_id']==first_node),{})
    if first_control.get('input_type')!='search':raise ValueError('First click is not the original search input')
    source=sources[-1];focused=[v for v in source['values'] if v.get('focused')]
    if len(focused)!=1 or focused[0].get('value')!=query or focused[0].get('value_visible') is not True:
        raise ValueError('Enter lacks the uniquely focused original visible query')
    node=focused[0]['element_id'];control=next((c for c in source['capture_controls'] if c['element_id']==node),{})
    typed_node=steps[1]['operation']['evidence'].get('anchor_element_id') or steps[1]['operation']['evidence'].get('focused_element_id')
    if (node!=typed_node or control.get('input_type')!='search' or any(s['url']!=source['url'] or s['document_identity']!=source['document_identity'] for s in sources)):
        raise ValueError('Search sequence changed field, document or application before Enter')
    html_ref=record['observations'][steps[-1]['react']['before_observation_id']]['evidence']['html'];verify_evidence([html_ref])
    parser=_Forms();parser.feed(Path(html_ref['path']).read_text());fi=control.get('form_index')
    if type(fi)is not int or fi<0 or fi>=len(parser.forms):raise ValueError('Original search form is missing')
    form=parser.forms[fi];attrs=form['attributes'];url=urljoin(source['url'],attrs.get('action',''))
    if (attrs.get('method','get').lower()!='get' or urlsplit(url).scheme not in ('http','https')
            or urlsplit(url).netloc!=urlsplit(source['url']).netloc or attrs.get('target') not in (None,'','_self')
            or form!=allowed.get('reviewed_form') or html_ref!=allowed.get('search_html')
            or not any(i.get('type')=='search' and i.get('name') for i in form['inputs'])
            or any(i.get('type','text').lower() in ('password','file') for i in form['inputs'])):
        raise ValueError('Reviewed same-origin GET search form binding differs')
    rejection_event=load_json(rejects[0]);rejection_ref=rejection_event.get('evidence');verify_evidence([rejection_ref]);rejection=load_json(rejection_ref['path']);diag=rejection.get('diagnostic',{})
    if (Path(rejection_ref['path']).parent!=raw or rejection.get('reason')!='Reading region not fully loaded'
            or rejection.get('after_dispatch') is not True or rejection.get('actual_actions')!=3
            or rejection.get('effective_steps')!=2 or rejection.get('accepted_as_formal_frame') is not False
            or diag.get('schema_version') not in ('capture-exception', 'webcollect-capture-exception-1') or diag.get('attempts')):
        raise ValueError('Original loading rejection diagnostic differs')
    png=base64.b64decode(diag['diagnostic_png_base64'],validate=True);png_sha=hashlib.sha256(png).hexdigest()
    if (allowed.get('rejected_capture')!=rejection_ref or allowed.get('diagnostic_png_sha256')!=png_sha
            or allowed.get('reviewed_visible_title')!=query or allowed.get('visual_review_basis')!='original_diagnostic_image'):
        raise ValueError('Exact original diagnostic visual assessment required')
    return {'schema_version':VERSION,'attempt_id':aid,'claim_id':binding['claim_id'],'candidate_id':binding['candidate_id'],
        'authorization':authorization,'raw_receipt':ref(raw/'raw-receipt.json'),'original_failure':failure_ref,
        'dispatches':[ref(p) for p in intents],'raw_steps':refs,'rejected_capture':rejection_ref,
        'search_html':html_ref,'query':query,'reviewed_form':form,'form_method_semantics':'GET',
        'actual_GET_navigation_request_receipt_available':False,'exact_landing_url_available':False,
        'diagnostic_png_sha256':png_sha,'accounted_dispatches':3,'original_effective_steps':2,
        'fact':'Enter dispatched to the verified search input; reviewed diagnostic shows the article; capture evidence incomplete',
        'original_capture_accepted':False,'source_unknown_retained':True,'deliverable':False,'goal_completion':'NOT_CLAIMED'}
