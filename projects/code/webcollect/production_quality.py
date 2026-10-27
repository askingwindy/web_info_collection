"""Producer safeguards. Independent QC must still inspect final candidates."""
import hashlib,json
from pathlib import Path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _sample_images(root):
    """Accept a customer package, a raw batch, or a directory of batches.

    Never recurse through evidence/rejected/other audit directories: those are
    retained failures, not members of the proposed delivery set.
    """
    root=Path(root)
    containers=[root] if (root/'samples').is_dir() else [p for p in root.iterdir() if p.is_dir() and (p/'samples').is_dir()] if root.is_dir() else []
    for container in containers:
        yield from container.glob('samples/*/images/*.png')

def exact_conflicts(sample,roots):
    sample=Path(sample).resolve();own={sha(p):p.name for p in (sample/'images').glob('*.png')};out=[];seen=set()
    for root in roots:
        root=Path(root).resolve()
        for image in sorted(_sample_images(root)):
            other=image.parent.parent.resolve()
            if other==sample or image.resolve() in seen:continue
            seen.add(image.resolve());digest=sha(image)
            if digest in own:out.append({'rule':'customer exact screenshot route','sha256':digest,'current_step_image':own[digest],'other_sample':str(other),'other_image':str(image),'not_full_trajectory_equivalence':True})
    return out

class ExactImageIndex:
    """Content-hashed snapshot for one serial collection run.

    Roots are read afresh on construction; a saved receipt is evidence, never a
    trusted hash cache. Accepted samples are added incrementally. Rehash the
    complete set at the run boundary to detect concurrent edits, additions or
    removals. Independent final QC remains mandatory.
    """
    def __init__(self, roots):
        self.roots = tuple(sorted({Path(root).resolve() for root in roots}))
        self.files = {}
        self.by_digest = {}
        for path in self._paths():
            self._add(path)

    def _paths(self):
        return sorted({p.resolve() for root in self.roots for p in _sample_images(root)})

    def _add(self, path):
        path = Path(path).resolve()
        digest = sha(path)
        if path in self.files:
            if self.files[path] != digest:
                raise ValueError(f'去重基线图片发生变化：{path}')
            return
        self.files[path] = digest
        self.by_digest.setdefault(digest, set()).add(path)

    def add_sample(self, sample):
        for path in sorted((Path(sample) / 'images').glob('*.png')):
            self._add(path)

    def conflicts(self, sample):
        sample = Path(sample).resolve()
        own = {sha(p): p.name for p in sorted((sample / 'images').glob('*.png'))}
        result = []
        for digest, name in own.items():
            for other in sorted(self.by_digest.get(digest, ())):
                if other.parent.parent == sample:
                    continue
                result.append({'rule': 'customer exact screenshot route',
                    'sha256': digest, 'current_step_image': name,
                    'other_sample': str(other.parent.parent), 'other_image': str(other),
                    'not_full_trajectory_equivalence': True})
        return result

    def verify_snapshot(self):
        current = {path: sha(path) for path in self._paths()}
        if current != self.files:
            changed = sorted(str(p) for p in current.keys() | self.files.keys()
                             if current.get(p) != self.files.get(p))
            raise ValueError(f'去重集合在运行期间发生未登记变化：{changed[:10]}')
        return self.receipt()

    def receipt(self):
        return {'schema': 'webcollect-exact-index-1', 'scope': 'producer-exact-images-only',
            'independent_final_qc_required': True, 'roots': [str(p) for p in self.roots],
            'image_count': len(self.files),
            'files_sha256': {str(p): digest for p, digest in sorted(self.files.items())}}

def contract_identity(repo):
    repo=Path(repo);sources=['request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md','request/需求澄清记录.md','request/web操作采集需求/附件A-字段说明.md','request/web操作采集需求/附件B-动作空间与坐标系.md','request/web操作采集需求/samples/样例说明.md']
    return {'profile':'customer-prose-with-clarifications','version':1,'authority_files_sha256':{s:sha(repo/s) for s in sources},'producer_constants_not_customer_exclusive_enums':True,'customer_actual_program':'NOT_EXECUTED'}

def require_public_task_state(state):
    """Stop at explicit auth endpoints; never retry with credentials or evade gates."""
    import re
    from urllib.parse import urlsplit
    path=urlsplit(state.get('url','')).path.lower()
    if re.fullmatch(r'/(?:user/|account/|accounts/)?(?:login|signin|sign-in)(?:\.aspx|\.html|\.php|/)?',path):
        raise ValueError('公开任务遇到登录门槛：停止该任务，未登录或绕过访问限制')
