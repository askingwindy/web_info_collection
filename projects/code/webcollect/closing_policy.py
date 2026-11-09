"""V2 bounded business attempts and evidence-bound exceptional closure.

The raw attempt journal includes zero-dispatch and unverified tails. Only a
continuous verified prefix with a proved harmless tail can be a marked sample.
"""
from .batch_core import load_json
from .planning import verify_evidence, object_sha256
from .reading_progress import same_view

V2_VERSION = 'webcollect-five-eight-attempt-ending-2'
V3_VERSION = 'webcollect-banded-attempt-ending-3'
VERSION = 'webcollect-continuous-attempt-ending-4'
EFFECTIVE_VERSION = 'webcollect-five-ten-effective-ending-5'
EFFECTIVE_MAXIMUM = 10
VERSIONS = (V2_VERSION, V3_VERSION, VERSION, EFFECTIVE_VERSION)
MINIMUM = 5
MAXIMUM = 8
LONG_MAXIMUM = 12
PROMPT = '''本任务按5–8次业务动作尝试收尾。每个实际准备执行的原子业务动作算一次尝试，复合act按其实际原子操作分别计次；派发前拒绝单列零派发尝试。宿主另列真实原子派发与已验证有效步。observe/inspect、无效参数/过期引用、wait、finish/complete不算业务尝试。未派发不算实际动作或有效步。目标可见结果已达到就finish，自然短流程照实结束，不凑步。第5–8次尝试的最后操作明确失败或效果无法核定时，立即停止探索并finish保存、标记异常；第8次之后宿主收口，不再追加第9次动作。异常收尾不等于目标完成；外部效果未知或缺可信末态只封存原件待核，不重发、不拼接。'''


def enabled(task):
    return task.get('fragment',{}).get('ending_policy') in VERSIONS


def attempt_limit(task, band=None):
    """One ceiling shared by planning, dispatch, closure and saved evidence."""
    fragment=task.get('fragment',{})
    if fragment.get('ending_policy') == EFFECTIVE_VERSION:
        return EFFECTIVE_MAXIMUM
    if fragment.get('ending_policy') == VERSION:
        return None
    band=band or fragment.get('session_objective',{}).get('objective',{}).get('preferred_band')
    limit=(LONG_MAXIMUM if fragment.get('ending_policy')==V3_VERSION
           and fragment.get('plan_protocol')=='webcollect-banded-conditional-plan-11'
           and band=='long' else MAXIMUM)
    budget=fragment.get('budgets',{}).get('max_actions')
    return min(budget,limit) if budget is not None else limit


def effective_limit(task):
    return EFFECTIVE_MAXIMUM if task.get('fragment',{}).get('ending_policy') == EFFECTIVE_VERSION else None


def limit_kind(limit):
    if limit == EFFECTIVE_MAXIMUM:return 'TEN_EFFECTIVE_STEP_LIMIT'
    return 'TWELVE_ATTEMPT_LIMIT' if limit==LONG_MAXIMUM else 'EIGHT_ATTEMPT_LIMIT'


def system_prompt(base, task=None):
    start=base.index('通常争取至少五个真实有效操作。')
    end=base.index('\n只引用当前观察',start)
    prompt=PROMPT
    if task is not None and attempt_limit(task) is None:
        prompt=('按当前目标和页面证据自然执行，不设动作次数、规划轮次或会话时长配额。'
                '目标达到即finish；无法继续时如实结束，不凑步。每个真实原子动作分别记账，'
                'observe/inspect/wait/finish不算有效业务动作。1–4步由宿主标记short_flow，零步不成样本。'
                '同站仅复用页面和动作知识，禁止复用完整动作链。滚动、跳转、返回后依当前观察重绑，必要时重规划。'
                '外部效果未知时保留原件，不重发、不拼接、不声称成功。')
    if task is not None and effective_limit(task) is not None:
        prompt=('先按原目标形成最短完整自然路径，通常控制在5–10个有效业务动作，累计最多10步。'
                '自然路径不足5步时，只在原目标内补充仍有独立用途且能产生新证据的动作；没有就如实结束，'
                '由宿主标记short_flow，零步不成样本。不得为数量另选繁琐目标、增加第二组输入或跨词条任务，'
                '不得重复输入、重复计算或无效往返。分支只规划剩余有效步；无效果动作保留派发记账但不计有效步。'
                '目标达到即finish；累计达到10步后结束，不再派发业务动作；必要结果缺证如实报告。'
                'observe/inspect/wait/finish不算有效业务动作；UNKNOWN保留原件，不重发、不拼接。')
    if task is not None and attempt_limit(task)==LONG_MAXIMUM:
        prompt=(prompt.replace('5–8','5–12')
                .replace('第8次之后宿主收口，不再追加第9次动作','第12次之后宿主收口，不再追加第13次动作'))
    return base[:start]+prompt+base[end:]


def state(record, oid):
    return load_json(record['observations'][oid]['state_path'])


def no_effect_proven(raw, observations, *, action_scoped=False):
    """Prove an omitted dispatch harmless using its original before/after states.

    A definite outcome label alone is insufficient. Values and business elements
    must be unchanged; action-scoped text/geometry equality cannot erase inputs.
    Observation values may be raw states or sealed observation rows.
    """
    react=raw.get('react',{})
    if (raw.get('unknown') is True or react.get('unknown') is True
            or raw.get('dispatched') is not True or raw.get('action_executed') is not True
            or react.get('zero_effect') is not True
            or react.get('effect_evidence',{}).get('verified') is True
            or react.get('after_observation_id') not in observations):
        return False
    before=raw.get('state');after=observations[react['after_observation_id']]
    if 'state_path' in after:after=load_json(after['state_path'])
    elif 'evidence' in after:after=load_json(after['evidence']['state']['path'])
    if not isinstance(before,dict) or not before.get('document_identity'):
        return False
    return (before.get('document_identity') == after.get('document_identity')
            and same_view(before,after))


def validate_reading_completion(record, basis):
    """Recompute the flag's early-end coverage from its sealed plan and facts."""
    from .plan_evidence import READING_COMPLETION_POLICY, facts, remaining_plan_coverage
    if record['task']['fragment'].get('reading_completion_policy')!=READING_COMPLETION_POLICY:return
    from pathlib import Path
    from types import SimpleNamespace
    from .agent_observation import project
    from .react_session import struct_goal
    receipt=basis.get('reading_plan_completion') or {}
    if receipt.get('protocol')!=READING_COMPLETION_POLICY:
        raise ValueError('Reading endpoint is missing frozen remaining-plan completion receipt')
    root=Path(record['receipt']['boundary']['path']).parent
    sealed=record['receipt']['files_sha256']
    plans=sorted(name for name in sealed if name.endswith(('-conditional-plan.json','-conditional-plan-revision.json')))
    if not plans:raise ValueError('Reading endpoint has no sealed source plan')
    loaded=[]
    for key,expected_name,expected_kind in (('original_plan',plans[0],'conditional-plan'),
                                         ('current_plan',plans[-1],None)):
        ref=receipt.get(key) or {};path=Path(ref.get('path',''))
        if path.parent!=root or path.name!=expected_name or sealed.get(path.name)!=ref.get('sha256'):
            raise ValueError('Reading completion plan reference is outside the sealed original route')
        verify_evidence([ref]);event=load_json(path)
        if expected_kind is not None and event.get('kind')!=expected_kind:
            raise ValueError('Reading completion original-plan kind mismatch')
        loaded.append(event)
    original,current=loaded;plan=current['plan'];position=receipt.get('position')
    if (receipt.get('original_plan_sha256')!=object_sha256(original['plan'])
            or receipt.get('current_plan_sha256')!=object_sha256(plan)
            or type(position) is not int or not 0<=position<=len(plan['steps'])):
        raise ValueError('Reading completion plan hash or remaining position mismatch')
    # A supplied position cannot silently discard unexecuted plan slots.
    effects=[]
    after_ids={r['after_observation_id'] for r in record['trajectory']}
    for name in sorted(sealed):
        if name<=plans[-1] or not name.endswith('-plan-effect.json'):continue
        event=load_json(root/name);actual=event.get('actual') or {}
        if actual.get('actual_effective_delta')!=1:continue
        index=actual.get('position')
        if (type(index) is not int or not 0<=index<len(plan['steps'])
                or event.get('expected')!=plan['steps'][index]['expected']
                or actual.get('observation_id') not in after_ids):
            raise ValueError('Reading completed-step evidence differs from the sealed plan')
        effects.append(index)
    if effects!=list(range(position)):
        raise ValueError('Reading remaining-plan position skips unexecuted or unresolved actions')
    observations={}
    for oid,row in record['observations'].items():
        observations[oid]=project(state(record,oid),{k:row['evidence'][k] for k in ('image','state','capture')})
    session=SimpleNamespace(task=record['task'],trajectory=record['trajectory'],observation_records=observations,
        requested_goal=struct_goal(record['task']),working_goal=record['terminal'].get('working_goal'))
    evidence=facts(session,original['plan'],page_urls=original.get('check_page_urls',{}))
    expected=remaining_plan_coverage(session,plan,position,evidence)
    if expected!=receipt.get('coverage') or expected['status']!='COVERED':
        raise ValueError('Reading remaining purposes are not covered by sealed body goal facts')
    return receipt


def validate_record(record):
    """Recompute tail accounting from immutable attempt/raw references."""
    marker=record['terminal'].get('collection_ending')
    policy=(record['task'].get('fragment',{}) or {}).get('ending_policy')
    if not enabled(record['task']) or not marker or marker.get('protocol')!=policy:
        raise ValueError('Missing versioned closure binding')
    band=marker.get('attempt_band')
    limit=attempt_limit(record['task'],band) if policy in (V3_VERSION, VERSION, EFFECTIVE_VERSION) else MAXIMUM
    if policy in (V3_VERSION, VERSION, EFFECTIVE_VERSION) and (marker.get('attempt_limit')!=limit or marker.get('attempt_band')!=band):
        raise ValueError('V3 closure attempt ceiling differs from its frozen task/band')
    attempts=[];raws=[];raw_refs=[]
    for ref in marker['attempt_refs']:
        verify_evidence([ref]);attempt=load_json(ref['path'])
        if attempt.get('kind')!='business-attempt':
            raise ValueError('Not an original business-attempt event')
        attempts.append(attempt)
        for raw_ref in attempt.get('raw_steps',[]):
            verify_evidence([raw_ref]);raws.append(load_json(raw_ref['path']));raw_refs.append(raw_ref)
    if ([a['number'] for a in attempts]!=list(range(1,len(attempts)+1)) or (limit is not None and policy!=EFFECTIVE_VERSION and len(attempts)>limit)
            or marker['business_attempts']!=len(attempts)):
        raise ValueError('Versioned business-attempt count changed')
    kind=marker.get('kind')
    if policy==EFFECTIVE_VERSION and marker.get('verified_effective_steps',0)>EFFECTIVE_MAXIMUM:
        raise ValueError('Effective-step ceiling exceeded')
    if kind=='TEN_EFFECTIVE_STEP_LIMIT' and (policy!=EFFECTIVE_VERSION or marker.get('verified_effective_steps')!=EFFECTIVE_MAXIMUM):
        raise ValueError('Effective-step limit closure differs from verified count')
    if kind in ('EIGHT_ATTEMPT_LIMIT','TWELVE_ATTEMPT_LIMIT') and (len(attempts)!=limit or kind!=limit_kind(limit)):
        raise ValueError('Attempt-limit closure kind differs from the actual ceiling/count')
    dispatched=[r for r in raws if r.get('dispatched') is True]
    verified=[r for r in dispatched if r.get('action_executed') is True
              and r.get('postconditions_checked') is True and r.get('react',{}).get('effect_evidence',{}).get('verified') is True]
    verified_refs=[ref for ref,raw in zip(raw_refs,raws) if raw in verified]
    if (len({ref['path'] for ref in raw_refs})!=len(raw_refs)
            or sorted((r['path'],r['sha256']) for r in verified_refs)
               !=sorted((r['raw_step']['path'],r['raw_step']['sha256']) for r in record['trajectory'])):
        raise ValueError('V2 attempt journal does not account for the exact verified prefix')
    for attempt in attempts:
        original=[load_json(ref['path']) for ref in attempt.get('raw_steps',[])]
        if (attempt['actual_dispatches_delta']!=sum(r.get('dispatched') is True for r in original)
                or attempt['effective_steps_delta']!=sum(r in verified for r in original)):
            raise ValueError('V2 per-attempt accounting differs from original raw')
    if (len(dispatched)!=marker['actual_atomic_dispatches']
            or len(dispatched)!=record['terminal']['actual_actions']
            or len(verified)!=len(record['trajectory'])
            or marker['verified_effective_steps']!=len(verified)
            or marker['unverified_tail_dispatches']!=len(dispatched)-len(verified)):
        raise ValueError('V2 dispatch/effective/tail accounting differs from original raw')
    prefix=record['trajectory']; final=record['terminal'].get('final_observation_id')
    safe=bool(prefix and final in record['observations'] and not record['terminal'].get('unknown')
              and (state(record,final).get('visible_text') or '').strip())
    if safe and len(dispatched)>len(verified):
        tail=[r for r in dispatched if r not in verified]
        if policy==EFFECTIVE_VERSION:
            safe=all(no_effect_proven(raw,record['observations']) for raw in tail)
        else:
            safe=(len(tail)==1 and tail[0]['operation']['action_type']=='scroll'
                  and tail[0].get('action_executed') is True
                  and tail[0].get('react',{}).get('after_observation_id') in record['observations'])
            if safe:
                raw=tail[0]; before=raw['state']; after=state(record,raw['react']['after_observation_id'])
                safe=same_view(before,after) and same_view(after,state(record,final))
    if safe:
        from .action_stability import ACTION_SCOPED_VERSIONS, action_scoped_view_stable
        if record['task']['fragment'].get('action_stability_protocol') in ACTION_SCOPED_VERSIONS:
            # Offline mirror of the online action-scoped ending check: same
            # document/scroll and retained visible reading material; unrelated
            # decorative image/overlay membership changes are not endpoint
            # changes. Older protocols keep the full same_view rule.
            safe=action_scoped_view_stable(state(record,prefix[-1]['after_observation_id']),state(record,final))
        else:
            safe=same_view(state(record,prefix[-1]['after_observation_id']),state(record,final))
        bridge=marker.get('direct_terminal_bridge')
        if bridge:
            from .direct_completion import enabled as explicit,bridge_evidence
            if not explicit(record['task']) or len(dispatched)!=len(verified) or marker.get('kind')!='HOST_PLAN_ENDPOINT':
                raise ValueError('Direct terminal bridge cannot cover unknown/tail/other closure')
            actual=bridge_evidence(record['task'],record['observations'][prefix[-1]['after_observation_id']]['evidence'],
                record['observations'][final]['evidence'],target_ids=[(r.get('target') or {}).get('control_id') for r in prefix])
            if actual!=bridge:raise ValueError('Direct terminal bridge differs from original frames')
            safe=safe or actual['proof']['accepted'] is True
    if marker['safe_for_pending_sample'] and not safe:
        raise ValueError('V2 closure cannot prove a safe continuous prefix and terminal')
    if marker.get('kind')=='HOST_BOUNDARY_RETURN':
        from .consumer_page_policy import ending_evidence, PLAN_PROTOCOL
        actual=ending_evidence(record['task'],prefix,{oid:state(record,oid) for oid in record['observations']},final)
        from .banded_plan import VERSIONS as PLAN_VERSIONS
        if (not actual or actual!=marker.get('boundary_return_evidence')
                or marker.get('plan_protocol') not in PLAN_VERSIONS[6:]
                or marker.get('plan_protocol')!=record['task']['fragment'].get('plan_protocol') or not safe):
            raise ValueError('Boundary return lacks two original effective actions and a sealed safe return')
    if marker.get('kind')=='HOST_PLAN_ENDPOINT':
        from .banded_plan import VERSIONS as PLAN_VERSIONS
        if (marker.get('plan_protocol')!=record['task']['fragment'].get('plan_protocol')
                or marker.get('plan_protocol') not in PLAN_VERSIONS):
            raise ValueError('Host endpoint is not bound to the original plan task')
        basis=marker.get('endpoint_evidence') or {}
        validate_reading_completion(record,basis)
        final_evidence=record['observations'][final]['evidence']
        if basis.get('image')!=final_evidence['image']:
            raise ValueError('Endpoint image differs from sealed final observation')
        if record['task']['fragment'].get('plan_protocol') in ('webcollect-banded-conditional-plan-6','webcollect-banded-conditional-plan-7','webcollect-banded-conditional-plan-8','webcollect-banded-conditional-plan-9','webcollect-banded-conditional-plan-10','webcollect-banded-conditional-plan-11'):
            from types import SimpleNamespace
            from pathlib import Path
            from .agent_observation import project
            from .session_objective import progress
            observations={}
            for oid,row in record['observations'].items():
                ob=project(state(record,oid),{k:row['evidence'][k] for k in ('image','state','capture')})
                ob['html']=Path(row['evidence']['html']['path']).read_text()
                observations[oid]=ob
            session=SimpleNamespace(task=record['task'],trajectory=record['trajectory'],
                observation_records=observations,current=observations[final])
            # The live session exposes its structured goal to the evidence
            # machinery; the offline replay must reconstruct the same surface,
            # or objective requirements derived from the goal description
            # (downward reading) would silently differ between both sides.
            from .react_session import struct_goal
            session.requested_goal=struct_goal(record['task'])
            from .goal_evidence import contract_for
            if contract_for(session.task):
                session.attempt_id = record['boundary']['attempt_id']
                session.binding = record['receipt']['boundary']
                session.answer_citation = (basis.get('session_objective_evidence') or {}).get('citation_event')
                from .direct_completion import enabled as explicit
                if explicit(session.task):
                    plans=sorted(Path(session.binding['path']).parent.glob('*-conditional-plan.json'))
                    from types import SimpleNamespace
                    session.plan_controller=SimpleNamespace(frozen_plan=load_json(plans[0])['plan'])
                    session.reading_completion=((basis.get('session_objective_evidence') or {}).get('completion') or {}).get('decision')
                    if session.reading_completion:
                        p=Path(session.reading_completion['path'])
                        if p.parent!=Path(session.binding['path']).parent or record['receipt']['files_sha256'].get(p.name)!=session.reading_completion['sha256']:
                            raise ValueError('Direct completion is outside the sealed attempt')
                if session.answer_citation:
                    path = Path(session.answer_citation['path'])
                    if (path.parent != Path(session.binding['path']).parent or
                            record['receipt']['files_sha256'].get(path.name) != session.answer_citation['sha256']):
                        raise ValueError('Reading citation is outside this sealed attempt')
            actual=progress(session,basis.get('initial_observation_id'))
            if actual['required'] and (actual['status']!='VERIFIED' or actual!=basis.get('session_objective_evidence')):
                raise ValueError('Explicit session objective is not established by the sealed original trace')
        if basis.get('source')=='host_rendered_state':
            from .agent_observation import project
            from .banded_plan import proves
            observation=project(state(record,final),{k:final_evidence[k] for k in ('image','state','capture')})
            if not proves(basis['predicate'],observation):
                raise ValueError('Sealed host endpoint predicate is not independently established')
        elif basis.get('source')=='host_goal_evidence':
            from .goal_evidence import contract_for
            if (not contract_for(record['task']) or basis.get('predicate',{}).get('kind') != 'goal_evidence'
                    or not actual['required'] or actual['status'] != 'VERIFIED'):
                raise ValueError('Host goal endpoint requires the sealed explicit evidence contract')
        elif basis.get('source')=='model_visual':
            proof=basis.get('visual_confirmation');verify_evidence([proof]);visual=load_json(proof['path'])
            decision=visual.get('decision_event');verify_evidence([decision]);branch=load_json(decision['path'])
            if (visual.get('kind')!='model-visual-confirmation' or visual.get('predicate')!=basis.get('predicate')
                    or visual.get('image',{}).get('sha256')!=final_evidence['image']['sha256']
                    or visual.get('document_identity')!=state(record,final).get('document_identity')
                    or branch.get('kind')!='plan-branch' or branch['response'].get('choice')!='visual_yes'
                    or branch['response'].get('visual_evidence')!=visual.get('interpretation')
                    or branch['response'].get('observation_id')!=visual.get('observation_id')
                    or visual.get('boundary')!=branch.get('boundary')):
                raise ValueError('Visual endpoint lacks its original image/ordinary decision binding')
        else:raise ValueError('Unknown host endpoint evidence source')
    return {**marker,'safe_for_pending_sample':bool(marker['safe_for_pending_sample'] and safe)}


def annotation_errors(annotation):
    marker=annotation.get('steps',[{}])[-1].get('tool_result',{}).get('return_value',{}).get('collection_ending')
    if not marker:return []
    policy=marker.get('protocol')
    limit=EFFECTIVE_MAXIMUM if policy==EFFECTIVE_VERSION else None if policy==VERSION else marker.get('attempt_limit',MAXIMUM) if policy==V3_VERSION else MAXIMUM
    effective=sum(s.get('action',{}).get('action_type') not in ('wait','complete') for s in annotation['steps'])
    errors=[]
    if (policy not in VERSIONS or marker.get('verified_effective_steps')!=effective
            or type(marker.get('business_attempts')) is not int or marker['business_attempts']<0
            or (limit is not None and policy!=EFFECTIVE_VERSION and marker['business_attempts']>limit)
            or (policy==EFFECTIVE_VERSION and (marker.get('attempt_limit')!=EFFECTIVE_MAXIMUM or effective>EFFECTIVE_MAXIMUM))
            or (policy==VERSION and marker.get('attempt_limit') is not None)
            or (policy==V3_VERSION and (marker.get('attempt_limit') not in (MAXIMUM,LONG_MAXIMUM)
                                    or marker.get('attempt_band') not in ('five','long','short',None)))
            or marker.get('actual_atomic_dispatches',-1)!=effective+marker.get('unverified_tail_dispatches',-1)
            or marker.get('safe_for_pending_sample') is not True or marker.get('external_effect_unknown') is not False
            or not marker.get('final_observation_id') or not marker.get('final_evidence')
            or marker.get('finish_count',0)!=1):
        errors.append('Versioned ending counts, finish, final evidence or safe-state binding is invalid')
    if marker.get('flagged') and (annotation.get('completion_status')!='controlled_exception'
            or not annotation['steps'][-1].get('exception_evidence')):
        errors.append('Flagged ending must be an explicit controlled_exception with evidence')
    if marker.get('goal_completion') not in ('NOT_CLAIMED','AGENT_REPORTED_VISIBLE_GOAL'):
        errors.append('Closure cannot invent business success')
    kind=marker.get('kind');attempts=marker.get('business_attempts',-1)
    if (marker.get('flagged') is not (kind not in ('VISIBLE_GOAL_REPORTED','HOST_PLAN_ENDPOINT','HOST_BOUNDARY_RETURN'))
            or marker.get('finish_origin') not in ('host','agent')
            or marker.get('finish_is_business_action') is not False or marker.get('wait_is_business_action') is not False
            or len(marker.get('attempt_refs',[]))!=attempts
            or (marker.get('flagged') and (kind not in ('EIGHT_ATTEMPT_LIMIT','TWELVE_ATTEMPT_LIMIT','TEN_EFFECTIVE_STEP_LIMIT','MODEL_BUDGET_LIMIT','KNOWN_NO_EFFECT','NOT_DISPATCHED')
                or attempts < (1 if policy in (VERSION,EFFECTIVE_VERSION) else 5) or (limit is not None and policy!=EFFECTIVE_VERSION and attempts>limit)))
            or (kind in ('EIGHT_ATTEMPT_LIMIT','TWELVE_ATTEMPT_LIMIT') and (attempts!=limit or kind!=limit_kind(limit)))
            or (kind=='TEN_EFFECTIVE_STEP_LIMIT' and (policy!=EFFECTIVE_VERSION or effective!=EFFECTIVE_MAXIMUM))
            or (policy!=EFFECTIVE_VERSION and marker.get('unverified_tail_dispatches',0)>0 and kind!='KNOWN_NO_EFFECT')):
        errors.append('Versioned exceptional closure kind/range/attempt references are inconsistent')
    if kind=='HOST_BOUNDARY_RETURN':
        from .consumer_page_policy import VERSION as PAGE_POLICY, PLAN_PROTOCOL
        proof=marker.get('boundary_return_evidence') or {}
        if (marker.get('plan_protocol') not in (PLAN_PROTOCOL,'webcollect-banded-conditional-plan-8','webcollect-banded-conditional-plan-9','webcollect-banded-conditional-plan-10','webcollect-banded-conditional-plan-11') or proof.get('policy')!=PAGE_POLICY
                or marker.get('goal_completion')!='NOT_CLAIMED' or marker.get('finish_origin')!='host'
                or effective<2 or marker.get('unverified_tail_dispatches')!=0):
            errors.append('Boundary return must preserve two verified operations without a login/download success claim')
    if kind=='HOST_PLAN_ENDPOINT' and (marker.get('plan_protocol') not in ('webcollect-banded-conditional-plan-1','webcollect-banded-conditional-plan-2','webcollect-banded-conditional-plan-3','webcollect-banded-conditional-plan-4','webcollect-banded-conditional-plan-5','webcollect-banded-conditional-plan-6','webcollect-banded-conditional-plan-7','webcollect-banded-conditional-plan-8','webcollect-banded-conditional-plan-9','webcollect-banded-conditional-plan-10','webcollect-banded-conditional-plan-11')
            or marker.get('finish_origin')!='host' or marker.get('goal_completion')!='NOT_CLAIMED'):
        errors.append('Host endpoint requires frozen conditional-plan binding and no business-success claim')
    return errors
