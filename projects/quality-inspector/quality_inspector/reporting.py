import hashlib
import json
from pathlib import Path
from .engine import SEMANTIC
from .layout import discover, sample_root

def review_template(report):
    """Return an untouched, evidence-bound blank review, never an acceptance."""
    template = {
        'schema_version': 'qc-review',
        'records': [{
            'sample_id': sample['sample_id'],
            'baseline_sha256': report['baseline']['config_sha256'],
            'annotation_sha256': sample['annotation_sha256'],
            'evidence_sha256': sample['evidence_sha256'],
            'reviewer': {'kind': '', 'name': ''},
            'provenance': {'description': ''},
            'checks': {name: {'status': 'REVIEW_REQUIRED', 'note': ''} for name in SEMANTIC},
        } for sample in report['samples']],
    }
    if report.get('scope')=='delivery':
        for record in template['records']:
            record['provenance']['frames_viewed']=[]
            record['step_observations']=[]
            for check in record['checks'].values():check['evidence_steps']=[]
    if 'local_profile' in report:
        from .profiles import package_review_template
        template['package_review'] = package_review_template(report)
        if report.get('scope') == 'delivery':
            from .profiles import delivery_document_review_template
            template['delivery_document_review'] = delivery_document_review_template(report)
    return template


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _evidence_path(root, value):
    """Only resolve local evidence inside the sample declared by the report."""
    if not isinstance(value, str) or not value:
        raise ValueError('证据路径缺失')
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('证据路径超出样本目录')
    return path


def review_samples(report):
    """Expose the real task and target beside its screenshots, without guessing."""
    rows = []
    for source in report['samples']:
        root = sample_root(source['sample_path'])
        annotation_path = root / 'annotation.json'
        warnings = []
        annotation = None
        try:
            annotation = json.loads(annotation_path.read_text(encoding='utf-8'))
            if not isinstance(annotation, dict):
                raise ValueError('标注必须为对象')
            if _sha(annotation_path) != source.get('annotation_sha256'):
                warnings.append('标注文件已变更，与本次质检报告的校验值不一致。')
        except (OSError, ValueError, UnicodeError) as error:
            annotation = None
            warnings.append('无法读取完整任务标注：' + str(error))
        original = annotation or {}
        steps = original.get('steps')
        if not isinstance(steps, list):
            warnings.append('标注中的步骤缺失或格式不正确，暂用报告中的证据索引。')
            steps = source.get('steps', [])
        if not isinstance(steps, list):
            steps = []
        if not steps:
            warnings.append('没有可逐步审核的证据。')
        device = original.get('device_info') if isinstance(original.get('device_info'), dict) else {}
        projected = []
        expected_files = source.get('evidence_sha256', {})
        if not isinstance(expected_files, dict):
            expected_files = {}
            warnings.append('质检报告缺少图树校验清单。')
        for step in steps:
            if not isinstance(step, dict):
                warnings.append('步骤记录格式不正确，无法展示该步骤。')
                continue
            row = dict(step)
            step_warnings = []
            image_path = tree_path = None
            for field, value in [('image_path', step.get('image_path')),
                                 ('tree_path', step.get('ui_tree_path', step.get('tree_path')))]:
                try:
                    path = _evidence_path(root, value)
                    relative = path.relative_to(root).as_posix()
                    if not path.is_file():
                        raise ValueError('文件不存在')
                    if expected_files.get(relative) != _sha(path):
                        step_warnings.append(('截图' if field == 'image_path' else '界面树') + '已变更或未绑定本次报告。')
                    if field == 'image_path':
                        image_path = str(path)
                    else:
                        tree_path = str(path)
                except (OSError, ValueError, TypeError) as error:
                    step_warnings.append(('截图' if field == 'image_path' else '界面树') + '不可用：' + str(error))
            tree = None
            if tree_path:
                try:
                    tree = json.loads(Path(tree_path).read_text(encoding='utf-8'))
                    if not isinstance(tree, dict) or not isinstance(tree.get('elements'), list):
                        raise ValueError('界面树格式不正确')
                except (OSError, ValueError, UnicodeError) as error:
                    tree = None
                    step_warnings.append('无法解析界面树：' + str(error))
            action = step.get('action') if isinstance(step.get('action'), dict) else {}
            target_id = action.get('target_element_id')
            target = next((element for element in (tree or {}).get('elements', [])
                           if isinstance(element, dict) and element.get('element_id') == target_id), None) if target_id else None
            if target_id and tree is not None and target is None:
                step_warnings.append('同步界面树中未找到动作引用的目标控件。')
            row.update(image_path=image_path, tree_path=tree_path, target=target,
                       screen_resolution=(tree or {}).get('screen_resolution', device.get('screen_resolution')),
                       warnings=step_warnings, binding_valid=not step_warnings)
            projected.append(row)
        app = original.get('app_info') if isinstance(original.get('app_info'), dict) else {}
        row = {
            'sample_id': source['sample_id'], 'sample_path': str(root),
            'annotation_path': str(annotation_path), 'annotation': annotation,
            'task_instruction': original.get('task_instruction', ''),
            'final_result': original.get('final_result', ''),
            'completion_judgement': original.get('completion_judgement', ''),
            'completion_status': original.get('completion_status', ''),
            'task_type': original.get('task_type', []),
            'device_info': device,
            'site': app.get('app_name', ''), 'title': app.get('app_name') or source['sample_id'],
            'warnings': warnings, 'steps': projected,
            'binding_valid': not warnings and all(step['binding_valid'] for step in projected),
        }
        rows.append(row)
    return rows


def _review_identity(report, template):
    """Version UI drafts by evidence identity, independent of page rendering."""
    identity = {
        'baseline_sha256': report['baseline']['config_sha256'],
        'records': [{key: row[key] for key in ['sample_id', 'annotation_sha256', 'evidence_sha256']}
                    for row in template['records']],
        'package_files_sha256': template.get('package_review', {}).get('package_files_sha256', {}),
        'profile_sha256': template.get('package_review', {}).get('profile_sha256'),
    }
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _package_documents(report):
    """Index original package documents; never manufacture missing paperwork."""
    root = Path(report['dataset']).resolve()
    layout = discover(root)
    bound = report.get('package_files_sha256')
    candidates = sorted(bound) if isinstance(bound, dict) else [p.relative_to(root).as_posix() for p in sorted(root.rglob('*')) if p.is_file()]
    documents = []
    for relative in candidates:
        path = (root / relative).resolve()
        parts = Path(relative).parts
        include = (relative in ['README.md', 'candidate_manifest.json', 'document_roles.json', 'delivery_manifest.json',
                                '附件A-字段说明.md', '附件B-动作空间与坐标系.md', '动作空间与系统提示.md',
                                '合成方式说明.md', '来源与合规说明.md', '来源说明.md', '字段说明.md', 'site-list.json'] or
                   (layout.kind == 'customer-flat' and relative in ['metadata.csv', 'qc_report.md']) or
                   (parts and parts[0] == 'docs' and path.suffix in ['.md', '.json', '.csv', '.txt']) or
                   (len(parts) == 2 and path.name in ['metadata.csv', 'qc_report.md', 'manifest.json']))
        if not include or not path.is_relative_to(root):
            continue
        warnings = []
        if not path.is_file():
            warnings.append('文档文件不存在。')
        elif isinstance(bound, dict) and _sha(path) != bound[relative]:
            warnings.append('文档已变更，与报告绑定的文件校验值不一致。')
        documents.append({'title': relative, 'path': str(path), 'relative_path': relative,
                          'binding_valid': not warnings, 'warnings': warnings})
    return documents


def review_data(report, template=None, reviewer_name='hemiao'):
    """Data contract shared by the offline page and preview fixtures."""
    template = review_template(report) if template is None else template
    samples = review_samples(report)
    statistics = report.get('acceptance_scopes', {}).get('pilot', {}).get('statistics', {})
    summary = dict(statistics) if isinstance(statistics, dict) else {}
    summary.update(sample_count=len(samples), frame_count=sum(len(row['steps']) for row in samples),
                   effective_action_count=sum(step.get('action', {}).get('action_type') not in ['wait', 'complete']
                                              for row in samples for step in row['steps'] if isinstance(step.get('action'), dict)))
    return {'report': report, 'template': template, 'semantic': SEMANTIC, 'samples': samples,
            'reviewer': {'kind': 'human', 'name': reviewer_name},
            'data_id': _review_identity(report, template), 'package_documents': _package_documents(report),
            'package_summary': summary}


def render_review(report, template=None, reviewer_name='hemiao'):
    return render_review_data(review_data(report, template, reviewer_name))


def render_review_data(value):
    """Render a prepared data contract; blind preparation has its own allowlist."""
    data = json.dumps(value, ensure_ascii=False).replace('<', '\\u003c')
    return Path(__file__).with_name('review.html').read_text(encoding='utf-8').replace('__DATA__', data)


def write_outputs(report,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'rule-catalog.json').write_text(json.dumps(report['rules']+report.get('local_rule_catalog',[]),ensure_ascii=False,indent=2)+'\n')
    template=review_template(report)
    if 'local_profile' in report:
        (output/'local-profile.json').write_text(json.dumps(report['local_profile'],ensure_ascii=False,indent=2)+'\n')
        (output/'requirements-baseline.json').write_text(json.dumps(report['requirements_baseline'],ensure_ascii=False,indent=2)+'\n')
    (output/'review-template.json').write_text(json.dumps(template,ensure_ascii=False,indent=2)+'\n')
    baseline_note=('合同规则绑定：'+report['baseline']['config_sha256']+'。本次仅依据实际交付物检查；旧baseline与raw只用于可选工程审计。' if report.get('scope')=='delivery' else '基准原件哈希：'+report['baseline']['integrity']+'。原样例已知空task_type及历史矛盾保留为限制，不要求新产物复制错误。')
    text=['# 独立质检程序结果','',f'程序状态：{report["status"]}；样本数：{report["sample_count"]}。这是本程序在已声明基准下的结果，客户真实程序未执行，客户验收为UNKNOWN。','',f'逐样本状态：{json.dumps(report["sample_status_counts"],ensure_ascii=False)}。','',baseline_note,'','|样本|状态|FAIL规则|待审规则数|','|---|---|---|---|']
    for s in report['samples']:text.append('|'+s['sample_id']+'|'+s['status']+'|'+', '.join(c['rule_id'] for c in s['checks'] if c['status']=='FAIL')+'|'+str(sum(c['status']=='REVIEW_REQUIRED' for c in s['checks']))+'|')
    text+=['','## 数据集/外部待审（不重复成逐样本人工任务）','']
    text += ['- '+c['rule_id']+' ['+c['scope']+'] '+c['status']+'：'+c['reason'] for c in report.get('dataset_checks',[])]
    text += ['','本地样本汇总：'+report.get('local_sample_status',report['status'])+'；外部客户验收：UNKNOWN。']
    if report.get('scope')=='delivery':
        imported=report.get('review_import',{})
        text += ['','机械规则只判文件/字段和确定性约束；REVIEW_*是导入的实际AI或真人判断。缺少有效审核不能发布。',
                 '审核记录完整性校验不认证身份或真实阅读。显式继承旧记录数：'+str(len(imported.get('migrated_records',[])))+'；继承不表示本次重新看图。',
                 'release_ready仅表示当前final本地交付门槛；不表示真人校准、M4能力评估或客户验收完成。']
    if 'local_profile' in report:
        text += ['','## 显式本地验收','', '本地验收：'+report['local_acceptance_status']+'；客户实际验收：UNKNOWN。',
                 '配置：'+report['local_profile']['configuration']['profile_id']+'；SHA256 '+report['local_profile']['sha256']+'。',
                 ('交付按样本和批次判定；不套用pilot最小数量。类目是否考核按显式profile记录。' if report.get('scope')=='delivery' else '样本/批次/试点均须PASS。已配置近似算法命中即FAIL，不以语义审核豁免；外部算法等价性与全集验收另列。'),
                 ('逐图语义结论只接受绑定实际交付文件的AI或真人审核；自动文档检查不冒充人工签署。' if report.get('scope')=='delivery' else '文档审核使用审核台的“最后核对交付资料”，绑定完整交付包与profile；本人实际判断后导出，未完成项保持待审。'),
                 '', '|作用域|状态|', '|---|---|']
        text += ['|'+scope+'|'+result['status']+'|' for scope,result in report['acceptance_scopes'].items()]
        text += ['', '本地未通过项：']
        text += ['- '+s['sample_id']+'：'+', '.join(c['rule_id']+'='+c['status'] for c in s['local_checks'] if c['status']!='PASS') for s in report['samples'] if s['local_acceptance_status']!='PASS']
        text += ['- '+c['rule_id']+'='+c['status'] for scope in ['batch','pilot'] for c in report['acceptance_scopes'][scope]['checks'] if c['status']!='PASS']
    text+=['','review.html为离线证据与审核入口，包含截图、树/动作定位、失败和修复建议。review-template.json需由实际审核者填写；默认待审，不能冒充签名。使用--reviews重新运行，哈希/基准不一致的记录将拒绝。已有AI字段证据以partial_ai_evidence附录接入，部分字段复核不自动等同全轨迹视觉通过。','','批次文件、去重算法及逐步骤证据见report.json。程序PASS只表示本质检配置下已执行规则通过，永不代表客户真实程序通过。']
    (output/'报告.md').write_text('\n'.join(text)+'\n')
    (output/'review.html').write_text(render_review(report,template),encoding='utf-8')
