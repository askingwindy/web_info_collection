"""Evidence-derived, project-bound templates; opt-in controller and append-only library.

No model emulation. The original four host tools, dispatch/UNKNOWN guards,
raw journal, effective-action checks and formal save remain authoritative.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from .agent_feedback import reference
from .batch_core import load_json
from .planning import object_sha256, verify_evidence
from .consumer_templates import (TemplateSession, ResultRegions, Inapplicable,
                                 shown, label, bind_control)
from .react_session import ReactSession

SESSION_WIRING = 'original-four-tool-react'
REQUIRED = {'visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference'}
COMPUTE = re.compile(r'^(?:(?:开始|開始)?(?:计算|計算)(?:税额|稅額|奖金|獎金)?|calculate(?:\s+.+)?|compute(?:\s+.+)?)$', re.I)


class DOM(ResultRegions):
    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        node = next(reversed(self.nodes.values()))
        node['attrs'] = dict(attrs)
        parent = self.stack[-2] if tag not in self.VOID and len(self.stack)>1 else self.stack[-1] if tag in self.VOID and self.stack else None
        tokens = re.split(r'\s+', node['attrs'].get('id','')+' '+node['attrs'].get('class',''))
        node['result'] = node['result'] or any(t.endswith(('-result','-results')) or t in ('result-area','result-tbl') for t in tokens) or bool(parent and parent['result'])

    def handle_data(self,data):
        if any(hidden(n) for n in self.stack):return
        super().handle_data(data)


def hidden(node):
    attrs=node.get('attrs',{})
    return ('hidden' in attrs or attrs.get('aria-hidden')=='true'
            or re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)',attrs.get('style',''),re.I) is not None)


def hidden_path(path,nodes):
    while path in nodes:
        if hidden(nodes[path]):return True
        parent=path.rsplit(' > ',1)[0]
        if parent==path:break
        path=parent
    return False


def result_evidence(state, before_state, html, before_html, *, card_labels=None):
    """A changed submitted result region and same-frame name/value pair.

    Each quoted cell remains a separate exact string. Hidden HTML may reject
    old results; only clipped current tree/PNG nodes supply positive evidence.
    """
    now, old = DOM(html).nodes, DOM(before_html).nodes
    input_numbers={str(v.get('value')).replace(',','') for v in before_state.get('values',[])
                   if re.fullmatch(r'[-+]?\d[\d,.]*',str(v.get('value','')))}
    visible = state.get('visible_text','')
    candidates = []
    for e in state.get('elements',[]):
        b = next((b for b in state.get('capture_controls',[]) if b['element_id']==e['element_id']),{})
        path = b.get('selector'); n = now.get(path); text = label(e)
        if (not n or not n['result'] or n['excluded'] or n['input'] or not text
                or not shown(e,state) or text not in visible or e.get('inputable')): continue
        ancestor = path
        while ancestor in now and now[ancestor]['result']:
            parent = ancestor.rsplit(' > ',1)[0]
            if parent == ancestor or parent not in now or not now[parent]['result']:break
            ancestor = parent
        region = now[ancestor]; prior = old.get(ancestor,{})
        numbers = re.findall(r'[-+]?\d[\d,.]*(?:%|％)?', region['text'])
        if not numbers or numbers == re.findall(r'[-+]?\d[\d,.]*(?:%|％)?',prior.get('text','')):continue
        candidates.append({'element_id':e['element_id'],'selector':path,'region':ancestor,
                           'text':text,'bbox':e['bbox'],'role':e.get('native_role'),
                           'input_echo':bool(re.findall(r'[-+]?\d[\d,.]*',text)) and set(n.replace(',','') for n in re.findall(r'[-+]?\d[\d,.]*',text))<=input_numbers,
                           'numeric_changed':(path not in old or hidden_path(path,old)
                             or re.findall(r'[-+]?\d[\d,.]*(?:%|％)?',n['text']) != re.findall(r'[-+]?\d[\d,.]*(?:%|％)?',old[path]['text']))})
    # Explicit output with both label/unit and number, or aligned table cells.
    proofs=[]
    for a in candidates:
        if a['numeric_changed'] and not a['input_echo'] and re.search(r'\d',a['text']) and re.search(r'[%％€$£元]|[A-Za-z\u4e00-\u9fff]',a['text']):
            if a['role'] not in ('td','th','strong'):
                proofs.append({'quotes':[a['text']],'nodes':[a]})
        if not re.search(r'\d',a['text']):
            for b in candidates:
                if (a['region']==b['region'] and a['bbox'][2]<=b['bbox'][0]+3
                        and abs(a['bbox'][1]-b['bbox'][1])<=5 and b['numeric_changed'] and not b['input_echo'] and re.search(r'\d',b['text'])):
                    proofs.append({'quotes':[a['text'],b['text']],'nodes':[a,b]})
    if card_labels:
        from .goal_evidence import norm, number
        expected_name, expected_unit = map(norm, card_labels)
        groups = {}
        for node in candidates:
            parent = node['selector'].rsplit(' > ', 1)[0]
            groups.setdefault((node['region'], parent), []).append(node)
        for siblings in groups.values():
            if len(siblings) != 3:
                continue
            name, value, unit = sorted(siblings, key=lambda node: node['bbox'][1])
            boxes = [node['bbox'] for node in (name, value, unit)]
            if (expected_name in norm(name['text']) and norm(unit['text']) == expected_unit
                    and number(value['text']) is not None and value['numeric_changed'] and not value['input_echo']
                    and max(b[0] for b in boxes) < min(b[2] for b in boxes)
                    and boxes[0][3] <= boxes[1][1] + 1 and boxes[1][3] <= boxes[2][1] + 1):
                proofs.append({'quotes':[node['text'] for node in (name,value,unit)], 'nodes':[name,value,unit]})
    return proofs


def numeric_controls(state, html, *, strict=True):
    dom=DOM(html).nodes; bindings={b['element_id']:b for b in state.get('capture_controls',[])}
    values={v['element_id']:v for v in state.get('values',[])}
    fields=[];choices=[]
    for e in state.get('elements',[]):
        if not shown(e,state) or not e.get('enabled'):continue
        b=bindings.get(e['element_id'],{});v=values.get(e['element_id'],{})
        attrs=dom.get(b.get('selector'),{}).get('attrs',{})
        if b.get('tag')=='select':
            if strict and (not label(e) or not v.get('display_value') or not v.get('value_visible')):
                raise Inapplicable('CHOICE_DISPLAY_OR_UNIT_UNPROVEN')
            choices.append({'label':label(e),'selector':b['selector'],'display':v.get('display_value'),
                            'value':v.get('value'),'value_visible':v.get('value_visible')})
        if e.get('inputable') and not v.get('readonly'):
            numeric=b.get('input_type')=='number' or (b.get('input_type')=='text' and attrs.get('inputmode') in ('numeric','decimal'))
            if not numeric or not label(e):raise Inapplicable('NON_NUMERIC_OR_UNLABELLED_FIELD')
            fields.append({'label':label(e),'selector':b['selector'],'input_type':b.get('input_type'),
                'inputmode':attrs.get('inputmode'),'old_value':v.get('value'),
                'value_visible':v.get('value_visible'),
                'placeholder':attrs.get('placeholder') if attrs.get('placeholder','!') in state.get('visible_text','') else None,
                'min':attrs.get('min'),'max':attrs.get('max')})
    if not fields or len(fields)>4 or len(set(f['label'] for f in fields))!=len(fields):
        raise Inapplicable('NUMERIC_FIELD_COUNT_OR_ROLE_AMBIGUOUS')
    return fields,choices


def demo_parameter(field):
    """Use current page's numeric example, otherwise keep a visible numeric default.

    No source values, rates, answers or candidate-specific rules are used.
    """
    for value in (field.get('placeholder'),field.get('old_value') if field.get('value_visible') else None):
        if value is not None and re.fullmatch(r'\d+(?:\.\d+)?',str(value)):
            return str(value)
    raise Inapplicable('NO_PAGE_GROUNDED_NUMERIC_EXAMPLE')


def derive_program(operations, fields, submit_index, proof):
    """Abstract verified source order into host primitives; no source values."""
    typed=[o for o in operations[:submit_index] if o['action_type']=='type']
    if not typed:raise ValueError('No input before submit')
    kinds=sorted({(f['input_type'],f.get('inputmode') or '') for f in fields
                  if f['selector'] in {o.get('selector') for o in typed}})
    if not kinds:raise ValueError('Source input roles missing')
    program=[{'op':'fill_numeric','source_input_kinds':[list(k) for k in kinds],
              'source_typed_roles':len({o.get('selector') for o in typed}),
              'repeat':'current_visible_compatible_numeric_roles',
              'source_primitives':[o['action_type'] for o in operations[:submit_index]],
              'generalization':'Repeat the demonstrated numeric role; units are rebound from the current frame.'},
             {'op':'submit_compute','mechanism':operations[submit_index]['action_type'],
              'max_submissions':1,'button_locate_scroll_limit':1}]
    scrolls=sum(o['action_type']=='scroll' for o in operations[submit_index+1:])
    if scrolls:program.append({'op':'scroll_result','limit':scrolls,'skip_if_result_visible':True})
    shape='aligned_cells' if any(len(p['nodes'])==2 for p in proof) else 'named_numeric_output'
    program.append({'op':'verify_result','shape':shape,'changed_since':'before_submission','exact_quotes':True})
    return program


def validate_program(program):
    if not isinstance(program,list) or len(program) not in (3,4):raise Inapplicable('MISSING_OR_INVALID_TEMPLATE_PROGRAM')
    ops=[s.get('op') for s in program]
    if ops not in (['fill_numeric','submit_compute','verify_result'],
                   ['fill_numeric','submit_compute','scroll_result','verify_result']):
        raise Inapplicable('UNKNOWN_OR_OUT_OF_ORDER_TEMPLATE_STEP')
    if (not program[0].get('source_input_kinds') or program[1].get('mechanism')!='click'
            or program[0].get('repeat')!='current_visible_compatible_numeric_roles'
            or program[1].get('max_submissions')!=1 or program[-1].get('shape') not in ('aligned_cells','named_numeric_output')
            or not program[-1].get('exact_quotes') or program[-1].get('changed_since')!='before_submission'):
        raise Inapplicable('UNSUPPORTED_TEMPLATE_STEP_CONSTRAINT')
    limit=program[1].get('button_locate_scroll_limit')
    if type(limit) is not int or not 0<=limit<=1:raise Inapplicable('UNSUPPORTED_BUTTON_LOCATE_CONSTRAINT')
    if len(program)==4 and not 1<=program[2].get('limit',0)<=2:raise Inapplicable('UNSUPPORTED_SOURCE_SCROLL_LIMIT')
    if len(program)==4 and program[2].get('skip_if_result_visible') is not True:raise Inapplicable('UNSUPPORTED_SOURCE_SCROLL_CONSTRAINT')
    return program


def match(template, application_id, state, html, requested_goal=None):
    if (not isinstance(template, dict) or not template.get('template_id')
            or not template.get('application_id') or not template.get('site_host')
            or not template.get('state')):
        raise Inapplicable('TEMPLATE_FIELDS_MISSING')
    program=validate_program(template.get('program'))
    if any(k not in (['text','decimal'],['text','numeric'],['number',''],['number','decimal'],['number','numeric']) for k in program[0]['source_input_kinds']):
        raise Inapplicable('SOURCE_INPUT_KIND_UNSUPPORTED')
    if template['application_id']!=application_id:raise Inapplicable('APPLICATION_MISMATCH')
    if template['state'] not in ('trial','same_site_revalidated'):raise Inapplicable('DRAFT_OR_QC_NOT_PASS')
    if urlsplit(state.get('url','')).hostname!=template['site_host']:raise Inapplicable('SITE_IDENTITY_CHANGED')
    if requested_goal:raise Inapplicable('EXPLICIT_GOAL_REQUIRES_REACT')
    # Only a trusted observation may be passed by the session; pure matcher
    # itself never promotes HTML-only controls to dispatchable controls.
    if re.search('留空|任意两|任意兩|未知量|leave.*blank|solve for',state.get('visible_text',''),re.I):
        raise Inapplicable('SOLVER_SEMANTICS_UNSUPPORTED')
    fields,choices=numeric_controls(state,html,strict=False)
    structure=DOM(html).nodes
    buttons=[n for n in structure.values() if n['tag']=='button' and COMPUTE.fullmatch(n['text'].strip())]
    if len(buttons)!=1:raise Inapplicable('SUBMIT_MECHANISM_NOT_UNIQUE')
    if not any(n['result'] and not n['excluded'] for n in structure.values()):
        raise Inapplicable('NO_EXPLICIT_RESULT_REGION_CONTRACT')
    unresolved=[c for c in choices if not c.get('display') or not c.get('value_visible')]
    for f in fields:
        if not re.search(r'[%％€$£元]|年|月|天|日|人数|份额|份數|份数|years?|months?|days?|count|number|percent|rate',f['label'],re.I):
            raise Inapplicable('PARAMETER_UNIT_OR_ROLE_UNPROVEN')
        f['value']=demo_parameter(f)
    desc='在当前计算器使用首帧的数字示例/可见初值：'+'；'.join(f"{f['label']}={f['value']}" for f in fields)
    if choices:desc+='；不修改首帧选择项：'+'；'.join(c['label'] for c in choices)
    return {'template':template['template_id'],'description':desc+'。执行计算并核对本次提交后可见结果的名称、数值及单位；不切换任务。',
            'fields':fields,'choices':choices,'button_selector':None,'button_label':None,
            'library_template':template,'program':deepcopy(program),
            'unresolved_choices':unresolved,'match_status':'GREY_NEEDS_CHOICE_OBSERVATION' if unresolved else 'HIT'}


def qc_binding(report_path, review_path, queue_path, ledger):
    """Read existing independent jobs; never dispatch, reset or infer package PASS."""
    from quality_inspector.profiles import package_files
    report,review,queue=map(load_json,(report_path,review_path,queue_path))
    with sqlite3.connect(Path(ledger.path).resolve().as_uri()+'?mode=ro',uri=True) as con:
        config=json.loads(con.execute('SELECT config FROM batch_meta WHERE id=1').fetchone()[0])
    if config.get('mode')!='real':raise ValueError('Only original real independent QC can promote a template')
    if package_files(Path(queue['dataset']))!=queue['candidate_package_sha256']:raise ValueError('QC package bytes changed')
    out={}
    for sample in report['samples']:
        sid=sample['sample_id'];records=[r for r in review['records'] if r['sample_id']==sid]
        jobs=[j for j in queue['jobs'] if j['sample_id']==sid]
        if len(records)!=1 or len(jobs)!=1:raise ValueError('QC sample/job binding ambiguous')
        r,j=records[0],jobs[0]
        if (r.get('reviewer') or {}).get('kind')!='ai':raise ValueError('Independent AI review required')
        if any(r[k]!=sample[k] for k in ('annotation_sha256','evidence_sha256')):raise ValueError('QC evidence binding differs')
        for kind in ('visual_job','difference_job'):
            job=ledger.get(j[kind])
            if r['provenance'][kind]!=j[kind] or job['state']!='done':raise ValueError('Independent QC job not settled')
            payload=job.get('payload') or {}
            if isinstance(payload,str):payload=json.loads(payload)
            if payload.get('mode')=='synthetic' or payload.get('synthetic') is True:raise ValueError('Synthetic QC cannot promote a template')
            with sqlite3.connect(Path(ledger.path).resolve().as_uri()+'?mode=ro',uri=True) as con:
                requests=con.execute('SELECT usage,response,request_json,state FROM model_requests WHERE job_id=?',(j[kind],)).fetchall()
            actual=False
            for usage,response,request,state in requests:
                u=json.loads(usage or '{}');response=json.loads(response or '{}');request=json.loads(request or '{}')
                actual |= bool(state=='succeeded' and (request.get('http_dispatch')==1 or (u.get('source')=='provider_response' and u.get('provider_request_id') and 'provider_response' in response)))
            if not actual:raise ValueError('QC has no actual independent provider request evidence')
        if getattr(ledger,'config',{}).get('mode')=='synthetic':raise ValueError('Synthetic ledger cannot promote a template')
        expected={s['step_id'] for s in sample['steps']}
        full=bool(expected) and expected<=set(r['provenance'].get('frames_viewed',[])) and expected<={s['step_id'] for s in r.get('step_observations',[])}
        checks={k:v['status'] for k,v in r['checks'].items()}
        passed=full and REQUIRED<=checks.keys() and all(checks[k]=='PASS' for k in REQUIRED) and sample['status']=='PASS'
        out[sid]={'sample_id':sid,'status':sample['status'],'package_status':report['status'],'full_frames':full,
                  'all_five_pass':passed,'checks':checks,'report':reference(report_path),'review':reference(review_path),
                  'queue':reference(queue_path),'annotation_sha256':sample['annotation_sha256'],
                  'jobs':{k:j[k] for k in ('visual_job','difference_job')},'ledger':str(ledger.path)}
    return out


class TemplateLibrary:
    def __init__(self, path, manifest, pool):
        self.path=Path(path).resolve();self.manifest=reference(manifest);self.pool=Path(pool).resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS templates(template_id TEXT PRIMARY KEY,definition TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS sources(receipt_sha TEXT PRIMARY KEY,template_id TEXT NOT NULL,record TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS qc(receipt_sha TEXT NOT NULL,report_sha TEXT NOT NULL,record TEXT NOT NULL,PRIMARY KEY(receipt_sha,report_sha));''')
            binding=json.dumps({'manifest':self.manifest,'pool':str(self.pool)},sort_keys=True)
            prior=c.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()
            if prior and prior[0]!=binding:raise ValueError('Template library belongs to another project/manifest version')
            c.execute("INSERT OR IGNORE INTO meta VALUES('manifest',?)",(binding,))

    def connect(self):
        from .batch_core import ClosingConnection
        return sqlite3.connect(self.path,timeout=30,factory=ClosingConnection)

    def snapshot(self):
        with self.connect() as c:
            templates=[json.loads(r[0]) for r in c.execute('SELECT definition FROM templates ORDER BY template_id')]
            sources=[json.loads(r[0]) for r in c.execute('SELECT record FROM sources ORDER BY rowid')]
            qcs=[json.loads(r[0]) for r in c.execute('SELECT record FROM qc ORDER BY rowid')]
        latest={q['receipt_sha']:q for q in qcs}
        for t in templates:
            accepted=[s for s in sources if s['template_id']==t['template_id'] and latest.get(s['save_receipt']['sha256'],{}).get('all_five_pass')]
            basis_url=accepted[0]['entry_url'] if accepted else None
            direct=[s for s in sources if s.get('reused_template_id')==t['template_id']
                    and s.get('route')=='template_direct' and s['entry_url']!=basis_url
                    and latest.get(s['save_receipt']['sha256'],{}).get('all_five_pass')]
            t['state']='same_site_revalidated' if accepted and direct else 'trial' if accepted else 'draft'
            t['source_receipts']=[s['save_receipt'] for s in sources if s['template_id']==t['template_id']]
            t['cross_page_validation_receipts']=[s['save_receipt'] for s in direct] if accepted else []
        return {'manifest':self.manifest,'pool':str(self.pool),'templates':templates,'sources':sources,'qc':qcs}

    def learn(self, pool, claim_id, qc=None):
        """Same entry after any formal save, including a new ReAct success."""
        from .candidate_consumer import verified_saved
        from .postprocess import session_record, effective_trajectory
        claim=pool.get_claim(claim_id);saved=verified_saved(claim)
        if pool.path!=self.pool:raise ValueError('Different candidate project')
        if not saved:raise ValueError('Committed formal saved sample required')
        receipt=saved['save_receipt'];raw=Path(receipt['path']).parent/'raw'
        record=session_record(raw);rows=effective_trajectory(record)
        terminal=record['terminal'];ending=terminal.get('collection_ending') or {}
        if (terminal.get('unknown') or ending.get('external_effect_unknown') or ending.get('unverified_tail_dispatches')
                or terminal.get('stop_reason')!='ready'):
            raise ValueError('Unsettled or non-success trajectory cannot teach execution')
        start=record['observations'][rows[0]['before_observation_id']]
        state=load_json(start['state_path']);html=Path(start['evidence']['html']['path']).read_text()
        fields,choices=numeric_controls(state,html,strict=False)
        operations=[load_json(r['raw_step']['path'])['operation'] for r in rows]
        input_ops=[o for o in operations if o['action_type']=='type']
        submits=[(i,o) for i,o in enumerate(operations) if o['action_type']=='click' and COMPUTE.fullmatch(o.get('evidence',{}).get('target_label',''))]
        if not input_ops or len(submits)!=1:raise ValueError('No verified numeric-input/compute trajectory')
        idx,submit=submits[0];baseline=record['observations'][rows[idx]['before_observation_id']]
        if any(o.get('selector') not in {f['selector'] for f in fields} for o in input_ops):
            raise ValueError('Typed operation lacks source numeric role binding')
        if any(o['action_type'] not in ('click','type','scroll') for o in operations):
            raise ValueError('Source has unsupported execution semantics')
        if any(o['action_type']=='type' for o in operations[idx:]):
            raise ValueError('Source parameters changed after submission')
        end=record['observations'][terminal['final_observation_id']]
        proof=result_evidence(load_json(end['state_path']),load_json(baseline['state_path']),
            Path(end['evidence']['html']['path']).read_text(),Path(baseline['evidence']['html']['path']).read_text())
        if not proof:raise ValueError('Submitted changed result lacks visible name/value evidence')
        # Parameter values, page selectors and source URL belong only to provenance.
        # The reusable program contains roles, not the source answer or coordinates.
        with pool.pool.connect() as c:
            aid=c.execute('SELECT application_id FROM data_candidates WHERE candidate_id=?',(claim['candidate_id'],)).fetchone()[0]
        definition={'application_id':aid,
            'site_host':urlsplit(state['url']).hostname,'program':derive_program(operations,fields,idx,proof),
            'parameter_roles':[{'numeric_kind':f['input_type'],'inputmode':f.get('inputmode'),'source_role_ordinal':i} for i,f in enumerate(fields,1)],
            'submit_mechanism':'unique_visible_compute_button; at_most_one_submission',
            'result_rule':'visible_numeric_node_changed_or_explicitly_newly_shown; no_parameter_echo; same_frame_exact_name_value_quotes',
            'fallback_conditions':['ambiguous_goal_or_units','incompatible_roles','untrusted_frame','missing_button_after_one_scroll','mismatch','unknown_never_replay'],
            'scope_limit':'Program order, input kinds, submission and result shape are derived from the verified source; repetition and button locating are bounded engineering generalizations.'}
        definition['template_id']='learned-'+object_sha256(definition)[:24]
        source={**saved,'template_id':definition['template_id'],'claim_id':claim_id,
            'candidate_id':claim['candidate_id'],'candidate_version':claim['version'],'candidate':claim['snapshot'],
            'entry_url':claim['snapshot']['entry_url'],'raw_receipt':reference(raw/'raw-receipt.json'),
            'original_actions':[r['raw_step'] for r in rows], 'first_frame':start['evidence'],
            'roles_observed':fields,'choices_observed':choices,'submitted_result_evidence':proof,
            'extraction_model_http':0,'extraction_tokens':0,'extraction_method':'deterministic_verified_trace_abstraction'}
        routes=sorted(raw.glob('*-template-route-summary.json'))
        source['route']=load_json(routes[-1])['route'] if routes else 'original_react'
        source['reused_template_id']=load_json(routes[-1]).get('template') if routes else None
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO templates VALUES(?,?)',(definition['template_id'],json.dumps(definition,ensure_ascii=False,sort_keys=True)))
            c.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?)',(receipt['sha256'],definition['template_id'],json.dumps(source,ensure_ascii=False,sort_keys=True)))
        if qc:self.apply_qc(receipt['sha256'],qc)
        return source

    def apply_qc(self, receipt_sha, qc):
        """Accept a qc_binding() result only after verifying the same annotation."""
        verify_evidence([qc[k] for k in ('report','review','queue')])
        class OriginalJobs:
            path=Path(qc['ledger'])
            def get(self,jid):
                with sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True) as con:
                    row=con.execute('SELECT state,payload FROM jobs WHERE id=?',(jid,)).fetchone()
                return {'state':row[0],'payload':json.loads(row[1])} if row else {}
        verified=qc_binding(qc['report']['path'],qc['review']['path'],qc['queue']['path'],OriginalJobs())[qc['sample_id']]
        if verified!=qc:raise ValueError('QC projection differs from original independent evidence')
        with self.connect() as c:
            row=c.execute('SELECT record FROM sources WHERE receipt_sha=?',(receipt_sha,)).fetchone()
            if not row:raise ValueError('QC cannot bind an unknown source')
            source=json.loads(row[0]);saved=load_json(source['save_receipt']['path'])
            if source['sample_id']!=qc['sample_id'] or saved['sample_files_sha256']['annotation.json']!=qc['annotation_sha256']:
                raise ValueError('QC is for a different saved sample')
            record={**qc,'receipt_sha':receipt_sha}
            c.execute('INSERT OR IGNORE INTO qc VALUES(?,?,?)',(receipt_sha,qc['report']['sha256'],json.dumps(record,ensure_ascii=False,sort_keys=True)))


class LearningSession(TemplateSession):
    library_snapshot=None

    def __init__(self,*args,**kwargs):
        ReactSession.__init__(self,*args,**kwargs)
        if self.plan_controller is not None:
            raise ValueError('Template learning requires explicit original four-tool ReAct wiring')
        self.experiment={'automatic_library_lookup':True};self.plan=None;self.template_disabled=False
        self.reactive_rounds=0;self.template_dispatches=0;self.template_tools=0;self.goal_initialized=False
        self.filled=set();self.calculated=False;self.lookup_done=False;self.library=deepcopy(self.library_snapshot)
        self.program_index=0;self.choice_observed=set();self.result_scrolls=0
        self.event('template-library-snapshot',snapshot=self.library,sha256=object_sha256(self.library))

    async def _round_impl(self):
        if not self.lookup_done:
            self.lookup_done=True;reasons=[];matches=[]
            cb=self.task.get('candidate_binding') or {}
            # Claim application comes from the original bound application registry,
            # not a cohort family or an inferred URL label.
            from .candidate_contract import validate_task_binding
            binding=validate_task_binding(self.task)
            import sqlite3
            con=sqlite3.connect(Path(self.library['pool']).as_uri()+'?mode=ro',uri=True)
            try:
                row=con.execute('SELECT application_id FROM data_candidates WHERE candidate_id=?',(binding['candidate_id'],)).fetchone()
                aid=row[0] if row else None
            finally:con.close()
            if not self.current.get('capture_verified') or not self.current.get('document_identity'):reasons.append('UNTRUSTED_FIRST_FRAME')
            else:
                for t in self.library['templates']:
                    try:matches.append(match(t,aid,self.state_now(),self.current['html'],self.requested_goal))
                    except Inapplicable as exc:reasons.append(str(exc))
            self.event('template-library-lookup',candidate_id=cb.get('candidate_id'),application_id=aid,
                library_sha256=object_sha256(self.library),static_matches=len(matches),rejections=reasons)
            if len(matches)==1:
                self.plan=matches[0];self.working_goal=self.plan['description']
                update={'description':self.working_goal,'basis_observation_id':self.current['observation_id'],
                        'reason':'原 claim 应用/原目标与可信首帧检索参数化模板'}
                self.goal_updates.append({**update,'applied_at_decision':0})
                self.event('template-library-hit' if self.plan['match_status']=='HIT' else 'template-library-grey',template=self.plan['template'],plan=self.plan,update=update)
            else:self.fallback('NO_UNAMBIGUOUS_LIBRARY_MATCH:'+','.join(reasons))
        if self.template_disabled:
            self.reactive_rounds+=1;return await ReactSession._round_impl(self)
        self._check_request_budget()
        try:
            self.template_tools+=1
            if self.template_tools>24:raise Inapplicable('TEMPLATE_TOOL_BOUND')
            return await self.calculator_round()
        except Inapplicable as exc:self.fallback(str(exc))

    async def calculator_round(self):
        program=validate_program(self.plan['program']);step=program[self.program_index]
        state=self.state_now();op=step['op']
        if op in ('scroll_result','verify_result'):
            baseline={**self.calculation_before,'values':self.calculation_before.get('values',[])+[{'value':f['value']} for f in self.plan['fields']]}
            proof=result_evidence(state,baseline,self.current['html'],self.calculation_before_html)
            shape=program[-1]['shape']
            proof=[p for p in proof if (len(p['nodes'])==2)==(shape=='aligned_cells')]
            if proof:
                if op=='scroll_result':self.program_index+=1;return
                return await self.close_visible('本次提交后可见结果：'+'；'.join('、'.join(p['quotes']) for p in proof[:3]),
                    {'result_evidence':proof,'parameters':self.plan['fields'],'submitted_once':True,'program_step':self.program_index})
            if op=='scroll_result' and self.result_scrolls<step['limit']:
                self.result_scrolls+=1;return await self.scroll_to('定位本次提交后的计算结果')
            raise Inapplicable('SUBMITTED_RESULT_NAME_VALUE_NOT_VISIBLE')
        if op=='fill_numeric':
            # Unchanged choices can stay untouched. Before any edit, unresolved
            # display evidence gets one original focused observe, never a hidden
            # HTML-to-visible-value conversion or automatic select action.
            for choice in self.plan['unresolved_choices']:
                if choice['selector'] not in self.choice_observed:
                    self.choice_observed.add(choice['selector'])
                    c=bind_control(self.current,choice['selector'])
                    await self.host_tool('observe',{'focus_control_id':c['binding']['element_id']})
                    return
                c=bind_control(self.current,choice['selector']);v=c.get('value') or {}
                if not v.get('display_value') or not v.get('value_visible'):
                    raise Inapplicable('CHOICE_DISPLAY_STILL_UNPROVEN_AFTER_OBSERVE')
            for choice in self.plan['choices']:
                c=bind_control(self.current,choice['selector'])
                if label(c.get('element',{}))!=choice['label'] or (c.get('value') or {}).get('value')!=choice['value']:
                    raise Inapplicable('UNIT_OR_CHOICE_CHANGED')
            for f in self.plan['fields']:
                control=bind_control(self.current,f['selector']);value=(control.get('value') or {}).get('value')
                if label(control.get('element',{}))!=f['label'] or control['binding'].get('input_type')!=f['input_type']:
                    raise Inapplicable('FIELD_IDENTITY_CHANGED')
                if f['selector'] in self.filled:
                    if str(value)!=f['value']:raise Inapplicable('FILLED_PARAMETER_CHANGED')
                    continue
                if str(value)==f['value']:self.filled.add(f['selector']);continue
                if await self.act_control(f['selector'],'set_value',f"填写{f['label']}={f['value']}",value=f['value']):
                    if str((bind_control(self.current,f['selector']).get('value') or {}).get('value'))!=f['value']:
                        raise Inapplicable('PARAMETER_NOT_CONFIRMED')
                    self.filled.add(f['selector'])
                return
            self.parameter_document=deepcopy(self.current.get('document_identity'));self.program_index+=1;return
        if op=='submit_compute':
            if self.calculated:raise Inapplicable('ALREADY_SUBMITTED_NEVER_REPLAY')
            if self.current.get('document_identity')!=self.parameter_document:raise Inapplicable('DOCUMENT_CHANGED_AFTER_PARAMETERS')
            controls=[c for c in self.current['controls'].values() if c['binding'].get('tag')=='button'
                      and shown(c.get('element',{}),state) and COMPUTE.fullmatch(label(c.get('element',{})))]
            if len(controls)!=1:
                if not controls and getattr(self,'button_scrolls',0)<step['button_locate_scroll_limit']:
                    self.button_scrolls=getattr(self,'button_scrolls',0)+1
                    return await self.scroll_to('定位当前表单的计算按钮')
                raise Inapplicable('COMPUTE_BUTTON_NOT_UNIQUE_VISIBLE')
            c=controls[0];self.plan.update(button_selector=c['binding']['selector'],button_label=label(c['element']))
            self.calculation_before=state;self.calculation_before_html=self.current['html']
            if await self.act_control(self.plan['button_selector'],'click','按本次固定参数计算并查看结果'):
                self.calculated=True;self.program_index+=1

    async def scroll_to(self,goal):
        if 'scroll' not in self.current['page_actions']:raise Inapplicable('NO_PROVEN_PAGE_SCROLL')
        return await self.host_tool('act',{'observation_id':self.current['observation_id'],
            'step':{'action':'scroll','direction':'down','goal':goal,'expected':'显示当前任务控件或本次提交后的可见结果'}})


@contextmanager
def enabled(library):
    # 策略1完全冻结：学习适配器（替换策略1会话）拒绝启用，纵深防御。
    from .collection_strategy import Strategy1Forbidden
    raise Strategy1Forbidden()
    from . import react_session
    old=react_session.ReactSession
    old_build=react_session.build_url_task
    if old is not ReactSession:raise RuntimeError('Another session adapter is active')
    LearningSession.library_snapshot=library.snapshot()
    react_session.ReactSession=LearningSession
    def original_four_tool_task(*args,**kwargs):
        # The shared candidate generator may opt into another experiment's
        # planner. This controller explicitly chooses the original four tools
        # BEFORE spec/task identity is constructed, and restores the builder.
        kwargs['plan_protocol']=None
        return old_build(*args,**kwargs)
    react_session.build_url_task=original_four_tool_task
    try:yield
    finally:
        react_session.ReactSession=old;react_session.build_url_task=old_build;LearningSession.library_snapshot=None
