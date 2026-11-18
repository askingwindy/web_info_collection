"""策略 1 会话：banded conditional-plan ReAct 决策循环。

The strategy-1 decision layer on the shared engine core
(session_core.RawSessionCore): legacy decision protocol, native tool loop and
the conditional-plan controller band. Engine facts (task builders, budgets,
trusted observations, atomic dispatch, raw close-out) live in session_core and
are re-exported here for the existing strategy-1 import sites; 策略 2
(screenshot_plan) never loads this module's decision path.
"""
import asyncio
from copy import deepcopy
import hashlib
from webcollect import workspace_json as json
import time
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from .planning import object_sha256, verify_evidence
from .batch_core import file_sha, load_json, OutcomeUnknown, BudgetStop, SessionGLMCallLimit
from .agent_observation import project, require_action, PROVEN, ACTIONS, CONTROL_ACTIONS, VERSION as OBS_VERSION
from .agent_controller import exclusive, compile_step, DecisionRequestError, DecisionModelFault

from .plan_protocol import (REACT_SESSION_PROTOCOL, REACT_PROTOCOL, REFERENCE_PROTOCOL, EFFECTIVE_ACTION_RULE,
                            NAVIGATION_PROTOCOL, DELAYED_NAVIGATION_PROTOCOL, PLANNING_INTENT_PROTOCOL,
                            ENDING_POLICY, PLAN_PROTOCOL, WIKI_READING_COMPLETION, DIRECT_COMPLETION_PROTOCOL,
                            RESULT_EXECUTION_POLICY, RESULT_COMPLETION_PROTOCOL, NUMERIC_RESULT_EVIDENCE_POLICY,
                            TRUSTED_PREFIX_POLICY, ACTION_STABILITY_PROTOCOL, FRAGMENT_POLICY, READING_PLAN_COMPLETION_POLICY,
                            PLAN_EXECUTION_POLICY)
from .react_protocol import (VERSION as NATIVE_VERSION, SYSTEM as NATIVE_SYSTEM,
                             RULE_VERSION, REFERENCE_PROTOCOL, rule_sources, native_tools, native_decision, atomic_effect)

from .session_core import (RawSessionCore, REACT_VERSION, STOP_REASONS, INSPECT_KINDS,
                           SYSTEM_PROMPT, DEFAULT_BUDGETS, BUDGET_KEYS, GOAL_BUDGETS, RESERVE,
                           ALLOWED_TOOL_ACTIONS, _HTML_EXCERPT_CHARS, _INSPECT_MAX_CHARS,
                           REACT_OBSERVE_TIMEOUT_SECONDS, obj, TEXT, NULLABLE_TEXT, GOAL_UPDATE,
                           ACTION_ARGUMENTS, is_react_task, ReactStop, struct_goal, describe_goal,
                           validate_effort_profile, build_url_task, configure_candidate_protocols,
                           build_candidate_task, build_capability_task, validate_task,
                           compact_observation, compact_trajectory, _raw_files)

REACT_DECISION = obj({'goal_update': {'anyOf': [{'type': 'null'}, GOAL_UPDATE]},
                      'decision_summary': TEXT,
                      'tool_call': obj({'name': {'enum': ['observe', 'inspect', 'act', 'finish']},
                                        'arguments': {'type': 'object'}})})


def tool_definitions(allowed_actions):
    actions = [name for name in ALLOWED_TOOL_ACTIONS if name in allowed_actions]
    return {
        'observe': {'签名': 'observe(focus_control_id: string|null)',
            '用途': '同一会话只读读取当前页面，保存当前 HTML/DOM、截图与运行时属性；不点击、不导航、不计有效步数。',
            '关键用法': 'controls 中某控件的动作为 INSUFFICIENT/MISSING_TARGET_PROBE 时，用 focus_control_id 指向该控件做一次定向观察以取得可执行性证明；整页观察不提供控件探针。每个控件在同一文档下最多一次：若定向后仍 INSUFFICIENT，看 reason——MISSING_READABLE_LABEL_EVIDENCE 表示输入/选择缺渲染标签；点击可由当前节点/绑定/边界/命中证明，无文字不等于不能点击；重复 focus 会被直接拒绝。',
            '返回': '新 observation_id、页面摘要/HTML片段、控件三态与真实值、图片引用与覆盖说明。新观察使旧动作绑定失效。'},
        'inspect': {'签名': 'inspect(kind: "html"|"control"|"history"|"feedback", observation_id: string|null, '
                          'target_id: string|null, query: string|null, offset: integer>=0, limit_chars: integer>0)',
            '用途': '读取已保存材料。html/control 必须给 observation_id（control 另给 target_id）；history/feedback 可按引用或 query 文字匹配。'
                    '六个参数字段都必须提供（不需要的用 null），不接受未声明字段；query 只做文字匹配，找不到会被拒绝。',
            '返回': '实际命中 content_text、来源引用、next_offset（无下一段为 null）、截断/缺失说明。不改变当前页面，不将旧材料升级为当前可执行证据。'},
        'act': {'签名': 'act(observation_id: string, step: ActionStep)',
            'ActionStep公共必填': 'action、goal（本步操作目的）、expected（待验证变化）',
            '嵌套规则': 'arguments 顶层只有 observation_id 与 step 两个键；action/control_id/value/keys/direction/page_id '
                        '等所有动作字段必须嵌套在 step 对象内部，平铺在顶层会被直接拒绝。'
                        '例：{"observation_id":"当前观察id","step":{"action":"type","control_id":"e_3","value":"网络营销","goal":"输入检索词","expected":"输入框值变化"}}',
            '允许动作及额外必填参数': {name: ACTION_ARGUMENTS[name] for name in actions},
            '用途': '校验当前观察、目标、权限与预算后，把一个语义动作交给原执行器；按真实原子操作取证计数，动作后返回新观察或结构化错误。'
                    '旧观察不可派发；复合动作按实际原子操作分别计数。'},
        'finish': {'签名': 'finish(observation_id: string, stop_reason: "ready"|"no_path"|"budget"|"blocked", '
                         'summary: string)',
            '用途': '核对当前状态并关闭本次原始执行，保存收据。ready 只代表申请结束并进入加工，不代表业务完成或 QC PASS。',
            '说明': '短流程及原因由宿主按有效操作数生成，无需声明；自然完成即结束，不凑步。'},
    }



class ReactSession(RawSessionCore):
    """策略 1 决策循环宿主；引擎事实与原始执行收尾由 session_core 提供。"""

    def _make_plan_controller(self):
        from .banded_plan import enabled, Controller
        return Controller() if enabled(self.task) else None

    def _boundary_system_prompt_sha256(self):
        if self.plan_controller is None:
            return object_sha256(NATIVE_SYSTEM)
        from .banded_plan import system_for, system_with_attempt_limit
        from .closing_policy import attempt_limit, completed_goal_only
        return object_sha256(system_with_attempt_limit(system_for(self.task),
            attempt_limit(self.task), completed_goal_only(self.task)))

    def _boundary_tool_schema_sha256(self, contracted):
        if self.plan_controller is None:
            return object_sha256(native_tools(self.task['fragment']['allowed_actions'],
                self.task['fragment']['decision_protocol'],
                self.task['fragment'].get('reference_protocol')))
        from .banded_plan import tools as plan_tools
        from .closing_policy import attempt_limit
        from .direct_article import protocol_schema
        from .goal_evidence import contract_for
        return object_sha256(protocol_schema(plan_tools(contracted,
            pending_checks=bool(self.task['fragment'].get('plan_protocol')),
            max_steps=attempt_limit(self.task)), contract_for(self.task),
            max_steps=attempt_limit(self.task),
            wiki=__import__('webcollect.wiki_reading', fromlist=['enabled']).enabled(self.task)))
    async def _tool_inspect(self, arguments):
        from jsonschema import Draft202012Validator
        schema = obj({'kind': {'enum': list(INSPECT_KINDS)}, 'observation_id': NULLABLE_TEXT,
                      'target_id': NULLABLE_TEXT, 'query': NULLABLE_TEXT,
                      'offset': {'type': 'integer', 'minimum': 0},
                      'limit_chars': {'type': 'integer', 'exclusiveMinimum': 0,
                                      'maximum': _INSPECT_MAX_CHARS}})
        if self.task['fragment'].get('decision_protocol') == NATIVE_VERSION:
            from .react_protocol import inspect_schema
            schema = inspect_schema()
        try:
            Draft202012Validator(schema).validate(arguments)
            if any(value == 'null' for value in arguments.values()):
                raise ValueError('NULL_STRING: omit unused fields; string null is not a reference')
        except Exception as error:
            return self._rejected('inspect', 'inspect 参数不合法：' + str(error).splitlines()[0])
        arguments = {'observation_id': None, 'target_id': None, 'query': None,
                     'offset': 0, 'limit_chars': 2000, **arguments}
        self._consume('max_queries')
        kind, offset, limit = arguments['kind'], arguments['offset'], arguments['limit_chars']
        material, source = None, None
        if kind in ('html', 'control', 'search'):
            record = self.observation_records.get(arguments['observation_id'] or '')
            if record is None:
                return self._rejected('inspect', '未找到该观察；请使用当前观察 ID 或先 observe')
            source = record['observation_id']
            if kind == 'html':
                material = record['html']
            elif kind == 'search':
                query = arguments['query'].strip().casefold()
                def labels(row):
                    return [str(x).strip().casefold() for x in
                        [row['element'].get('text',''),*row.get('readable_labels',[])] if isinstance(x,str) and x.strip()]
                candidates={cid:row for cid,row in record['controls'].items() if not arguments.get('role') or
                    arguments['role'].casefold() in (str(row['element'].get('native_role','')).casefold(),
                        str(row['element'].get('element_type','')).casefold(),str(row['binding'].get('tag','')).casefold())}
                exact={cid:row for cid,row in candidates.items() if query in labels(row)}
                matches=exact or ({cid:row for cid,row in candidates.items() if any(query in label for label in labels(row))}
                                 if arguments.get('match')!='exact' else {})
                matches = [{'control_id':cid, 'label_hint':row['element'].get('text','')[:120],
                    'readable_labels':row['readable_labels'], 'bbox':row['element'].get('bbox'),
                    'actions':row['actions']} for cid,row in matches.items()]
                material = json.dumps(matches, ensure_ascii=False, sort_keys=True)
                if not matches:
                    return self._rejected('inspect', 'CONTROL_SEARCH_NO_MATCH: query 只填普通可见文字（如 R），不要含 text_hint、label_hint 或 JSON 标点；可去掉role或改contains。',
                        data={'source':source,'matches':0,'does_not_upgrade_actions':True,
                              'next_tool':{'name':'inspect','arguments':{'kind':'search','observation_id':source,
                                  'query':query.split('"')[-2] if '"' in query else query,'match':'contains'}}})
            else:
                control = record['controls'].get(arguments['target_id'] or '')
                if control is None:
                    return self._rejected('inspect', '该观察中没有此控件', data={'source': source})
                material = json.dumps(control, ensure_ascii=False, sort_keys=True)
        elif kind == 'pages':
            source = 'observed_pages'
            pages = [{'page_id':f'p{i}', 'url':url} for i,url in enumerate(self.page_urls)]
            if arguments['query']:
                pages = [row for row in pages if arguments['query'].casefold() in row['url'].casefold()]
            material = json.dumps(pages, ensure_ascii=False, sort_keys=True)
        elif kind == 'history':
            source = 'trajectory'
            if arguments['target_id']:
                row = next((r for r in self.trajectory if r['operation_id'] == arguments['target_id']), None)
                if row is None:
                    return self._rejected('inspect', '没有此历史动作引用')
                material = json.dumps(row, ensure_ascii=False, sort_keys=True)
            else:
                material = json.dumps(compact_trajectory(self.trajectory), ensure_ascii=False)
        else:
            source = 'site_feedback'
            avoid = deepcopy(self.context.get('actual_feedback', self.context).get('avoid', []))
            if arguments['target_id']:
                avoid = [row for row in avoid if arguments['target_id'] in json.dumps(row, ensure_ascii=False)]
            if arguments['query']:
                avoid = [row for row in avoid
                         if arguments['query'] in json.dumps(row, ensure_ascii=False)]
            material = json.dumps([{k: row.get(k) for k in ('operation', 'reason')} for row in avoid[:20]],
                                   ensure_ascii=False, sort_keys=True)
        if arguments['query'] and kind in ('html', 'control'):
            position = material.find(arguments['query'])
            if position < 0:
                return self._rejected('inspect', 'query 未命中该材料', data={'source': source})
            offset = position
        window = material[offset:offset + limit]
        html_hint = ('；仅 HTML 结构线索，未提升 actions。INSUFFICIENT 仍不能 act，'
                     'placeholder/aria-label 不等于可读标签证据。' if
                     kind == 'html' and self.task['fragment'].get('decision_protocol') == NATIVE_VERSION else '')
        return self._ok('inspect',
            summary=f'{kind} 片段 {len(window)} 字符（材料共 {len(material)} 字符）' + html_hint,
            data={'kind': kind, 'content_text': window, 'source': source, 'offset': offset,
                  **({'does_not_upgrade_actions':True, 'evidence_scope':'structure_only_not_readable_label'} if html_hint else {}),
                  'next_offset': (offset + limit) if offset + limit < len(material) else None,
                  'truncated': offset + limit < len(material), 'total_chars': len(material)})

    # ------------------------------------------------------------------ act


    async def _tool_finish(self, arguments):
        if self.native:
            return await self._native_finish(arguments)
        from jsonschema import Draft202012Validator
        try:
            # short_flow fields are accepted-but-ignored host facts; only the
            # finish identity fields are required (keyword: obj() takes no
            # second positional argument).
            Draft202012Validator(obj({'observation_id': TEXT,
                'stop_reason': {'enum': list(STOP_REASONS)}, 'summary': TEXT,
                'short_flow': {},
                'short_flow_reason': {}}, required=['observation_id','stop_reason','summary'])).validate(arguments)
        except Exception as error:
            return self._rejected('finish', 'finish 参数不合法：' + str(error).splitlines()[0])
        if arguments['observation_id'] != self.current['observation_id']:
            return self._rejected('finish', 'finish 必须绑定当前观察', data={
                'current_observation_id': self.current['observation_id']})
        effective = len(self.trajectory)
        if self._left('max_observations') >= 1:
            closing = await self._observe()
            final = self.current
        else:
            final = self.current
        self.state = 'finished'
        self.stop_reason = arguments['stop_reason']
        self.stop_summary = arguments['summary']
        from .postprocess import flow_classification
        self.short_flow, self.short_flow_reason = flow_classification(effective)
        receipt = self._close()
        return self._ok('finish', summary='原始执行已关闭：' + self.stop_reason,
                        data={'raw_receipt': receipt, 'effective_steps': effective,
                              'actual_actions': effective, 'stop_reason': self.stop_reason,
                              'short_flow': self.short_flow,
                              'final_observation_id': final['observation_id'],
                              'length_qualified': effective >= 5 or self.short_flow},
                        evidence_refs=[receipt['path']])


    async def _native_finish(self, arguments):
        from .closing_policy import completed_goal_only
        current_id = self.current['observation_id']
        submitted = deepcopy(arguments)
        reference = self.active_reference
        alias = reference['reference'] if reference else None
        if self.task['fragment'].get('reference_protocol') == REFERENCE_PROTOCOL and reference:
            if (reference['attempt_id'] == self.attempt_id and reference['observation_id'] == current_id
                    and reference['decision'] == self.used['max_decisions']):
                arguments = deepcopy(arguments)
                if arguments['observation_id'] == alias:
                    arguments['observation_id'] = current_id
                arguments['evidence_refs'] = [current_id if ref == alias else ref for ref in arguments['evidence_refs']]
        if (arguments['observation_id'] != current_id or current_id not in arguments['evidence_refs']
                or any(ref not in self.observations for ref in arguments['evidence_refs'])):
            corrected = {**arguments, 'observation_id':current_id, 'evidence_refs':[current_id]}
            suggestion = {'name':'finish', 'arguments':corrected}
            rejected = self._rejected('finish', 'finish 的 evidence_refs 仅接受原始观察 ID，请核对当前可见终态后使用返回的引用。',
                                      data={'next_tool':suggestion})
            if rejected['error'] is not None:
                rejected['error']['next_tool'] = suggestion
            return rejected
        if self._left('max_observations') >= 1:
            await self._observe()
        if self.plan_controller is not None and arguments['stop_reason']=='ready':
            result_complete=(getattr(self,'result_completion',None) and self.plan_controller.fact_progress(self).get('business_goal_status')=='VERIFIED')
            if not result_complete and not self.plan_controller.proved(self.plan_controller.plan['finish_when'],self):
                return self._rejected('finish','HOST_ENDPOINT_CHANGED: refreshed sealed final frame no longer proves finish_when')
        if completed_goal_only(self.task) and arguments['stop_reason']=='ready' and len(self.trajectory)<5:
            return self._rejected('finish','原目标即使已完成，实际1–4步也只保留内部记录，不能形成正式样本')
        if self.task['fragment'].get('ending_policy'):
            from .reading_progress import ending
            proof = ending(len(self.trajectory), load_json(self.current['evidence']['state']['path']))
            self.event('ending-evidence', **proof, final_observation_id=self.current['observation_id'])
            if arguments['stop_reason'] == 'ready' and self.trajectory and not proof['visible_terminal_material']:
                return self._rejected('finish','当前末帧缺少可核对的可见终态；第五步不能自动宣告成功', data=proof)
            if len(self.trajectory)>=2:
                from .reading_progress import same_view
                first,last=self.trajectory[-2:]
                origin=load_json(self.observation_records[first['before_observation_id']]['evidence']['state']['path'])
                end=load_json(self.observation_records[last['after_observation_id']]['evidence']['state']['path'])
                if first['action']==last['action']=='scroll' and same_view(origin,end):
                    raise ReactStop('blocked','READING_ROUND_TRIP: 两步原样往返尚无后续真实控件用途，保留原动作并拒收','collector')
        self.event('finish-basis', observation_id=current_id, evidence_refs=arguments['evidence_refs'],
                   final_observation_id=self.current['observation_id'], summary=arguments['summary'],
                   submitted_references={'observation_id':submitted['observation_id'], 'evidence_refs':submitted['evidence_refs']},
                   request_reference=reference)
        self.state = 'finished'
        self.stop_reason, self.stop_summary = arguments['stop_reason'], arguments['summary']
        if self._v2():
            original_stop=self.stop_reason
            self._range_close(('HOST_PLAN_ENDPOINT' if self.plan_controller else 'VISIBLE_GOAL_REPORTED') if original_stop=='ready' else 'AGENT_STOP',
                              arguments['summary'])
            self.stop_reason=original_stop
        self.short_flow = 0 < len(self.trajectory) < 5
        self.short_flow_reason = self._short_reason() if self.short_flow else None
        return self._ok('finish', summary='原始执行待封存：' + self.stop_reason,
                        data={'effective_steps': len(self.trajectory), 'actual_actions': self.used['max_actions'],
                              'stop_reason': self.stop_reason, 'short_flow': self.short_flow,
                              'final_observation_id': self.current['observation_id']})


    def _short_reason(self):
        from .postprocess import flow_classification
        return flow_classification(len(self.trajectory))[1]

    # ------------------------------------------------------------------ loop


    def _prompt(self):
        avoid = self.context.get('actual_feedback', self.context).get('avoid', [])
        result = {
            'protocol': REACT_VERSION,
            'system': NATIVE_SYSTEM,
            'entry_url': self.task['initial_url'],
            'requested_goal': deepcopy(self.requested_goal),
            'working_goal': deepcopy(self.working_goal),
            'observation': self._compact(self.current),
            'progress': {'effective_steps': len(self.trajectory),
                         'actual_actions': self.actual_dispatches,
                         'decisions_used': self.used['max_decisions'],
                         'summary': (f'已执行 {len(self.trajectory)} 个有效操作')},
            'trajectory': compact_trajectory(self.trajectory[-8:] if self.native else self.trajectory),
            'goal_updates': deepcopy(self.goal_updates[-4:] if self.native else self.goal_updates),
            'last_tool_result': self.last_tool_result,
            'recent_feedback': [{'reason': row.get('reason')} for row in avoid[:3]],
            'boundary': {'allowed_actions': self.task['fragment']['allowed_actions'],
                         'remaining_budgets': {k: self._left(k) if self.budgets[k] is not None else None for k in BUDGET_KEYS},
                         **({'budget_note':'remaining_budgets 中 null 表示该项没有累计上限。'} if None in self.budgets.values() else {}),
                         'observed_pages': [{'page_id': f'p{i}', 'url': url}
                                            for i, url in enumerate(self.page_urls) if not self.native or i < 24],
                         'page_coverage': {'shown':min(len(self.page_urls),24) if self.native else len(self.page_urls),
                            'total':len(self.page_urls), 'remaining_via':'inspect(kind=pages, query, offset)'}},
            'tools': (native_tools(self.task['fragment']['allowed_actions'], self.task['fragment']['decision_protocol'],
                    self.task['fragment'].get('reference_protocol'),self.task['fragment'].get('planning_intent_protocol'),
                    not getattr(self,'planning_intents',[])) if self.native
                      else tool_definitions(self.task['fragment']['allowed_actions'])),
            **({'_history': self.history} if self.native else {}),
            'output_requirement': '每轮恰一个原生工具调用' if self.native else '只输出一个 JSON 对象，顶层字段恰为 goal_update（可为 null）、'
                                  'decision_summary、tool_call（恰一个）',
        }

        if self.task['fragment'].get('decision_protocol') == NATIVE_VERSION:
            from .react_context import project as project_context, collection_facts
            result['collection_facts'] = deepcopy(self.context.get('collection_facts') or collection_facts())
            if self.active_reference:
                result['output_requirement'] += '；finish可用本请求request_observation_ref短引用，其他工具继续用原观察ID'
                result['request_observation_ref'] = self.active_reference['reference']
            result['progress']['counting_basis'] = '仅原子派发且效果已验证；observe/inspect与语义工具调用不计步'
            result['host_facts'] = {'actions': compact_trajectory(self.trajectory),
                'failed_tools': [event for event in getattr(self, 'failure_facts', [])],
                'unknown': self.unknown, 'glm_http_requests': self.glm_http_requests,
                'visited_pages': list(dict.fromkeys(o['url'] for o in self.observation_records.values()))}
            if self.task['fragment'].get('reading_progress_protocol'):
                from .reading_progress import project as reading, ending
                states = {oid:load_json(o['evidence']['state']['path']) for oid,o in self.observation_records.items()}
                result['reading_progress'] = reading(states, self.current['observation_id'], self.trajectory)
                result['ending_evidence'] = ending(len(self.trajectory), states[self.current['observation_id']])
            if self._v2():
                from .closing_policy import system_prompt,attempt_limit
                POLICY=self.task['fragment']['ending_policy']
                band=getattr(self.plan_controller,'frozen_band',None) if self.plan_controller else None
                limit=attempt_limit(self.task,band)
                result['system'] = system_prompt(result['system'],self.task)
                result['ending_evidence']={'protocol':POLICY,'business_attempts':len(getattr(self,'business_attempt_refs',[])),
                    'actual_atomic_dispatches':self.actual_dispatches,'verified_effective_steps':len(self.trajectory),
                    'unverified_tail_dispatches':self.actual_dispatches-len(self.trajectory),
                    'finish_counted_as_action':False,
                    'attempt_interval':None if limit is None else [5,limit]}
                result['reading_progress']['instruction']='按当前新正文与位置核对目标；达到目标就finish，不凑步；失败与未知结果照实保留。'
            if self.task['fragment'].get('planning_intent_protocol'):
                result['planning_basis']={'site_primary_category':self.task.get('site_category','UNKNOWN'),
                    'page_purpose':(self.task.get('candidate_binding') or {}).get('candidate',{}).get('page_purpose','UNKNOWN'),
                    'intent_history':getattr(self,'planning_intents',[])[-2:],
                    'instruction':'首轮task_intent按原目标、主类、有据用途与可信首帧建立类型意向及可见结束条件；用途UNKNOWN可先observe。只提交本轮一个下一工具。意向不是实际标签，不声明未执行的购买/对局。链接清单不是已访问正文。'}
            return project_context(result)
        return result


    def _strip_prompt(self, prompt):
        """Journal the prompt without duplicating the full system prompt body."""
        stripped = deepcopy({k: v for k, v in prompt.items() if k not in ('_history','_dispatch_deadline')})
        stripped['system'] = 'SHA256:' + object_sha256(prompt['system'])
        return stripped


    async def _round(self):
        dispatches_before = self.actual_dispatches
        effective_before = len(self.trajectory)
        try:
            await self._round_impl()
            if self.budgets['max_no_progress'] is None:
                return
            result = self.last_tool_result or {}
            stalled = result.get('status') in ('rejected', 'need_observation')
            if result.get('status') == 'ok':
                if self.native and result['tool'] in ('observe', 'inspect'):
                    # Paths and observation IDs change on capture even on an unchanged page.
                    signature = (self._probe_key(self.current), result['tool'],
                                 object_sha256(result.get('data')) if result['tool'] == 'inspect'
                                 else self.current['coverage'].get('focus_control_id'))
                    stalled = signature in self.read_evidence
                    self.read_evidence.add(signature)
                elif result['tool'] == 'act':
                    self.read_evidence.clear()
            self.no_progress = self.no_progress + 1 if stalled else 0
            if self.no_progress >= self.budgets['max_no_progress']:
                raise ReactStop('blocked', '连续无进展轮次达到上限', 'collector')
        except ReactStop as error:
            if self.native and self.pending_tool_call_id:
                from .react_protocol import effect_feedback
                self.last_tool_result = {'tool':'host', 'status':'stopped', 'summary':str(error),
                    'data':{'actual_actions_delta':self.actual_dispatches-dispatches_before,
                            'effect_status':'UNKNOWN' if self.unknown or error.unknown else 'NOT_ESTABLISHED',
                            'effective_steps_delta':len(self.trajectory)-effective_before,
                            'effects':[effect_feedback(row) for row in self.trajectory[effective_before:]],
                            'stop_reason':error.stop_reason, 'business_completion':'NOT_CLAIMED'}}
            raise
        finally:
            self.active_reference = None
            if self.native and self.pending_tool_call_id:
                result = deepcopy(self.last_tool_result) if self.last_tool_result else {
                    'tool': 'host', 'status': 'stopped', 'stop_reason': self.stop_reason,
                    'unknown': self.unknown, 'actual_actions': self.used['max_actions']}
                self.history.append({'role': 'tool', 'tool_call_id': self.pending_tool_call_id,
                                     'content': json.dumps(result, ensure_ascii=False, sort_keys=True)})
                self.pending_tool_call_id = None


    async def _round_impl(self):
        if self.plan_controller is not None:
            try:
                await self.plan_controller.round(self)
            except ValueError as error:
                self.event('plan-protocol-rejected',reason=str(error),actual_dispatches=self.actual_dispatches)
                raise ReactStop('blocked',str(error),'model') from error
            return
        from jsonschema import Draft202012Validator
        if self.native or self.glm_session_id:
            self._check_request_budget()
        if self.task['fragment'].get('reference_protocol') == REFERENCE_PROTOCOL:
            self.active_reference = {'reference': 'r_' + secrets.token_urlsafe(12),
                'attempt_id':self.attempt_id, 'observation_id':self.current['observation_id'],
                'decision':self.used['max_decisions'] + 1, 'boundary':self.binding}
            self.event('request-observation-reference', **self.active_reference)
        try:
            prompt = self._prompt()
        except ValueError as error:
            raise ReactStop('blocked', str(error), 'program') from error
        if self.host_limits and '_dispatch_deadline' not in prompt:
            # 策略1非计划分支同样执行会话软时限：软时限后不再发起新的模型请求。
            prompt['_dispatch_deadline'] = (self.host_limits['started_monotonic']
                                            + self.host_limits['soft_seconds'])
        self._last_model_intent=self.event('model-intent', prompt=self._strip_prompt(prompt))
        self._consume('max_decisions')
        if not self.native:
            self._consume('max_model_calls')
        try:
            with self._phase('model_wait', decision=self.used['max_decisions']):
                decision = await self.choose(prompt)
        except SessionGLMCallLimit:
            raise
        except BudgetStop as error:
            raise ReactStop('budget', str(error)) from error
        except DecisionRequestError as error:
            if self.glm_session_id and isinstance(error, DecisionModelFault):
                self._check_request_budget()
            raise ReactStop('blocked', str(error),
                            'program' if error.stage == 'local_preflight' else 'model') from error
        except OutcomeUnknown as error:
            self.unknown = True
            raise ReactStop('blocked', '决策请求结果未知，保留 UNKNOWN 不重发：' + str(error),
                            'interrupted', unknown=True) from error
        except ReactStop:
            raise
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            self.unknown = True
            raise ReactStop('blocked', type(error).__name__ + ': ' + str(error),
                            'interrupted', unknown=True) from error
        finally:
            counter = getattr(self.choose, 'requests_used', None)
            if counter is not None and (self.native or self.glm_session_id):
                used = counter()
                if self.native:
                    self.used['max_model_calls'] = used
                if self.glm_session_id:
                    self.glm_http_requests = used
        if self.native:
            response = decision
            try:
                decision = native_decision(response, prompt['tools'], self.tool_call_ids)
            except Exception as error:
                self._consume('max_replans')
                self.last_tool_result = self._rejected('protocol', 'NATIVE_PROTOCOL: ' + str(error).splitlines()[0])
                self.event('decision-rejected', reason=self.last_tool_result['summary'])
                return
            cid = response['tool_call_id']
            intent=response['arguments'].get('task_intent')
            if intent is not None:
                if intent['basis_observation_id'] != self.current['observation_id'] or (intent['status']=='GROUNDED' and not intent['task_types']):
                    self.last_tool_result=self._rejected('protocol','task_intent 必须引用当前观察；缺类型依据请用UNKNOWN')
                    self.event('intent-rejected',intent=intent)
                    return
                if not hasattr(self,'planning_intents'):self.planning_intents=[]
                self.planning_intents.append(deepcopy(intent))
                self.event('planning-intent',intent=intent)
            self.tool_call_ids.add(cid)
            self.history.extend([deepcopy(response['user_message']), deepcopy(response['assistant_message'])])
            self.pending_tool_call_id = cid
            self.last_tool_result = None
        try:
            Draft202012Validator(REACT_DECISION).validate(decision)
        except Exception as error:
            self._consume('max_replans')
            self.last_tool_result = self._rejected(decision.get('tool_call', {}).get('name', 'unknown')
                                                   if isinstance(decision, dict) else 'unknown',
                '决策 JSON 不符合协议：' + str(error).splitlines()[0])
            self.event('decision-rejected', response=decision, reason=str(error))
            return
        self._last_decision=self.event('decision', decision={'goal_update': decision['goal_update'],
            'decision_summary': decision['decision_summary'],
            'tool_call': decision['tool_call']})
        self.last_decision_summary = decision['decision_summary']
        update = decision['goal_update']
        if update is not None:
            if update['basis_observation_id'] != self.current['observation_id']:
                self._consume('max_replans')
                self.last_tool_result = self._rejected(decision['tool_call']['name'],
                    'goal_update 必须引用当前观察（' + self.current['observation_id'][:12] + '）')
                self.event('goal-update-rejected', update=update)
                return
            self.working_goal = update['description']
            self.goal_updates.append({**deepcopy(update), 'applied_at_decision': self.used['max_decisions']})
            self.event('goal-update', update=update)
        name = decision['tool_call']['name']
        arguments = decision['tool_call'].get('arguments') or {}
        if name == 'observe':
            from jsonschema import Draft202012Validator as V
            try:
                V(obj({'focus_control_id': NULLABLE_TEXT})).validate(arguments)
            except Exception as error:
                self._consume('max_replans')
                self.last_tool_result = self._rejected('observe', 'observe 参数不合法：' + str(error).splitlines()[0])
                return
            result = await self._observe(arguments['focus_control_id'])
        elif name == 'inspect':
            result = await self._tool_inspect(arguments)
        elif name == 'act':
            result = await self._tool_act(arguments)
        elif name == 'finish':
            result = await self._tool_finish(arguments)
        else:
            self._consume('max_replans')
            result = self._rejected(name, '未知工具')
        self.last_tool_result = {k: result[k] for k in ('tool', 'status', 'observation_id', 'summary')}
        self.last_tool_result['data'] = {k: result['data'][k] for k in result['data']
                                         if k not in ('observation',)}
        self.event('tool-result', result=result)


    async def run(self):
        """Frozen historical strategy; no live entry or model dispatch."""
        from .collection_strategy import Strategy1Forbidden
        raise Strategy1Forbidden()
        stop = None
        try:
            if self.native or self.glm_session_id:
                self._check_request_budget()
            await self._open_entry()
            while self.state == 'recording':
                if self._left('max_seconds') <= 0:
                    self.stop_reason, self.stop_summary = 'budget', '宿主时间预算耗尽，保留已执行内容'
                    self.state = 'closed_by_host'
                    break
                await self._round()
        except SessionGLMCallLimit as error:
            self.stop_details = error.details
            self.stop_reason, self.stop_summary = 'budget', str(error)
            self.state = 'closed_by_host'
        except ReactStop as error:
            stop = error
            if self.stop_reason is None:
                self.stop_reason = error.stop_reason
                self.stop_summary = error.reason
                self.failure_class = error.failure_class
                self.unknown = self.unknown or error.unknown
            self.state = 'closed_by_host'
        except asyncio.CancelledError as error:
            self.stop_reason, self.stop_summary = 'blocked', '会话被取消，保留已执行内容'
            self.strategy_end_reason = ('unknown' if error.args and error.args[0] == 'consumer_session_hard_deadline'
                                        else 'user_stopped')
            self.unknown = True
            self.failure_class = 'interrupted'
            self.state = 'closed_by_host'
            if not (self.host_limits and time.monotonic() >= self.host_limits['started_monotonic'] + self.host_limits['hard_seconds']):
                self._close()
                raise
            # Only the bounded consumer deadline can resume prefix close-out.
            # User/manual cancellation is propagated below by its explicit cause.
            if not error.args or error.args[0] != 'consumer_session_hard_deadline':
                self._close()
                raise
        except BaseException as error:
            stop = ReactStop('blocked', type(error).__name__ + ': ' + str(error), 'program')
            self.stop_reason, self.stop_summary = 'blocked', str(stop)
            self.failure_class = 'program'
            self.state = 'closed_by_host'
        self.host_failure = stop is not None
        receipt = self._close()
        summary = {'host_failure':self.host_failure, 'stop_reason': self.stop_reason, 'stop_summary': self.stop_summary,
                'strategy_end_reason': getattr(self, 'strategy_end_reason', None),
                **({'collection_ending':self.collection_ending} if self._v2() else {}),
                **({'stop_details': self.stop_details} if self.stop_details else {}),
                'failure_class': self.failure_class, 'unknown': self.unknown,
                'effective_steps': len(self.trajectory), 'actual_actions': self.actual_dispatches,
                'short_flow': self.short_flow, 'short_flow_reason': self.short_flow_reason,
                'raw_receipt': receipt,
                'terminal': {'path': str(self.root / 'terminal.json'),
                             'sha256': file_sha(self.root / 'terminal.json')}}
        from .collection_strategy import strategy_result
        summary['strategy_result'] = strategy_result(self.task, summary=summary, raw_receipt=receipt)
        return summary

    # ------------------------------------------------------------------ records for postprocess



def _image_part_sha(part):
    """SHA of one history image part's decoded payload; None if not a data URL."""
    import base64 as _b64
    url = (part.get('image_url') or {}).get('url') or ''
    marker = ';base64,'
    if not url.startswith('data:') or marker not in url:
        return None
    try:
        return hashlib.sha256(_b64.b64decode(url.split(marker, 1)[1], validate=False)).hexdigest()
    except (ValueError, TypeError):
        return None


def dedupe_history_images(history, *, extra_images=1, max_images):
    """Collapse duplicate-SHA history images, then oldest-truncate to budget.

    Within one outgoing request an identical image (same SHA) never occupies a
    second image slot: every older duplicate becomes a text reference with its
    hash prefix; different hashes stay. Afterwards the oldest remaining images
    beyond the budget (current-frame images are counted via extra_images)
    become text references too. Original messages are copied, never mutated.
    """
    history = deepcopy(history)
    images = [part for message in history if message.get('role') == 'user'
              and isinstance(message.get('content'), list) for part in message['content']
              if isinstance(part, dict) and part.get('type') == 'image_url']
    latest = {}
    for part in images:
        digest = _image_part_sha(part)
        if digest is not None:
            latest[digest] = part
    for part in images:
        digest = _image_part_sha(part)
        if digest is not None and part is not latest[digest]:
            part.clear()
            part.update(type='text',
                        text='该轮与后续某轮截图内容相同（sha256 前缀 ' + digest[:12] + '），已由最新一轮图片代表，此处省略重传。')
    remaining = [part for message in history if message.get('role') == 'user'
                 and isinstance(message.get('content'), list) for part in message['content']
                 if isinstance(part, dict) and part.get('type') == 'image_url']
    excess = max(0, len(remaining) + extra_images - max_images)
    for part in remaining[:excess]:
        part.clear()
        part.update(type='text', text='该轮截图已保存在原观察记录中，本次请求省略重传。')
    return history


def react_chooser(ledger, task, attempt_id, *, parent_job=None):
    """Frozen historical chooser; original request identities remain read-only."""
    from .collection_strategy import Strategy1Forbidden
    raise Strategy1Forbidden()
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise ValueError('Original ReAct attempt identity required')

    def usage():
        with ledger.connect() as con:
            return ledger.session_http_usage(con, attempt_id)

    def guard_unresolved():
        pending = usage()['unresolved']
        if pending:
            raise OutcomeUnknown('Original attempt has an unresolved request; no new dispatch: ' + pending)

    if task['fragment'].get('decision_protocol') == NATIVE_VERSION:
        from .collection_strategy import enabled as _screenshot_task
        if _screenshot_task(task):
            # 策略 2 owns its submit_plan/plan_decision wire protocol; it must
            # not inherit the conditional-plan branch schema or band gates.
            from .screenshot_plan import screenshot_chooser
            choose = screenshot_chooser(ledger, task, attempt_id, parent_job=parent_job)
            choose.session_usage = usage
            choose.requests_used = lambda: usage()['used']
            choose.guard_unresolved = guard_unresolved
            choose.glm_session_id = attempt_id if ledger.real_glm else None
            return choose
        choose = _native_chooser(ledger, task, attempt_id, guard_unresolved, parent_job=parent_job)
    else:
        choose = _legacy_chooser(ledger, task, attempt_id, parent_job=parent_job)
    choose.session_usage = usage
    choose.requests_used = lambda: usage()['used']
    choose.guard_unresolved = guard_unresolved
    choose.glm_session_id = attempt_id if ledger.real_glm else None
    return choose


def _legacy_chooser(ledger, task, attempt_id, *, parent_job=None):
    from .model_gateway import ModelGateway
    gateway = None

    async def choose(prompt):
        nonlocal gateway
        payload = {'protocol': REACT_VERSION, 'attempt_id': attempt_id, 'task_id': task['task_id'],
                   'site_uri': task['site_uri'], 'prompt_sha256': object_sha256({k:v for k,v in prompt.items() if k != '_dispatch_deadline'}),
                   'decision': prompt['progress']['decisions_used']}
        if parent_job is not None:
            payload['parent_job_id'] = parent_job['id']
        jid = ledger.enqueue('react-decision', payload)
        old = ledger.get(jid)
        if old['state'] != 'queued':
            raise ValueError('Original decision request unresolved/consumed; do not resend')
        try:
            job = ledger.claim('react-decision', job_id=jid,
                               **({'parent_job': parent_job} if parent_job is not None else {}))
        except ValueError as error:
            from .agent_controller import _job_request_count
            if _job_request_count(ledger, jid):
                raise OutcomeUnknown('Original decision claim has request records; reconcile') from error
            with ledger.transaction() as con:
                changed = con.execute(
                    "UPDATE jobs SET state='failed',error=? WHERE id=? AND state='queued' AND attempts=0",
                    ('local-claim:' + type(error).__name__, jid)).rowcount
                if changed:
                    ledger.event(con, 'react_decision_local_claim_failure',
                                 {'job_id': jid, 'reason': str(error), 'requests_sent': 0})
            if not changed:
                raise OutcomeUnknown('Decision claim ownership unresolved') from error
            raise DecisionRequestError('Local decision claim failed before any request: ' + str(error)) from error
        if not job:
            raise ValueError('Original decision could not be claimed')
        images = [prompt['observation']['image_ref']]
        try:
            import json as _json
            # Provider-side structured output: the decision object is the forced
            # native function-call arguments (official GLM function-calling
            # support includes glm-5.3-flash). Content JSON stays as fallback.
            decision_tool = {'type': 'function', 'function': {
                'name': 'react_decision',
                'description': '输出本轮 ReAct 决策：goal_update（可为 null）、'
                               'decision_summary、恰一个 tool_call',
                'parameters': REACT_DECISION}}
            # Three bounded attempts absorb repeated non-JSON format lapses;
            # both requests are reserved, billed and retained in the ledger.
            if gateway is None:
                gateway = ModelGateway(ledger)
            response = await asyncio.to_thread(gateway.call, job, REACT_VERSION,
                _json.dumps({k: v for k, v in prompt.items() if k != '_dispatch_deadline'},
                            ensure_ascii=False), REACT_DECISION,
                images=list(dict.fromkeys(images)), attempts=3,
                output_limit=min(4096,ledger.config['model']['max_completion_tokens']),
                tools=[decision_tool], tool_choice={'type': 'function',
                    'function': {'name': 'react_decision'}})
            ledger.finish(job, result=response)
            return response
        except OutcomeUnknown as error:
            ledger.finish(job, 'review_required', error='unknown:' + type(error).__name__)
            raise
        except SessionGLMCallLimit as error:
            ledger.finish(job, 'failed', error='budget:' + error.code)
            raise
        except ValueError as error:
            from .agent_controller import _job_request_count
            if _job_request_count(ledger, job['id']):
                ledger.finish(job, 'failed', error='settled:' + type(error).__name__)
                raise DecisionModelFault('Definite failed model response (request settled, no resend): '
                                         + str(error)) from error
            ledger.finish(job, 'failed', error='local:' + type(error).__name__)
            raise DecisionRequestError('Local decision preflight failed before any request: '
                                       + str(error)) from error
        except BaseException as error:
            ledger.finish(job, 'review_required', error=type(error).__name__)
            raise
    return choose


def _native_chooser(ledger, task, attempt_id, guard_unresolved, *, parent_job=None):
    """Original attempt identity, tool history and actual HTTP dispatch accounting."""
    from .model_gateway import ModelGateway
    from .agent_controller import _job_request_count
    from .goal_evidence import contract_for
    from .plan_protocol import PLAN_PROTOCOL, WIKI_READING_COMPLETION, DIRECT_COMPLETION_PROTOCOL
    gateway = None  # Cached/UNKNOWN paths do not select or read an account.
    protocol = task['fragment']['decision_protocol']
    plan_protocol = task['fragment'].get('plan_protocol')
    grounded = bool(contract_for(task))
    # Conditional-plan sessions dispatch explicit low effort for the first plan
    # and ordinary branches. A frozen per-task reasoning effort profile
    # overrides this: it is the task's own dispatch contract.
    first_plan_effort = 'max'
    branch_effort = 'max'
    effort_profile = task['fragment'].get('reasoning_effort_profile')
    if effort_profile:
        first_plan_effort = effort_profile['first_plan']
        branch_effort = effort_profile['branch']
    elif ledger.real_glm and plan_protocol == PLAN_PROTOCOL:
        first_plan_effort = 'low'
        branch_effort = 'low'
    request_limit = None

    async def choose(prompt):
        nonlocal gateway
        # Hash the full wire prefix, including opaque protocol fields, without
        # putting those fields in ordinary prompt journals or annotations.
        payload = {'protocol': protocol, 'attempt_id': attempt_id, 'task_id': task['task_id'],
                   'site_uri': task['site_uri'], 'prompt_sha256': object_sha256({k:v for k,v in prompt.items() if k != '_dispatch_deadline'}),
                   'decision': prompt['progress']['decisions_used']}
        if parent_job is not None:
            payload['parent_job_id'] = parent_job['id']
        jid = ledger.enqueue('react-native-decision', payload)
        old = ledger.get(jid)
        if old['state'] == 'done' and old.get('result') is not None:
            # Only this exact settled original request may be reused.
            return deepcopy(old['result'])
        if old['state'] != 'queued' or old['attempts']:
            with ledger.connect() as con:
                states = [row[0] for row in con.execute(
                    'SELECT state FROM model_requests WHERE job_id=?', (jid,))]
            if (old['state'] == 'running' or (old['state'] == 'review_required' and states)
                    or any(state in ('reserved', 'unknown') for state in states)):
                raise OutcomeUnknown('Original native request unresolved; reconcile before retry')
            # Preserve the original failure classification without reclaiming
            # this job or issuing another HTTP request under its identity.
            if old.get('error') == 'budget:' + SessionGLMCallLimit.code:
                with ledger.connect() as con:
                    used = ledger.session_http_usage(con, attempt_id)['used']
                raise SessionGLMCallLimit(attempt_id, used)
            if (old.get('error') or '').startswith('budget:'):
                raise BudgetStop('Original native decision exhausted its request/run budget')
            if states:
                raise DecisionModelFault('Original native decision has a settled failure; no automatic resend')
            raise DecisionRequestError('Original native decision failed before any request; no automatic resend')
        guard_unresolved()
        try:
            job = ledger.claim('react-native-decision', job_id=jid,
                               **({'parent_job': parent_job} if parent_job is not None else {}))
        except BudgetStop:
            raise
        except ValueError as error:
            if _job_request_count(ledger, jid):
                raise OutcomeUnknown('Original decision claim has request records; reconcile') from error
            raise DecisionRequestError('Native claim failed before any request: ' + str(error)) from error
        if not job:
            raise DecisionRequestError('Native decision could not be claimed')
        try:
            if gateway is None:
                gateway = ModelGateway(ledger)
            user_payload = {key: value for key, value in prompt.items()
                            if key not in ('system', 'tools', '_history', '_images', '_dispatch_deadline')}
            if prompt.get('protocol') == PLAN_PROTOCOL:
                user_payload=deepcopy(user_payload)
                user_payload['observation'].pop('image_ref',None)
                user_payload['observation'].pop('_node_scope',None)
            history = deepcopy(prompt.get('_history', []))
            if ledger.real_glm:
                # Keep the current PNG and most recent historical images in this
                # outgoing message. Original journal, requests and tool IDs stay
                # intact; identical images never consume a second image slot.
                history = dedupe_history_images(history, extra_images=1,
                                                max_images=ledger.config['model']['max_images'])
            if prompt.get('protocol') == PLAN_PROTOCOL:
                text_payload = json.dumps(user_payload, ensure_ascii=False, sort_keys=True)
                if prompt['phase'] == 'first':
                    effort = first_plan_effort
                else:
                    effort = branch_effort
                common = dict(system=prompt['system'], images=(prompt.get('_images') or [prompt['observation']['image_ref']])[-ledger.config['model']['max_images']:],
                    attempts=2, output_limit=ledger.config['model']['max_completion_tokens'],
                    reasoning_effort=effort,
                    attempt_id=attempt_id, max_requests=request_limit, dispatch_deadline=prompt.get('_dispatch_deadline'))
                if prompt['phase'] == 'first':
                    patient = ledger.real_glm
                    first_timeout = None
                    if patient:
                        first_timeout = choose.first_plan_timeout_seconds
                    else:
                        first_timeout = min(300, ledger.config['budget']['lease_seconds'] - 10)
                    response = await asyncio.to_thread(gateway.call_tool, job, prompt['protocol'],
                        text_payload, prompt['tools'], inference=True, timeout_seconds=first_timeout, patient_first_plan=patient, content_plan_protocol='strict-plan-content', **common)
                else:
                    from .banded_plan import choice_schema
                    from .direct_article import protocol_schema
                    wiki_completion = (prompt.get('wiki_reading_completion_protocol')
                                       == WIKI_READING_COMPLETION)
                    completion = (prompt.get('direct_completion_protocol') == DIRECT_COMPLETION_PROTOCOL
                                  or wiki_completion)
                    from .closing_policy import attempt_limit
                    branch_limit=attempt_limit(task)
                    # V9 ordinary branches use the same choice wire protocol as
                    # grounded branches; V8 and older keep their original form.
                    branch_schema=protocol_schema(choice_schema(grounded, inherited=True, wire=True, max_steps=branch_limit),prompt.get('evidence_contract'),completion=completion,max_steps=branch_limit,wiki=wiki_completion)
                    from .banded_plan import strip_v13_wire
                    branch_schema=strip_v13_wire(branch_schema,wiki=wiki_completion)
                    response = await asyncio.to_thread(gateway.call_message, job, prompt['protocol'],
                        text_payload, branch_schema, grounded_choice=True, content_envelope='single-json-commentary', **common)
                ledger.finish(job, result=response)
                return response
            response = await asyncio.to_thread(gateway.call_tool, job, protocol,
                json.dumps(user_payload, ensure_ascii=False, sort_keys=True), prompt['tools'],
                system=prompt['system'], history=history,
                images=[prompt['observation']['image_ref']], attempts=2,
                output_limit=ledger.config['model']['max_completion_tokens'],
                reasoning_effort='max', attempt_id=attempt_id, max_requests=request_limit, dispatch_deadline=prompt.get('_dispatch_deadline'))
            ledger.finish(job, result=response)
            return response
        except OutcomeUnknown as error:
            ledger.finish(job, 'review_required', error='unknown:' + type(error).__name__)
            raise
        except BudgetStop as error:
            ledger.finish(job, 'failed', error='budget:' + (error.code if isinstance(error, SessionGLMCallLimit) else type(error).__name__))
            raise
        except ValueError as error:
            with ledger.connect() as con:
                unresolved=[row['id'] for row in con.execute("SELECT id,state FROM model_requests WHERE job_id=? AND state IN ('reserved','unknown')",(job['id'],))
                    if row['state']=='reserved' or not ledger.timeout_retry_answered(con,row['id'])]
            if unresolved:
                # A local lease error cannot turn an already-dispatched UNKNOWN
                # into a settled model fault or authorize a replacement request.
                raise OutcomeUnknown('Original decision HTTP unresolved after '+type(error).__name__+': '+','.join(unresolved)) from error
            sent = _job_request_count(ledger, job['id'])
            ledger.finish(job, 'failed', error=('settled:' if sent else 'local:') + type(error).__name__)
            if sent:
                raise DecisionModelFault('Settled native protocol/request failure: ' + str(error)) from error
            raise DecisionRequestError('Native preflight failed before any request: ' + str(error)) from error
        except BaseException as error:
            ledger.finish(job, 'review_required', error=type(error).__name__)
            raise

    choose.request_limit = request_limit
    choose.first_plan_reasoning_effort = first_plan_effort
    choose.first_plan_timeout_seconds = 600 if plan_protocol == PLAN_PROTOCOL and ledger.real_glm else None
    choose.branch_reasoning_effort = branch_effort
    return choose
