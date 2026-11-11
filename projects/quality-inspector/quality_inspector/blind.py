"""Evidence-bound first-pass human workspace, without previous review outcomes.

This is a presentation isolation policy, not a new customer acceptance rule.
Original annotations, images and trees are copied byte-for-byte after checking
their bindings and field allowlists. Reports and documentary history stay out.
"""
import hashlib
import json
from pathlib import Path
import shutil
from jsonschema.exceptions import ValidationError

from .format_checks import ANNOTATION, TREE, Strict

CONTEXT_FIELDS = {'source_statement', 'input_statement'}
ARGUMENT_FIELDS = {
    'click': {'x', 'y'}, 'double_click': {'x', 'y'}, 'right_click': {'x', 'y'},
    'type': {'text'}, 'hotkey': {'keys'}, 'scroll': {'x', 'y', 'direction'},
    'drag': {'x', 'y', 'end_x', 'end_y'}, 'back': set(), 'open_url': {'url'},
    'select': {'x', 'y', 'option'}, 'wait': set(), 'complete': {'status'},
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def context_value(value):
    if (not isinstance(value, dict) or set(value) != CONTEXT_FIELDS or
            any(not isinstance(value[k], str) or not value[k].strip() for k in CONTEXT_FIELDS)):
        raise ValueError('盲审需单独提供source_statement/input_statement两项中性事实说明')
    return dict(value)


def _allow_fields(value, schema, path):
    if isinstance(value, dict):
        allowed = schema.get('properties')
        if allowed is None:
            return
        extras = set(value) - set(allowed)
        if extras:
            raise ValueError('盲审字段白名单不包含：' + path + '/' + ','.join(sorted(extras)))
        for key, child in value.items():
            _allow_fields(child, allowed[key], path + '/' + key)
    elif isinstance(value, list) and 'items' in schema:
        for index, child in enumerate(value):
            _allow_fields(child, schema['items'], path + '/' + str(index))


def validate_sample(sample):
    """Reject unknown embedded metadata instead of silently copying it."""
    if not sample.get('binding_valid') or not sample.get('steps'):
        raise ValueError('盲审样本的实际标注和图树绑定无效：' + str(sample.get('sample_id')))
    sid = sample['sample_id']
    if not isinstance(sid, str) or Path(sid).name != sid or sid in ('.', '..'):
        raise ValueError('盲审样本编号不适合作为独立资源路径')
    annotation = sample['annotation']
    Strict(ANNOTATION).validate(annotation)
    _allow_fields(annotation, ANNOTATION, 'annotation')
    for step in annotation['steps']:
        call = step['tool_call']
        allowed = ARGUMENT_FIELDS.get(call['tool_name'])
        if allowed is None or set(call['arguments']) - allowed:
            raise ValueError('盲审动作参数超出字段白名单：' + str(step['step_id']))
    for step in sample['steps']:
        tree = json.loads(Path(step['tree_path']).read_text(encoding='utf-8'))
        Strict(TREE).validate(tree)
        _allow_fields(tree, TREE, 'ui_tree')


def prepare_data(report, *, reviewer_name, context):
    from .reporting import review_template, review_samples, _review_identity
    from .reviews import evidence_files
    context = context_value(context)
    if not isinstance(reviewer_name, str) or not reviewer_name.strip():
        raise ValueError('盲审需要已确认的真人审核姓名')
    if report.get('scope') != 'delivery':
        raise ValueError('盲审入口仅接受当前delivery报告及其审核绑定')
    samples = review_samples(report)
    if not samples or len({s['sample_id'] for s in samples}) != len(samples):
        raise ValueError('盲审需要非空、编号唯一的实际样本')
    for sample, source in zip(samples, report['samples']):
        try:
            validate_sample(sample)
        except ValidationError as error:
            raise ValueError('盲审原始字段结构无效：' + str(sample['sample_id'])) from error
        if evidence_files(sample['sample_path']) != source['evidence_sha256']:
            raise ValueError('盲审图树绑定必须精确等于实际步骤，不能带入额外文件')
    # Always rebuild blank records. No caller-supplied record or package template.
    full_template = review_template(report)
    template = {key: full_template[key] for key in ('schema_version', 'records')}
    context_sha = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True,
                                          separators=(',', ':')).encode()).hexdigest()
    identity = _review_identity(report, template)
    data_id = 'blind-v1-' + hashlib.sha256((identity + ':' + context_sha + ':' + reviewer_name).encode()).hexdigest()
    return {
        'mode': 'blind', 'samples': samples, 'template': template,
        'semantic': ['visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference'],
        'reviewer': {'kind': 'human', 'name': reviewer_name}, 'data_id': data_id,
        'neutral_context': context, 'neutral_context_sha256': context_sha,
        'package_documents': [],
        'package_summary': {'sample_count': len(samples),
                            'frame_count': sum(len(s['steps']) for s in samples)},
    }


def write_workspace(report_path, output, *, context_path, receipt_path, reviewer_name='hemiao'):
    """Create an isolated, portable review folder and a separate operator receipt."""
    report_path, output = Path(report_path).resolve(), Path(output).resolve()
    context_path, receipt_path = Path(context_path).resolve(), Path(receipt_path).resolve()
    report = json.loads(report_path.read_text(encoding='utf-8'))
    dataset = Path(report['dataset']).resolve()
    if output.exists() or receipt_path.exists():
        raise ValueError('盲审输出与操作收据必须使用新路径')
    if (output.is_relative_to(dataset) or receipt_path.is_relative_to(dataset)
            or receipt_path.is_relative_to(output) or report_path.is_relative_to(output)
            or context_path.is_relative_to(output)):
        raise ValueError('盲审资料须独立；报告和操作收据不得放入受检包或盲审目录')
    context = context_value(json.loads(context_path.read_text(encoding='utf-8')))
    data = prepare_data(report, reviewer_name=reviewer_name, context=context)
    source_sha = {'report': digest(report_path), 'context': digest(context_path)}
    inputs = {}
    copied = {}
    output.mkdir(parents=True, exist_ok=False)
    for sample, record in zip(data['samples'], data['template']['records']):
        root = Path(sample['sample_path'])
        asset_root = Path('assets') / sample['sample_id']
        bound = {'annotation.json': record['annotation_sha256'], **record['evidence_sha256']}
        for relative, expected in bound.items():
            path = root / relative
            if Path(relative).is_absolute() or not path.resolve().is_relative_to(root) or path.is_symlink():
                raise ValueError('盲审证据路径越界或为符号链接')
            if digest(path) != expected:
                raise ValueError('创建盲审入口时证据发生变化')
            destination = output / asset_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            if digest(destination) != expected:
                raise ValueError('盲审副本与原件不一致')
            inputs[str(path)] = expected
            copied[(asset_root / relative).as_posix()] = expected
        sample['sample_path'] = asset_root.as_posix()
        sample['annotation_path'] = (asset_root / 'annotation.json').as_posix()
        for step, original in zip(sample['steps'], sample['annotation']['steps']):
            step['image_path'] = (asset_root / original['image_path']).as_posix()
            step['tree_path'] = (asset_root / original['ui_tree_path']).as_posix()
    from .reporting import render_review_data
    (output / 'review.html').write_text(render_review_data(data), encoding='utf-8')
    (output / 'review-template.json').write_text(json.dumps(data['template'], ensure_ascii=False, indent=2) + '\n')
    if digest(report_path) != source_sha['report'] or digest(context_path) != source_sha['context']:
        raise ValueError('盲审报告或事实说明在生成期间发生变化')
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise ValueError('盲审生成后原始证据发生变化')
    receipt = {
        'schema_version': 'qc-blind-workspace-receipt-1', 'mode': 'blind',
        'workspace': str(output), 'data_id': data['data_id'],
        'source_report': {'path': str(report_path), 'sha256': source_sha['report']},
        'neutral_context': {'path': str(context_path), 'sha256': source_sha['context']},
        'source_files_sha256': inputs, 'copied_evidence_sha256': copied,
        'workspace_files_sha256': {p.relative_to(output).as_posix(): digest(p)
                                   for p in sorted(output.rglob('*')) if p.is_file()},
        'sample_count': len(data['samples']),
        'frame_count': sum(len(s['steps']) for s in data['samples']),
        'reviewer': data['reviewer'], 'decisions_prefilled': False,
        'AI_or_mechanical_decisions_included': False,
        'package_document_review_deferred': True,
        'actual_human_reviews_created': 0,
        'limitations': 'UI/data isolation only, not identity authentication or proof of actual reading. Original task annotations remain the content under review.',
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2); stream.write('\n')
    return receipt
