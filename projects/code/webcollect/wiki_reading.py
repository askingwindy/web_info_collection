"""Versioned ordinary Wiki reading, with cumulative archived body references.

This contract does not impose the direct-article immediate-return policy.
Answers are model reported; deterministic provenance is not independent QC.
"""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlsplit
from .batch_core import load_json
from .planning import object_sha256, verify_evidence

LEGACY_VERSION = 'webcollect-wiki-reading-completion-1'
VERSION = 'webcollect-wiki-reading-completion-2'
FIELD = 'wiki_reading_completion_protocol'
GUIDANCE = '''本次使用普通Wiki累计阅读完成协议。首轮submit_plan顶层必须填写本请求的attempt_id和observation_id；不要新增requested_goal顶层字段。保留requested_goal；已有具体任务必须原样覆盖。仅无具体任务时首轮可选一个具体适度的阅读问题，goal和checks接受后冻结，不得因失败缩小。
checks至少一项，列待核阅读事项field，可给已知page/region。section仅填写当前真实目录或HTML章节标题原文，不填“某词条正文”等描述性位置；原目标没有明确章节要求且当前没有可核章节时可省略section，跨词条check使用已知真实page URL/href，不猜章节、不省去原目标必需章节。原目标要求通读整节必须scope=section，普通具体问题scope=passage，不预填未来visible_text或预猜答案关键词；每项evidence_kind为reading或actions。reading的required_step_indices为空可省。actions只用于原业务目标明确要求的click/back，用原首轮steps零起始索引；可选实现路线不自动成为业务义务。
目录和章节标题仅定位，不是正文答案；目录点击按实际href/位置效果，scroll用scroll_changed。finish_when用{"kind":"visible_text","text":"阅读完成由finish_reading核验","region":"正文"}作为完成申请占位，宿主不会把目录或任意正文出现当目标完成。真正完成只通过finish_reading申请。
保持合法剩余计划执行，不每步重规划。阅读证据累计保留，包括先前已保存帧中的正文，不要求末帧重显全部答案。所有原事项得到答案时可选finish_reading并提交reading_answer={answer,check_answers:[{check_index,answer,passages:[{observation_id,node,quote}],operation_ids}]}；引用只能来自reading_evidence_catalog，动作只能来自actual_operations。可省唯一可回算的引用元数据和operation_ids。必须的点击/返回仍须真实完成。缺项继续有用动作；stop只表示无法继续，不表示完成。累计最多10有效动作，不强制点击次数、章节数或固定往返模板，不补无用动作。'''


def system_text(value):
    """Remove only obsolete ordinary-Wiki instructions from the shared prompt."""
    replacements={
        '首轮必须给checks多项核对清单，逐项写field、允许的page（实际URL或可见章节标题）、region（正文/左栏菜单/业务区域标题）、visible_text（需要看见的原文关键词）。':
            '首轮checks列原问题的待核事项field和evidence_kind；已知来源可写page、region或section，不预填未来原文关键词。',
        '阅读必须见搜索打开后的新正文。':'阅读完成依据累计已保存正文引用与原事项覆盖，不要求先搜索。',
        '终点必须证明 requested_goal/session_objective 所要求的结果，而不是页面任意位置已有关键词。':
            'finish_reading完成申请必须引用requested_goal/session_objective所需的实际正文；finish_when占位字面不证明完成。',
        'finish_when 命中只说明该条件可见；剩余计划未走时，确认它确属冗余才能申请提前完成（finish_early，若在options中）。':
            'finish_when仅为协议占位；原问题及原checks已覆盖时用finish_reading，未执行的可选路线不是新增业务义务。',
    }
    for old,new in replacements.items():value=value.replace(old,new)
    return value


def enabled(task):
    return task.get('fragment', {}).get(FIELD) in (LEGACY_VERSION, VERSION)


def stable_ids(task):
    return task.get('fragment', {}).get(FIELD) == VERSION


def configure(task):
    """Only newly generated ordinary Wiki tasks opt in; frozen tasks stay intact."""
    from .banded_plan import V11_VERSION, V12_VERSION, V13_VERSION
    from .goal_evidence import contract_for
    url = urlsplit(task['initial_url'])
    if (task['fragment'].get('plan_protocol') not in (V11_VERSION, V12_VERSION, V13_VERSION) or contract_for(task)
            or not (url.hostname or '').endswith('.wikipedia.org') or not url.path.startswith('/wiki/')):
        return
    for part in (task['fragment'], task['workflow_proposal']['spec']):
        part[FIELD] = VERSION if task['fragment']['plan_protocol'] in (V12_VERSION,V13_VERSION) else LEGACY_VERSION



def schema(value, *, max_steps=10, evidence_ids=False):
    from .direct_completion import schema as completion_schema
    result=completion_schema(value,max_steps=max_steps)
    def visit(item):
        if isinstance(item,dict):
            props=item.get('properties',{})
            if 'checks' in props:
                props['checks']['items']['properties'].update(
                    section={'type':'string','minLength':1,'maxLength':120},
                    scope={'enum':['passage','section']},
                    **({'source_step_index':{'type':'integer','minimum':0}} if evidence_ids else {}))
            if evidence_ids and 'steps' in props and 'goal' in props:
                item['required']=[k for k in item.get('required',[]) if k!='finish_when']
            if evidence_ids and 'check_index' in props and 'passages' in props:
                props['evidence_ids']={'type':'array','maxItems':8,'uniqueItems':True,
                    'items':{'type':'string','minLength':1,'maxLength':80}}
                item['required']=[k for k in item.get('required',[]) if k!='passages']
            for child in item.values():visit(child)
        elif isinstance(item,list):
            for child in item:visit(child)
    visit(result)
    return result


def progress(session, initial_observation_id):
    from .direct_article import body
    from .direct_completion import completion
    modern=stable_ids(session.task)
    readings = []; seen = set()
    blocked_reason='WIKI_READING_UNRESOLVED_UNKNOWN' if getattr(session,'unknown',False) else None
    for row in session.trajectory:
        if row.get('unknown'):
            blocked_reason='WIKI_READING_UNRESOLVED_UNKNOWN'
            break  # Never join observations across an unresolved operation.
        if any(not session.observation_records.get(row.get(key),{}).get('capture_verified')
               for key in ('before_observation_id','after_observation_id')):
            blocked_reason=blocked_reason or 'WIKI_READING_UNVERIFIED_FRAME'
            break
        for key in ('before_observation_id', 'after_observation_id'):
            oid = row[key]; observation = session.observation_records[oid]
            state = load_json(observation['evidence']['state']['path'])
            for p in body(state):
                identity = ((oid,state['url'],p['node'],p['quote']) if modern else (state['url'],p['node'],p['quote']))
                if identity in seen:continue
                seen.add(identity)
                if modern:
                    from .reading_sections import section_titles
                    p={**p,'sections':section_titles(observation,state,p['node'])}
                readings.append({**p, 'url':state['url'], 'observation_id':oid,
                                 'operation_id':row['operation_id'], 'epoch':0,
                                 **({'evidence_id':'e'+object_sha256({'attempt':getattr(session,'attempt_id',None),
                                     'observation_id':oid,'url':state['url'],'node':p['node'],'quote':p['quote']})[:32]} if modern else {})})
    result = {'required':True, 'protocol':session.task['fragment'][FIELD], 'status':'UNVERIFIED',
              'new_visible_body':readings, 'passages':[], 'selected_passage':None,
              'return_required':False, 'semantic_goal_judgment':'MODEL_REPORTED_REQUIRES_INDEPENDENT_QC'}
    if blocked_reason:
        return {**result,'completion':None,'blocked_reason':blocked_reason}
    result['completion'] = completion(session, result)
    if result['completion']:result['status']='VERIFIED'
    return result


def validate_sources(session, plan, answer, evidence):
    """Original check/source identity and section containment, never answer truth."""
    from .plan_evidence import page_matches, region_matches, verify_page_binding
    controller=session.plan_controller
    binding=getattr(controller,'frozen_page_binding',None)
    if not binding:raise ValueError('WIKI_READING_ORIGINAL_PAGE_BINDING_MISSING')
    verify_page_binding(plan,binding)
    for item in answer['check_answers']:
        index=item['check_index']; check=plan['checks'][index]
        if check['evidence_kind']=='actions':continue
        source=binding['resolved_pages'][index] or check.get('page')
        if stable_ids(session.task):source=resolve_source(session,plan,index,binding)
        if not source:
            # A check without a page is bound to the actual original article.
            origin=session.observation_records[plan['observation_id']]
            source=origin['url']
        for p in item['passages']:
            state=load_json(session.observation_records[p['observation_id']]['evidence']['state']['path'])
            if not page_matches(source,state):
                raise ValueError(f'WIKI_READING_CHECK_{index}_WRONG_SOURCE')
            from .reading_sections import section_contains, section_rows, norm
            section=check.get('section')
            region=check.get('region')
            if section:
                if not section_contains(session.observation_records[p['observation_id']],state,p['node'],section):
                    raise ValueError(f'WIKI_READING_CHECK_{index}_WRONG_SECTION')
            elif region and not region_matches(state,p['node'],region):
                raise ValueError(f'WIKI_READING_CHECK_{index}_WRONG_SECTION')
        if check.get('scope')=='section':
            if not check.get('section'):raise ValueError(f'WIKI_READING_CHECK_{index}_SECTION_NOT_DECLARED')
            source_ob=session.observation_records[item['passages'][0]['observation_id']]
            required=section_rows(source_ob,check['section'])
            covered={r['selector']:set() for r in required}
            for reading in evidence['new_visible_body']:
                observation=session.observation_records[reading['observation_id']]
                state=load_json(observation['evidence']['state']['path'])
                if not page_matches(source,state):continue
                selector=next((b.get('selector') for b in state.get('capture_controls',[]) if b['element_id']==reading['node']),None)
                if not section_contains(observation,state,reading['node'],check['section']):continue
                for block in required:
                    if block['selector']!=selector:continue
                    text=norm(block['text']);quote=norm(reading['quote'])
                    start=text.find(quote)
                    if start>=0:covered[selector].update(range(start,start+len(quote)))
            if not required or any(len(covered[r['selector']])<len(norm(r['text'])) for r in required):
                raise ValueError(f'WIKI_READING_CHECK_{index}_SECTION_BODY_NOT_FULLY_READ')


def replay(record, expected, *, basis=None, _verified=None):
    """Rebuild explicit Wiki completion only from this attempt's sealed bytes."""
    if not enabled(record['task']):raise ValueError('WIKI_READING_PROTOCOL_REQUIRED')
    from pathlib import Path
    from .agent_observation import project
    from .closing_policy import validate_plan_page_bindings
    root=Path(record['receipt']['boundary']['path']).parent
    sealed=record['receipt']['files_sha256']
    marker=record['terminal'].get('collection_ending') or {}
    if (record['terminal'].get('unknown') or marker.get('external_effect_unknown')
            or marker.get('unverified_tail_dispatches')!=0 or not marker.get('safe_for_pending_sample')
            or marker.get('kind')!='HOST_PLAN_ENDPOINT'):
        raise ValueError('WIKI_READING_UNSAFE_OR_UNKNOWN_FINAL_BOUNDARY')
    def sealed_ref(ref, label):
        path=Path((ref or {}).get('path',''))
        if path.parent!=root or sealed.get(path.name)!=(ref or {}).get('sha256'):
            raise ValueError('WIKI_READING_'+label+'_OUTSIDE_SEALED_ATTEMPT')
        verify_evidence([ref])
    names=sorted(name for name in sealed if name.endswith(('-conditional-plan.json','-conditional-plan-revision.json')))
    if not names:raise ValueError('WIKI_READING_ORIGINAL_PLAN_MISSING')
    events=[]
    for name in names:
        sealed_ref({'path':str(root/name),'sha256':sealed[name]},'PLAN')
        event=load_json(root/name)
        if event.get('boundary')!=record['receipt']['boundary']:
            raise ValueError('WIKI_READING_PLAN_BOUNDARY_MISMATCH')
        events.append(event)
    original=events[0];plan=original['plan']
    if original.get('kind')!='conditional-plan':raise ValueError('WIKI_READING_ORIGINAL_PLAN_MISSING')
    attempt_id=plan.get('attempt_id')
    if (not isinstance(attempt_id,str) or not attempt_id
            or any(event['plan'].get('attempt_id')!=attempt_id for event in events)
            or record['boundary'].get('attempt_id',attempt_id)!=attempt_id):
        raise ValueError('WIKI_READING_PLAN_ATTEMPT_SCOPE_MISMATCH')
    if any(any(event['plan'].get(k)!=plan.get(k) for k in ('goal','checks')) for event in events):
        raise ValueError('WIKI_READING_ORIGINAL_GOAL_OR_CHECKS_CHANGED')
    validate_plan_page_bindings(record)
    decision=((expected or {}).get('completion') or {}).get('decision')
    if not decision:raise ValueError('WIKI_READING_EXPLICIT_COMPLETION_MISSING')
    sealed_ref(decision,'COMPLETION')
    observations=(_verified.observations(record) if _verified is not None else {})
    for oid,row in record['observations'].items():
        evidence=row['evidence']
        for key in ('state','image','capture','html'):sealed_ref(evidence[key],'OBSERVATION')
        if _verified is None:
            observations[oid]=project(load_json(evidence['state']['path']),{k:evidence[k] for k in ('image','state','capture')})
        observations[oid]['html_ref']=evidence['html']
    if basis is not None:
        if basis.get('initial_observation_id')!=plan['observation_id'] or basis.get('predicate')!=events[-1]['plan']['finish_when']:
            raise ValueError('WIKI_READING_ENDPOINT_ORIGINAL_PLAN_MISMATCH')
    session=SimpleNamespace(task=record['task'],plan_controller=SimpleNamespace(
        frozen_plan=plan,frozen_page_binding=original.get('page_binding')),
        trajectory=record['trajectory'],observation_records=observations,
        current=observations[record['terminal']['final_observation_id']],
        binding=record['receipt']['boundary'],attempt_id=attempt_id,
        reading_completion=decision,unknown=False)
    actual=progress(session,plan['observation_id'])
    if actual['status']!='VERIFIED' or actual!=expected:
        raise ValueError('WIKI_READING_SAVED_COMPLETION_NOT_REPRODUCIBLE')
    return actual


def verify_record(record, *, _verified=None):
    if not enabled(record['task']):return
    expected=(record['terminal'].get('goal_evidence') or {}).get('session_objective') or {}
    if not (expected.get('completion') or {}).get('decision'):return
    replay(record,expected,_verified=_verified)


def progress_key(session,action,failure):
    """Wording changes are not progress; use the archived business state."""
    from .direct_article import body
    state=load_json(session.current['evidence']['state']['path'])
    return object_sha256({'document':state.get('document_identity'),'url':state['url'],
        'scroll':state.get('scroll'),'body':body(state),'action':action,'failure':failure,
        'operations':[r['operation_id'] for r in session.trajectory]})


FINISH_WHEN={'kind':'visible_text','text':'阅读完成由finish_reading核验','region':'正文'}
NEW_GUIDANCE = '''普通Wiki正文证据新版：保留requested_goal；已有具体任务原样覆盖，仅无具体任务时可选择一次具体问题，首轮接受后goal与checks冻结。checks列原目标必要事项field、evidence_kind（reading/actions），不预填未来原文或答案。已知来源写page；查阅新条目可用source_step_index关联首轮click，工程能唯一确认查阅动作时可省，不能猜未来URL。section只写真实章节标题，明确通读整节才用scope=section；普通问题scope=passage，目录标题不是正文。actions只声明原业务必需的click/back，required_step_indices用首轮零起始索引，普通实现路线不是新增义务。
finish_when固定占位由工程补齐，真正完成用finish_reading提交reading_answer={answer,check_answers:[{check_index,answer,evidence_ids:[稳定编号]}]}。只选reading_check_progress对应事项的编号，不抄长引文、观察或动作身份；actions的operation_ids可省。已保存原帧正文累计保留，返回后仍可引用，完整回答原问题后立即申请。缺项只补读缺少内容，不改原问题，无新证据不重复重写引用。保持有效剩余路径，不每滚动一步重规划；允许滚动、链接、返回与续读自由组合，不固定点击次数/比例或往返模板。累计最多10有效动作，不补无用动作；stop不能声称完成。合法引用不证明答案语义正确，仍须独立QC。'''


def bind_plan_wire(arguments,prompt):
    if prompt.get(FIELD)!=VERSION:return arguments
    result=deepcopy(arguments)
    from .banded_plan import V13_VERSION
    if prompt.get('protocol')==V13_VERSION:
        result.pop('finish_when',None)
    elif 'finish_when' in result and result['finish_when']!=FINISH_WHEN:
        raise ValueError('WIKI_READING_FINISH_PROTOCOL_CONFLICT')
    result['finish_when']=deepcopy(FINISH_WHEN)
    return result


def bind_reply(response,prompt):
    if prompt.get(FIELD)!=VERSION:return response
    result=deepcopy(response)
    if result.get('choice')=='finish_reading' and 'check_answers' in result:
        answers=result.pop('check_answers')
        answer={'check_answers':answers,'answer':'；'.join(str(r.get('answer','')) for r in answers)}
        if 'reading_answer' in result and result['reading_answer']!=answer:
            raise ValueError('WIKI_READING_CONFLICTING_ANSWERS')
        result['reading_answer']=answer
    return result


def resolve_source(session,plan,index,binding):
    """Resolve a frozen check to its actual archived lookup, never any visited URL."""
    import re
    from .direct_completion import action_requirements
    from .direct_article import url_key
    check=plan['checks'][index]
    source=binding['resolved_pages'][index] or check.get('page')
    step=check.get('source_step_index')
    if step is not None and (type(step)is not int or not 0<=step<len(plan['steps']) or plan['steps'][step]['action']!='click'):
        raise ValueError(f'WIKI_READING_CHECK_{index}_INVALID_SOURCE_STEP')
    # Missing source is not intrinsically the entry page. Only an explicit
    # current-page statement or a uniquely evidenced original lookup resolves it.
    if step is None and source:return source
    field=check.get('field','')
    cross=bool(re.search('点入|点击进入|进入的|相关条目|查阅.*条目|链接.*条目',field))
    if step is None and not cross:
        if re.search('当前页|本页|入口页',field):
            return session.observation_records[plan['observation_id']]['url']
        raise ValueError(f'WIKI_READING_CHECK_{index}_SOURCE_UNBOUND: declare original source or lookup')
    candidates=([step] if step is not None else [i for i,s in enumerate(plan['steps'])
        if s.get('action')=='click' and (s.get('expected',{}).get('kind')=='document_changed'
            or re.search('条目|查阅|进入|正文|链接',s.get('purpose','')))])
    if len(candidates)!=1:
        raise ValueError(f'WIKI_READING_CHECK_{index}_SOURCE_UNBOUND: original lookup is ambiguous')
    original=candidates[0];landings=[]
    for row in session.trajectory:
        if row.get('unknown'):break
        before=session.observation_records.get(row.get('before_observation_id'),{})
        after=session.observation_records.get(row.get('after_observation_id'),{})
        if not before.get('capture_verified') or not after.get('capture_verified'):break
        if row.get('action')!='click':continue
        state=load_json(before['evidence']['state']['path'])
        cid=(row.get('target') or {}).get('control_id')
        actual=next((b for b in state.get('capture_controls',[]) if b['element_id']==cid),{})
        href=actual.get('href')
        if not href:continue
        matched=False
        try:
            action_requirements(session,{'required_step_indices':[original]},plan,[row['operation_id']])
            matched=True
        except ValueError:pass
        # A formerly semantic future target may be rebound by a remaining plan.
        # Its exact frozen purpose must survive in the dispatched operation;
        # free similarity or merely visiting a page cannot establish identity.
        wanted=plan['steps'][original]
        if not matched and not wanted.get('target',{}).get('href') and not wanted.get('target',{}).get('node'):
            purpose=wanted.get('purpose')
            matched=bool(purpose and purpose in (row.get('semantic_goal'),row.get('goal')))
        if not matched:continue
        landed=load_json(after['evidence']['state']['path'])['url']
        if url_key(landed)==url_key(state['url']):continue
        landings.append((row['operation_id'],href,landed))
    if len(landings)!=1:
        raise ValueError(f'WIKI_READING_CHECK_{index}_SOURCE_UNBOUND: original lookup not uniquely executed')
    landed=landings[0][2]
    if source:
        from .plan_evidence import page_matches
        if not page_matches(source,{'url':landed}):raise ValueError(f'WIKI_READING_CHECK_{index}_SOURCE_CONFLICT')
    return landed


def evidence_payload(session):
    """Short previews and per-check missing facts, using the same source verifier."""
    plan=getattr(session.plan_controller,'frozen_plan',{})
    facts=progress(session,plan.get('observation_id'))
    catalog=facts['new_visible_body'];rows=[]
    for i,check in enumerate(plan.get('checks',[])):
        allowed=[];missing=None
        if check.get('evidence_kind')=='actions':
            try:
                from .direct_completion import action_requirements
                action_requirements(session,check,plan,[r['operation_id'] for r in session.trajectory])
            except ValueError:missing='原要求的点击或返回尚未完成'
        else:
            for passage in catalog:
                try:validate_sources(session,plan,{'check_answers':[{'check_index':i,'passages':[passage]}]},facts)
                except ValueError as error:missing=str(error);continue
                allowed.append(passage['evidence_id'])
            missing=None if allowed else (missing or '缺少原检查对应页面或章节的已保存正文')
        rows.append({'check_index':i,'field':check['field'],'available_evidence_ids':allowed,
                     'missing':missing,'answer_required':True})
    return {'reading_evidence_catalog':[{'evidence_id':p['evidence_id'],'preview':p['quote'][:160],
                'url':p['url']} for p in catalog], 'reading_check_progress':rows}
