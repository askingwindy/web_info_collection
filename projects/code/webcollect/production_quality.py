"""Producer safeguards. Independent QC must still inspect final candidates."""
import hashlib,json
from pathlib import Path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def exact_conflicts(sample,roots):
    sample=Path(sample).resolve();own={sha(p):p.name for p in (sample/'images').glob('*.png')};out=[];seen=set()
    for root in roots:
        root=Path(root).resolve()
        for image in sorted(root.glob('*/samples/*/images/*.png')):
            other=image.parent.parent.resolve()
            if other==sample or image.resolve() in seen:continue
            seen.add(image.resolve());digest=sha(image)
            if digest in own:out.append({'rule':'customer exact screenshot route','sha256':digest,'current_step_image':own[digest],'other_sample':str(other),'other_image':str(image),'not_full_trajectory_equivalence':True})
    return out

def contract_identity(repo):
    repo=Path(repo);sources=['request/需求书-Web浏览器自动化操作轨迹数据集.md','request/需求澄清记录.md','request/web操作采集需求/附件A-字段说明.md','request/web操作采集需求/附件B-动作空间与坐标系.md','request/web操作采集需求/samples/样例说明.md']
    return {'profile':'customer-prose-with-clarifications','version':1,'authority_files_sha256':{s:sha(repo/s) for s in sources},'producer_constants_not_customer_exclusive_enums':True,'customer_actual_program':'NOT_EXECUTED'}

def require_public_task_state(state):
    """Stop at explicit auth endpoints; never retry with credentials or evade gates."""
    import re
    from urllib.parse import urlsplit
    path=urlsplit(state.get('url','')).path.lower()
    if re.fullmatch(r'/(?:user/|account/|accounts/)?(?:login|signin|sign-in)(?:\.aspx|\.html|\.php|/)?',path):
        raise ValueError('公开任务遇到登录门槛：停止该任务，未登录或绕过访问限制')
