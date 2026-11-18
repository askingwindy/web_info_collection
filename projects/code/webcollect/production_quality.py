"""Producer safeguards. Independent QC must still inspect final candidates."""
import hashlib
from webcollect import workspace_json as json
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
        return {'schema': 'exact-index', 'scope': 'producer-exact-images-only',
            'independent_final_qc_required': True, 'roots': [str(p) for p in self.roots],
            'image_count': len(self.files),
            'files_sha256': {str(p): digest for p, digest in sorted(self.files.items())}}


class ConcurrentExactImageIndex:
    """Shared exact-image claims, committed atomically with a capture outcome.

    Browsers run independently. Only baseline registration, successful capture
    commits and boundary integrity snapshots serialize through the existing
    production ledger. In-flight/failed directories are not accepted history.
    """
    def __init__(self, roots, store):
        self.roots = tuple(sorted({Path(root).resolve() for root in roots}))
        self.store = store
        with store.exact_image_snapshot() as (states, _):
            baseline = {str(path): sha(path) for path in self._paths(states)}
        store.register_exact_baseline(baseline)

    def _paths(self, states):
        return sorted({p.resolve() for root in self.roots for p in _sample_images(root)
                       if states.get(p.parent.parent.name, 'legacy') in ('legacy', 'collected_pending_review')})

    def _covered(self, path):
        path = Path(path)
        for root in self.roots:
            try:
                parts = path.relative_to(root).parts
            except ValueError:
                continue
            if ((len(parts) == 4 and parts[0] == 'samples' and parts[2] == 'images')
                    or (len(parts) == 5 and parts[1] == 'samples' and parts[3] == 'images')):
                return True
        return False

    def conflicts(self, sample):
        sample = Path(sample).resolve()
        own = {sha(path): path.name for path in sorted((sample / 'images').glob('*.png'))}
        result = []
        for row in self.store.exact_image_claims():
            if row['sample_id'] != sample.name and row['digest'] in own:
                result.append({'rule': 'customer exact screenshot route', 'sha256': row['digest'],
                    'current_step_image': own[row['digest']], 'other_sample': str(Path(row['path']).parent.parent),
                    'other_image': row['path'], 'not_full_trajectory_equivalence': True})
        return result

    def sample_images(self, sample):
        return {str(path.resolve()): sha(path) for path in sorted((Path(sample) / 'images').glob('*.png'))}

    def add_sample(self, sample):
        expected = self.sample_images(sample)
        actual = {row['path']: row['digest'] for row in self.store.exact_image_claims()
                  if row['sample_id'] == Path(sample).name}
        if any(actual.get(path) != digest for path, digest in expected.items()):
            raise ValueError('成功保存的样本缺少同事务精确图片声明')

    def verify_snapshot(self):
        with self.store.exact_image_snapshot() as (states, rows):
            expected = {row['path']: row['digest'] for row in rows if self._covered(row['path'])}
            current = {str(path): sha(path) for path in self._paths(states)}
            if current != expected:
                changed = sorted(path for path in current.keys() | expected.keys()
                                 if current.get(path) != expected.get(path))
                raise ValueError('并发去重集合存在未登记变化：' + str(changed[:10]))
            # Check claims outside the scanned roots too: they participate in
            # the global conflict check and must not become a stale cache.
            for row in rows:
                if sha(row['path']) != row['digest']:
                    raise ValueError('已登记精确图片发生变化：' + row['path'])
        return {'schema': 'exact-index-concurrent',
            'scope': 'producer-exact-images-only', 'independent_final_qc_required': True,
            'atomic_capture_commit': True, 'registry_path': str(self.store.registry),
            'roots': [str(root) for root in self.roots], 'image_count': len(expected),
            'files_sha256': dict(sorted(expected.items()))}

def contract_identity(repo):
    """Bind installed requirement documents without opening historical samples."""
    import json
    root = Path(repo) / 'projects/quality-inspector/quality_inspector'
    manifest = json.loads((root / 'contract-authority.json').read_text())
    rows = manifest.get('documents', [])
    roles = [row.get('role') for row in rows]
    if (manifest.get('schema_version') not in ('installed-authority', 'qc-installed-authority-1')
            or len(roles) != len(set(roles)) or roles != manifest.get('source_precedence')
            or not {'clarification', 'requirement', 'annex_a', 'annex_b'} <= set(roles)):
        raise ValueError('Complete installed authority and precedence required')
    files = {}
    for row in rows:
        resource = Path(row['resource'])
        if resource.is_absolute() or '..' in resource.parts or resource.parts[0] != 'authority':
            raise ValueError('Installed authority resource is outside its package')
        path = root / resource
        if path.is_symlink() or sha(path) != row['sha256']:
            raise ValueError('Installed authority document changed')
        files[row['path']] = row['sha256']
    legacy = len(rows) == 4
    return {'profile': 'customer-prose-with-clarifications', 'version': 2 if legacy else 3,
            'authority_source': 'installed-four-document-authority' if legacy else 'installed-document-authority', 'authority_files_sha256': files,
            'producer_constants_not_customer_exclusive_enums': True, 'customer_actual_program': 'NOT_EXECUTED'}

class LoginRequiredError(ValueError):
    failure_class = 'unsupported'


def require_public_task_state(state):
    """Stop at explicit auth endpoints; never retry with credentials or evade gates."""
    import re
    from urllib.parse import urlsplit
    path=urlsplit(state.get('url','')).path.lower()
    if re.fullmatch(r'/(?:user/|account/|accounts/)?(?:login|signin|sign-in)(?:\.aspx|\.html|\.php|/)?',path):
        raise LoginRequiredError('公开任务遇到登录门槛：停止该任务，未登录或绕过访问限制')
