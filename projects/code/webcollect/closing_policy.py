"""V2 bounded business attempts and evidence-bound exceptional closure.

The raw attempt journal includes zero-dispatch and unverified tails. Only a
continuous verified prefix with a proved harmless tail can be a marked sample.
"""
from .batch_core import load_json
from .planning import verify_evidence, object_sha256
from .reading_progress import same_view

V2_VERSION = 'webcollect-five-eight-attempt-ending-2'
VERSION = 'webcollect-banded-attempt-ending-3'
VERSIONS = (V2_VERSION, VERSION)
MINIMUM = 5
MAXIMUM = 8
LONG_MAXIMUM = 12
PROMPT = '''本任务按5–8次业务动作尝试收尾。每个实际准备执行的原子业务动作算一次尝试，复合act按其实际原子操作分别计次；派发前拒绝单列零派发尝试。宿主另列真实原子派发与已验证有效步。observe/inspect、无效参数/过期引用、wait、finish/complete不算业务尝试。未派发不算实际动作或有效步。目标可见结果已达到就finish，自然短流程照实结束，不凑步。第5–8次尝试的最后操作明确失败或效果无法核定时，立即停止探索并finish保存、标记异常；第8次之后宿主收口，不再追加第9次动作。异常收尾不等于目标完成；外部效果未知或缺可信末态只封存原件待核，不重发、不拼接。'''


def enabled(task):
    return task.get('fragment',{}).get('ending_policy') in VERSIONS


def attempt_limit(task, band=None):
    """One ceiling shared by planning, dispatch, closure and saved evidence."""
    fragment=task.get('fragment',{})
    band=band or fragment.get('session_objective',{}).get('objective',{}).get('preferred_band')
    limit=(LONG_MAXIMUM if fragment.get('ending_policy')==VERSION
           and fragment.get('plan_protocol')=='webcollect-banded-conditional-plan-11'
           and band=='long' else MAXIMUM)
    budget=fragment.get('budgets',{}).get('max_actions')
    return min(budget,limit) if budget is not None else limit


def limit_kind(limit):
    return 'TWELVE_ATTEMPT_LIMIT' if limit==LONG_MAXIMUM else 'EIGHT_ATTEMPT_LIMIT'


def system_prompt(base, task=None):
    start=base.index('通常争取至少五个真实有效操作。')
    end=base.index('\n只引用当前观察',start)
    prompt=PROMPT
    if task is not None and attempt_limit(task)==LONG_MAXIMUM:
        prompt=(prompt.replace('5–8','5–12')
                .replace('第8次之后宿主收口，不再追加第9次动作','第12次之后宿主收口，不再追加第13次动作'))
    return base[:start]+prompt+base[end:]


def state(record, oid):
    return load_json(record['observations'][oid]['state_path'])


def validate_record(record):
    """Recompute tail accounting from immutable attempt/raw references."""
    marker=record['terminal'].get('collection_ending')
    policy=(record['task'].get('fragment',{}) or {}).get('ending_policy')
    if not enabled(record['task']) or not marker or marker.get('protocol')!=policy:
        raise ValueError('Missing versioned closure binding')
    band=marker.get('attempt_band')
    limit=attempt_limit(record['task'],band) if policy==VERSION else MAXIMUM
    if policy==VERSION and (marker.get('attempt_limit')!=limit or marker.get('attempt_band')!=band):
        raise ValueError('V3 closure attempt ceiling differs from its frozen task/band')
    attempts=[];raws=[];raw_refs=[]
    for ref in marker['attempt_refs']:
        verify_evidence([ref]);attempt=load_json(ref['path'])
        if attempt.get('kind')!='business-attempt':
            raise ValueError('Not an original business-attempt event')
        attempts.append(attempt)
        for raw_ref in attempt.get('raw_steps',[]):
            verify_evidence([raw_ref]);raws.append(load_json(raw_ref['path']));raw_refs.append(raw_ref)
    if ([a['number'] for a in attempts]!=list(range(1,len(attempts)+1)) or len(attempts)>limit
            or marker['business_attempts']!=len(attempts)):
        raise ValueError('Versioned business-attempt count changed')
    kind=marker.get('kind')
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
    policy=marker.get('protocol');limit=marker.get('attempt_limit',MAXIMUM) if policy==VERSION else MAXIMUM
    effective=sum(s.get('action',{}).get('action_type') not in ('wait','complete') for s in annotation['steps'])
    errors=[]
    if (policy not in VERSIONS or marker.get('verified_effective_steps')!=effective
            or type(marker.get('business_attempts')) is not int or not 0<=marker['business_attempts']<=limit
            or (policy==VERSION and (marker.get('attempt_limit') not in (MAXIMUM,LONG_MAXIMUM)
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
            or (marker.get('flagged') and (kind not in ('EIGHT_ATTEMPT_LIMIT','TWELVE_ATTEMPT_LIMIT','MODEL_BUDGET_LIMIT','KNOWN_NO_EFFECT','NOT_DISPATCHED') or not 5<=attempts<=limit))
            or (kind in ('EIGHT_ATTEMPT_LIMIT','TWELVE_ATTEMPT_LIMIT') and (attempts!=limit or kind!=limit_kind(limit)))
            or (marker.get('unverified_tail_dispatches',0)>0 and kind!='KNOWN_NO_EFFECT')):
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
