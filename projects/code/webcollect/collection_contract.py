"""冻结业务目标、显式范围与业务依赖；未来观察步骤不属于业务合同。
真实结果来源、输入因果和结束展示由实际执行证据核验。
"""
import re
from copy import deepcopy

BUSINESS_MINIMUM = 5
NON_BUSINESS_ACTIONS = ('wait',)
RESULT_KINDS = ('calculation', 'navigation', 'input_conversion')
KIND_SOURCE_TYPES = {'input': ('input_state',), 'result': ('page_result',),
                     'content': ('page_content', 'derived_check')}

# Only an explicit independent-derivation obligation demands arithmetic.
# Confirming the page's own output (“核对结果”/“核对”) is a page_result duty:
# 计算/核对 words alone must not turn page confirmation into manual arithmetic.
DERIVATION_OBLIGATION = re.compile(
    r'验算|复算|重算|推导|手动换算|手算|独立(?:计算|验算|核对|推导)|自行(?:计算|验算)|'
    r'交叉验证|计算过程|recomput|cross.?check|re-?derive|deriv', re.I)


def _flat(text):
    return re.sub(r'\s+', '', str(text or ''))


def _explicit_result_terms(goal):
    """Return explicit output lists, including an unambiguous two-output ``A与B``."""
    # A reading list names questions/sections, not calculator outputs. Requiring
    # `result` here would then demand input/submission for a read-only article.
    if (re.search(r'阅读|閱讀|文章|条目|條目|正文', str(goal or ''))
            and not re.search(r'输入|輸入|填写|填寫|设置|設置|修改|提交|计算器|計算器|转换器|求解器', str(goal or ''))):
        return []
    for clause in re.split(r'[。；;]', str(goal or '')):
        # Literal field-name admission is sound only for an explicit output
        # list ending in 结果/输出. Shared nouns (年度与月度账单) and comparative
        # prose do not define literal labels that descriptions must reproduce.
        if not re.search(r'(?:结果|输出)[。！？!?.]*$', clause.strip()):
            continue
        if re.search(r'对比|比较|比較|哪个|哪個|哪种|哪種', clause):
            continue
        enumerated = '、' in clause
        if not re.search(r'结果|输出|查看|读取', clause):
            continue
        if not enumerated and len(re.findall('与', clause)) != 1:
            continue
        head = clause.split('结果', 1)[0]
        if '输出' in head:
            tail = head.rsplit('输出', 1)[1]
        elif re.search(r'查看|读取', head):
            tail = re.split(r'查看|读取', head)[-1]
        else:
            continue
        tail = re.sub(r'^(?:的|页面|计算)+', '', tail)
        # “收入与支出比”是一个指标名，不是两个独立输出；显式顿号列表除外。
        if not enumerated and re.search(r'(?:比|比例|比率|比值)$', tail):
            continue
        parts = re.split(r'、|以及|与|和|及', tail)
        terms = [part.strip(' \t\r\n，,：:「」“”') for part in parts]
        if len(terms) >= 2 and all(2 <= len(term) <= 30 for term in terms):
            return list(dict.fromkeys(terms))
    return []


def result_requirements_feedback(requirements, goal):
    result_terms = _explicit_result_terms(goal)
    if result_terms:
        result_rows = [row for row in requirements if row.get('kind') == 'result']
        coverage = {term: [row['id'] for row in result_rows
                           if term in str(row.get('description') or '')] for term in result_terms}
        compound = sorted({rid for rows in coverage.values() for rid in rows
                           if sum(rid in matches for matches in coverage.values()) > 1})
        missing = [term for term, rows in coverage.items() if not rows]
        if compound or missing:
            return {'kind': 'RESULT_REQUIREMENT_ATOMICITY',
                           'field_paths': ['requirements'], 'requirement_ids': compound,
                           'missing_result_terms': missing,
                           'message': '原目标明确列举的每个输出字段必须各用一个result事项，description保留原字段名；不得合并或漏列',
                           'dispatched': False}
    return None


def requirement_scope_feedback(requirements, goal):
    """Reject determinable extra obligations and mutually exclusive final inputs."""
    states = {}
    for row in requirements:
        if row.get('kind') != 'input' or row.get('evidence_scope') != 'current':
            continue
        target = row.get('target') or {}
        identity = target.get('control') or target.get('node') or tuple(
            (key, target[key]) for key in ('text', 'role', 'href') if target.get(key))
        if not identity:
            continue
        expected = ('value', row['expected_value']) if 'expected_value' in row else ('checked', row.get('expected_checked'))
        if identity in states and states[identity][1] != expected:
            return {'kind': 'INCOMPATIBLE_FINAL_INPUTS', 'field_paths': ['requirements'],
                'requirement_ids': [states[identity][0], row['id']], 'dispatched': False,
                'message': '同一控件不能同时保留两个互斥最终值；互斥阶段须在首轮明确historical并保留真实阶段动作及捕获，不得把两个互斥值都声明为current'}
        states[identity] = (row['id'], expected)
    definition = r'定义|定義|含义|含義|概念|何谓|何謂|是什么|是什麼'
    if not re.search(definition, str(goal or '')):
        extra = [row['id'] for row in requirements if row.get('kind') == 'content'
                 and re.search(r'(?:词条|詞條|条目|條目)?.{0,20}(?:定义|定義)', str(row.get('description') or ''))]
        if extra:
            return {'kind': 'UNREQUESTED_READING_OBLIGATION', 'field_paths': ['requirements'],
                'requirement_ids': extra, 'dispatched': False,
                'message': '条目访问是原目标的路径，不能额外冻结原目标未要求的定义事项；只保留原问题必需的原子事实'}
    return None


def _dependency_cycles(requirements):
    """Transitive depends_on cycles; self-reference is reported separately."""
    graph = {row['id']: [dep for dep in (row.get('evidence_route') or {}).get('depends_on', [])]
             for row in requirements if isinstance(row, dict)}
    cycles = []
    for start in graph:
        walked, stack = set(), [start]
        while stack:
            node = stack.pop()
            for dep in graph.get(node, []):
                if dep == start:
                    cycles.append(start)
                elif dep in graph and dep not in walked:
                    walked.add(dep)
                    stack.append(dep)
    return sorted(set(cycles))


def evidence_route_gaps(plan, session=None, *, require_explicit_scope=False):
    """Validate an intended route, never grant completion for future steps.

    依赖只表达真实业务关系；普通历史事实不新增结束保持义务。
    """
    requirements, steps = plan.get('requirements', []), plan.get('steps', [])
    ids = {r['id'] for r in requirements}
    gaps = []
    if len(ids) != len(requirements):
        gaps.append('重复事项编号')
    if plan.get('final_requirement_ids') is not None:
        final_ids = plan['final_requirement_ids']
        if (not final_ids or len(final_ids) != len(set(final_ids)) or not set(final_ids) <= ids):
            gaps.append('final_requirement_ids须非空、唯一且引用冻结事项')
        meaningful = {r['id'] for r in requirements if r['kind'] in ('result', 'content')}
        if meaningful and not meaningful.intersection(final_ids):
            gaps.append('final_requirement_ids不能只展示输入而逃开结果或正文结论')
    dependencies = set()
    for requirement in requirements:
        route = requirement.get('evidence_route') or {}
        scope = requirement.get('evidence_scope')
        if scope is not None and scope not in ('current', 'historical'):
            gaps.append(requirement['id'] + ':未知证据时态')
        if requirement.get('result_kind') is not None and requirement['result_kind'] not in RESULT_KINDS:
            gaps.append(requirement['id'] + ':未知结果类型')
        kind = route.get('source_type')
        if kind is not None and kind not in KIND_SOURCE_TYPES[requirement['kind']]:
            gaps.append(requirement['id'] + ':来源类型与事项不符')
        depends = set(route.get('depends_on', []))
        if not depends <= ids or requirement['id'] in depends:
            gaps.append(requirement['id'] + ':依赖未知事项或自身')
        if kind == 'derived_check':
            dependencies.update(depends)
            if not depends:
                gaps.append(requirement['id'] + ':推导核对缺少依赖事项')
        if session is not None:
            for anchor in route.get('existing_evidence', []):
                oid = anchor['observation']
                observation = session.observation_records.get(oid)
                if not observation or oid not in session.provided_observations or not observation.get('capture_verified'):
                    gaps.append(requirement['id'] + ':已有依据不是实际提供的可信观察')
                    continue
                state = _state_for_observation(session, oid)
                region = next((r for r in session.region_registries.get(oid, []) if r['region_id'] == anchor.get('region')), None)
                if (anchor.get('control') not in observation.get('provided_control_ids', [])
                        and region is None and not (anchor.get('quote') and _flat(anchor['quote']) in _flat(state.get('visible_text', '')))):
                    gaps.append(requirement['id'] + ':已有依据锚点无效')
    for start in _dependency_cycles(requirements):
        gaps.append(start + ':depends_on依赖成环，阶段依赖必须是先后无环的业务顺序')
    return gaps


def _state_for_observation(session, oid):
    from .batch_core import load_json
    observation = session.observation_records.get(oid)
    if not observation or observation.get('capture_verified') is not True:
        return None
    return load_json(observation['evidence']['state']['path'])


def first_plan_admission(plan, *, minimum=BUSINESS_MINIMUM, goal='',
                         wire_schema=None, allowed_tool_actions=None):
    """首轮资格：必要业务动作数与原目标义务（wait 不计）。

    wire_schema/allowed_tool_actions allow a 策略 2 template session to inject
    its own wire schema and allowed-action source; the default keeps importing
    the historical monolith so existing callers behave unchanged.
    """
    from jsonschema import Draft202012Validator
    if wire_schema is None or allowed_tool_actions is None:
        from .screenshot_plan import submit_plan_schema as wire_schema, _allowed_all as allowed_tool_actions
    wire = deepcopy(plan)
    for row in wire.get('requirements', []):
        row.pop('source_type', None)
        route = row.get('evidence_route')
        if isinstance(route, dict):
            route.pop('source_type', None)
            route.pop('observation_steps', None)
    errors = list(Draft202012Validator(wire_schema(allowed_tool_actions())).iter_errors(wire))
    if errors:
        error = errors[0]
        return False, {'kind': 'PLAN_FIELDS_INVALID', 'field_paths': ['.'.join(map(str, error.absolute_path))],
                       'message': error.message, 'dispatched': False}
    original_goal = str(goal or plan.get('goal') or '')
    if not DERIVATION_OBLIGATION.search(original_goal):
        extra = [row['id'] for row in plan.get('requirements') or []
                 if row.get('kind') == 'content' and (
                     row.get('evidence_route', {}).get('source_type') == 'derived_check'
                     or DERIVATION_OBLIGATION.search(str(row.get('description') or '')))]
        if extra:
            return False, {'kind': 'UNREQUESTED_DERIVATION_CHECK',
                           'field_paths': ['requirements'],
                           'requirement_ids': extra,
                           'message': '原目标没有独立验算、复算、换算推导或交叉验证义务；删除自增的推导核对事项，保留页面结果确认',
                           'dispatched': False}
    if DERIVATION_OBLIGATION.search(original_goal) and not any(r.get('evidence_route', {}).get('source_type') == 'derived_check' for r in plan.get('requirements', [])):
        return False, {'kind': 'DERIVATION_REQUIREMENT_MISSING', 'dispatched': False, 'message': '原目标明确要求独立推导核对；首轮须有保留该义务的content事项描述及对应输入/结果depends_on，不能只记录页面结果'}
    steps = plan.get('steps') or []
    waiting = [step for step in steps if step.get('action') in NON_BUSINESS_ACTIONS]
    business = business_actions(steps)
    if plan.get('unsuitable'):
        return True, {'kind': 'unsuitable', 'message': '模型报告本页自然路径不适合普通长流程',
                      'unsuitable': plan['unsuitable'], 'dispatched': False}
    atomicity = result_requirements_feedback(plan.get('requirements') or [], original_goal)
    if atomicity:
        return False, atomicity
    scope_gap = requirement_scope_feedback(plan.get('requirements') or [], original_goal)
    if scope_gap:
        return False, scope_gap
    for row in plan.get('requirements', []):
        acceptance = row.get('acceptance') or {}
        if row.get('business_role') == 'process':
            process_source = acceptance.get('source_quote', '')
            outcome_text = ' '.join((process_source, row.get('description', ''), acceptance.get('subject', '')))
            process_object = re.sub(r'通过|通過|经过|經過|经|經|搜索|检索|輸入|输入|提交|打开|打開|选择|選擇|填写|填寫|点击|點擊|获得|獲得|获取|獲取|并|並|的|「|」|[，,。\s]', '', process_source)
            process_specific = bool(process_object and process_object in _flat(
                str(row.get('description', '')) + str(acceptance.get('subject', ''))))
            if (not process_specific or row.get('kind') not in ('input', 'result') or not process_source or process_source not in original_goal
                    or not re.search(r'搜索|检索|輸入|输入|提交|打开|打開|选择|選擇|填写|填寫|点击|點擊', process_source)
                    or re.search(r'比较|比較|对比|對比|最终|最終|结论|結論|计算结果|計算結果|转换结果|轉換結果', outcome_text)):
                return False, {'kind': 'BUSINESS_ROLE_CONFLICT', 'requirement_ids': [row['id']],
                    'message': 'process仅允许原目标明确要求的input/result过程及其原文来源；比较、最终结果与结论仍是outcome', 'dispatched': False}
        source = acceptance.get('source_quote', '')
        if source not in original_goal:
            return False, {'kind': 'ACCEPTANCE_SOURCE_INVALID', 'requirement_ids': [row['id']], 'message': '验收范围须引用原目标原文', 'dispatched': False}
        if re.search(r'(?:阅读|读取|采集|获取|通读)(?:[^，。；;]{0,12})(?:全文(?!检索)|完整正文|完整文章)|完整(?:阅读|读取|采集|获取|通读)|完整正文', source) and acceptance.get('mode') != 'complete':
            return False, {'kind': 'ACCEPTANCE_SCOPE_CONFLICT', 'requirement_ids': [row['id']], 'message': '原目标明确完整范围不能缩减为存在或指定片段', 'dispatched': False}
    # An explicit whole-object request cannot disappear by quoting only an
    # easier substring of the frozen goal in every item.
    whole = re.search(r'(?:阅读|读取|采集|获取|通读)(?:[^，。；;]{0,12})(?:全文(?!检索)|完整正文|完整文章)|完整(?:阅读|读取|采集|获取|通读)|完整正文', original_goal)
    if whole and not any((r.get('acceptance') or {}).get('mode') == 'complete'
                         and whole.group() in (r.get('acceptance') or {}).get('source_quote', '')
                         for r in plan.get('requirements', [])):
        return False, {'kind': 'ACCEPTANCE_SCOPE_CONFLICT', 'message':
                       '原目标明确的完整正文义务未被任何完整范围事项承接', 'dispatched': False}
    if not any(row.get('business_role', 'outcome') == 'outcome' and row.get('kind') in ('result', 'content')
               for row in plan.get('requirements', [])):
        return False, {'kind': 'OUTCOME_REQUIREMENT_MISSING', 'message': '交付须保留至少一个最终结果或正文结论，不能全部降为过程', 'dispatched': False}
    route_gaps = evidence_route_gaps(plan)
    if route_gaps:
        return False, {'kind': 'EVIDENCE_ROUTE_INVALID', 'message': '；'.join(route_gaps), 'dispatched': False}
    if len(business) >= minimum:
        histogram = {}
        for step in business:
            histogram[step['action']] = histogram.get(step['action'], 0) + 1
        return True, {'kind': 'accepted', 'business_steps': len(business), 'wait_steps': len(waiting),
                      'total_steps': len(steps), 'action_kinds': len(histogram),
                      'action_histogram': dict(sorted(histogram.items()))}
    return False, {'kind': 'business_minimum', 'message': (
                      f'首轮计划{len(steps)}项中{len(waiting)}项为wait（不计业务动作），业务动作仅{len(business)}个，'
                      f'少于必要业务动作下限{minimum}；请提交自然完整路径，不补无用动作；自然不足即报告unsuitable'),
                   'business_steps': len(business), 'wait_steps': len(waiting),
                   'total_steps': len(steps), 'field_paths': ['steps'], 'dispatched': False}


def compile_contract(plan, fixed_goal=None):
    """Compile an accepted first plan into the frozen business contract.

    删除预测步号与机制猜测，保存业务验收的目标来源。
    返回编译后的计划与来源记录；原模型提交保留在 normalization 事件。
    """
    compiled = deepcopy(plan)
    if compiled.get('unsuitable'):
        return compiled, {}
    provenance = {}
    compiled.pop('final_presentation_step', None)
    for requirement in compiled.get('requirements') or []:
        if not isinstance(requirement, dict) or requirement.get('kind') not in KIND_SOURCE_TYPES:
            continue
        route = requirement.get('evidence_route')
        if route is None:
            route = requirement['evidence_route'] = {}
        elif not isinstance(route, dict):
            continue
        rid = requirement.get('id')
        if True: # Mechanical source classification has one host-owned value.
            if requirement['kind'] == 'content' and DERIVATION_OBLIGATION.search(str(requirement.get('description') or '')):
                route['source_type'] = 'derived_check'
            else:
                route['source_type'] = {'input': 'input_state', 'result': 'page_result',
                                        'content': 'page_content'}[requirement['kind']]
            provenance.setdefault('requirements', {})[rid] = {'source_type': 'host_derived_from_kind'}
        if requirement['kind'] == 'result' and requirement.get('result_kind') is None:
            provenance.setdefault('requirements', {})[rid] = {
                **provenance.get('requirements', {}).get(rid, {}),
                'result_kind': 'host_unknown_ordinary_page_result'}
        route.pop('observation_steps', None)
        requirement.pop('result_kind', None)
        # Historical facts are ordinary evidence; current is an explicit end-state duty.
        requirement.setdefault('business_role', 'outcome')
        requirement.setdefault('evidence_scope', 'historical')
        provenance.setdefault('requirements', {}).setdefault(rid, {})['acceptance'] = {
            'source_quote': (requirement.get('acceptance') or {}).get('source_quote'),
            'goal': str(fixed_goal or compiled.get('goal') or '')}
    if fixed_goal:
        compiled['goal'] = fixed_goal
    return compiled, provenance


def business_actions(steps):
    return [step for step in (steps or []) if isinstance(step, dict)
            and step.get('action') not in NON_BUSINESS_ACTIONS]
