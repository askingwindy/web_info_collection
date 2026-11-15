"""引用解析、覆盖、时效与共同完成谓词（策略2唯一实现）。

普通答案只要求 requirement_id 与证据引用；规范 observed_result 与 proof
由宿主从原始捕获生成。本模块集中：可见证据节点/区域解析、有界正文与
清单/表格/比较的覆盖谓词（分母来自合同，绝不由已采集内容反推）、结果
时效（同表单后续输入/提交作废旧结果）与不同事项不得复制同一答案的
共同完成谓词。在线核验与封存复算共用，不保留第二份规则。
"""
import re


def _flat(text):
    return re.sub(r'\s+', '', str(text or ''))


def _evidence_nodes(state):
    """Visible blocks are capture-owned DOM sources, even without a tree row."""
    nodes = {row['element_id']: {**row, **({'text': row['visible_text']}
             if 'visible_text' in row else {})} for row in state.get('elements', [])}
    for block in state.get('text_blocks', []):
        eid, box = block.get('element_id'), block.get('bbox')
        text = str(block.get('visible_text') or '')
        if (not eid or not box or len(box) != 4 or not text
                or _flat(text) not in _flat(state.get('visible_text'))):
            continue
        original = nodes.get(eid, {})
        if original and original.get('visible') is not True:
            continue
        nodes[eid] = {**original, 'element_id': eid, 'visible': True,
                      'bbox': box, 'text': text, 'native_role': block.get('tag', original.get('native_role'))}
    return list(nodes.values())


def _bbox_inside(inner, outer):
    return (inner[0] >= outer[0] - 1 and inner[1] >= outer[1] - 1
            and inner[2] <= outer[2] + 1 and inner[3] <= outer[3] + 1)


def _region_has_node(region, node):
    return (node.get('element_id') in {region.get('element_id'), *region.get('member_ids', [])}
            or bool(node.get('bbox') and _bbox_inside(node['bbox'], region['bbox'])))


def _visible_node_texts(state, node):
    from .result_execution import visible_result_texts
    return visible_result_texts(state, node)


def _visible_control_values(state, node):
    from .result_execution import visible_control_texts
    return visible_control_texts(state, node)


def _result_tokens_visible(state, node, text, *, causal_result=False):
    """Allow labels interleaved between values in one visible verified result.

    A result container often concatenates sibling values while the page's full
    visible text also contains their labels. Every result token must still be
    present in order; non-result nodes and offscreen nodes keep exact matching.
    """
    binding = next((row for row in state.get('capture_controls', [])
                    if row.get('element_id') == node.get('element_id')), {})
    if not binding.get('result_region_selector') and not causal_result:
        return False
    visible = _flat(state.get('visible_text'))
    position = 0
    for token in str(text or '').split():
        position = visible.find(_flat(token), position)
        if position < 0:
            return False
        position += len(_flat(token))
    return bool(str(text or '').split())


def _result_superseded(session, rows, oid, state, node, proof):
    """Historical reading stays valid; a calculation must match current inputs."""
    from .result_execution import _binding, submission_row
    from .screenshot_effect import business_scope
    from .collection_contract import _state_for_observation
    order = {key: index for index, key in enumerate(session.observation_records)}
    document = state.get('document_identity')
    if document != session.current.get('document_identity'):
        return True
    form = business_scope(state, node['element_id'])
    if not form:
        causal = proof.get('post_submit_causality') or {}
        submit_before = _state_for_observation(session, causal.get('submit_before_observation_id'))
        submit = next((row for row in rows
                       if row.get('operation_id') == causal.get('submit_operation_id')), None)
        if submit_before is not None and submit is not None:
            form = business_scope(submit_before, (submit.get('target') or {}).get('control_id'))
    if not form:
        binding = proof.get('result_execution_binding') or {}
        submission = binding.get('submission') or {}
        before = _state_for_observation(session, submission.get('before_observation_id'))
        if before is not None:
            form = business_scope(before, submission.get('node'))
    for row in rows:
        if row.get('definite_zero_effect') or order.get(row.get('after_observation_id'), -1) <= order.get(oid, -1):
            continue
        before = _state_for_observation(session, row.get('before_observation_id'))
        if before is None or before.get('document_identity') != document:
            continue
        from .screenshot_effect import input_edit_row
        if not input_edit_row(session, row) and not submission_row(row, before):
            continue
        changed_form = business_scope(before, (row.get('target') or {}).get('control_id'))
        if form and changed_form == form:
            return True
    return False


# --------------------------------------------------------------- coverage

def comparison_coverage_gaps(requirement, proofs):
    # Comparison endpoints are explicit specified items, never lexical guesses.
    return []


def content_boundary_proof(state, node):
    """Unique capture-owned semantic scope; answer regions cannot create scope."""
    boundaries = [b for b in state.get('content_boundaries', [])
                  if node.get('element_id') in b.get('member_ids', [])]
    if len(boundaries) != 1:
        return None
    boundary = boundaries[0]
    if boundary.get('source') != 'rendered_semantic_container' or not boundary.get('text'):
        return None
    return {**{key: boundary.get(key) for key in ('selector', 'element_id', 'text', 'source', 'node_ranges', 'scope_closed', 'scope_source')},
            'document_identity': state.get('document_identity'), 'url': state.get('url')}


def complete_scope_fragment(requirement, state, node):
    """Truth of a visible content fragment is independent of scope closure.

    Early titles remain usable after a later capture closes the same object.
    Only coverage_gaps may decide whether these spans prove a complete scope.
    """
    if requirement.get('kind') != 'content' or node.get('visible') is not True:
        return False
    if node.get('inputable') or node.get('clickable'):
        return False
    if node.get('native_role') in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'heading'):
        return True
    boundary = content_boundary_proof(state, node)
    return bool(boundary and (boundary.get('node_ranges') or {}).get(node.get('element_id')))


def multi_item_coverage_gaps(requirement, proofs):
    """有界正文/清单/表格覆盖：分母来自合同（区域整体或事项列举项）。

    单节点全文命中不再是完整性的替代证明：要么引用覆盖整个容器区域的
    证据（区域全文按序被已核验节点覆盖），要么合同 description 以「」
    列举的每一项都被覆盖；缺项如实列出，不由已采集内容反推分母。
    """
    acceptance = requirement.get('acceptance') or {}
    mode = acceptance.get('mode')
    if mode == 'presence':
        return []
    if mode not in ('specified', 'complete'):
        return [{'kind': 'ACCEPTANCE_SCOPE_UNKNOWN', 'requirement_id': requirement['id'],
                 'message': '缺少明确业务验收范围；不能默认存在即可完成'}]
    terms = acceptance.get('items', []) if mode == 'specified' else []
    if not proofs:
        return [{'kind': 'CONTENT_COVERAGE_INCOMPLETE', 'requirement_id': requirement['id'],
                 'message': '尚无可见证据引用'}]
    boundaries = [p.get('content_boundary') for p in proofs
                  if p.get('content_boundary') and p['content_boundary'].get('scope_closed') is True
                  and p['content_boundary'].get('scope_source')]
    if mode == 'complete':
        subject = _flat(acceptance.get('subject', ''))
        boundaries = [b for b in boundaries if subject and (
            subject in _flat((b.get('scope_source') or {}).get('object_title', ''))
            or _flat((b.get('scope_source') or {}).get('object_title', '')) in subject
            and bool(_flat((b.get('scope_source') or {}).get('object_title', ''))))]
    def boundary_key(b):
        return (_flat(b['text']), b.get('selector'), str(b.get('document_identity')), b.get('url'))
    unique = {boundary_key(b): b for b in boundaries}
    boundary = next(iter(unique.values())) if unique else None
    if boundary and not terms:
        missing_fragment = None
        for boundary in unique.values():
            # Source-owned offsets distinguish repeated identical paragraphs;
            # the same DOM node cannot consume a second occurrence by repetition.
            text = _flat(boundary['text'])
            intervals, sources = [], set()
            for proof in proofs:
                own_boundary = proof.get('content_boundary')
                if not own_boundary or boundary_key(own_boundary) != boundary_key(boundary):
                    continue
                source = proof.get('node')
                quote = _flat(proof.get('quote'))
                span = (own_boundary.get('node_ranges') or {}).get(source)
                if not span or not quote or (tuple(span), quote) in sources:
                    continue
                sources.add((tuple(span), quote))
                start = text.find(quote, span[0], span[1])
                if start >= 0:
                    intervals.append((start, start + len(quote)))
            covered = 0
            for start, end in sorted(intervals):
                if start > covered:
                    break
                covered = max(covered, end)
            missing_fragment = None if covered >= len(text) else text[covered:covered + 80]
            if missing_fragment is not None:
                break
        if missing_fragment is None:
            return []
        return [{'kind': 'CONTENT_COVERAGE_INCOMPLETE', 'requirement_id': requirement['id'],
                 'missing_fragment': missing_fragment,
                 'message': '此事项要求完整清单/正文/表格；已核验片段未按顺序覆盖所引区域的全部内容，'
                            '还缺：' + missing_fragment[:80] + '；补齐该区域内剩余内容，继续引用原事项剩余证据'}]
    if terms:
        missing = [term for term in terms
                   if not any(_flat(term) in _flat(proof.get('quote') or '') for proof in proofs)]
        if not missing:
            return []
        return [{'kind': 'CONTENT_COVERAGE_INCOMPLETE', 'requirement_id': requirement['id'],
                 'missing_terms': missing[:8],
                 'message': '此事项要求完整清单/列表；原目标列举项还缺：' + '、'.join(missing[:8])
                            + '；逐项引用可见证据后再次提交，不能以部分命中充当完整'}]
    return [{'kind': 'CONTENT_COVERAGE_INCOMPLETE', 'requirement_id': requirement['id'],
             'message': '此事项要求完整清单/正文/表格，但合同尚无已证明的完整内容边界；'
                        '局部region不能自证完整；已有明确容器时补齐其剩余可见引用，宿主仍无明确边界时保留scope_unknown并返回规划器，不修改冻结事项'}]


def coverage_gaps(requirement, proofs):
    if requirement.get('kind') not in ('content', 'result'):
        return []
    return multi_item_coverage_gaps(requirement, proofs)


def distinct_result_gaps(checks, requirements, claimed=None):
    """不同输出事项不能复制同一位置的同一个答案；同值须区分来源。

    claimed 为模型声明的 observed_result（引用制答案可为空）：同节点上的
    不同字段声明保持区分，宿主生成的规范文本相同则视为同一答案。
    """
    claimed = claimed or {}
    by_id = {row['id']: row for row in requirements}
    signatures = {}
    for check in checks:
        requirement = by_id.get(check.get('requirement_id'))
        if not requirement or requirement.get('kind') != 'result':
            continue
        proof = check['evidence'][0]
        signature = (proof.get('observation_id'), proof.get('node'),
                     str(claimed.get(check.get('requirement_id'))
                         or check.get('observed_visible_text') or '').strip())
        signatures.setdefault(signature, []).append(requirement['id'])
    duplicates = {rid for ids in signatures.values() if len(ids) > 1 for rid in ids}
    if not duplicates:
        return []
    return ({'kind': 'DISTINCT_RESULT_EVIDENCE_REQUIRED',
             'requirement_ids': sorted(duplicates),
             'message': '不同输出事项不能复制同一位置的同一个答案；分别引用各字段真实标签和值。数值相同时仍须区分对应字段位置或完整标签原文'},
            sorted(duplicates))
