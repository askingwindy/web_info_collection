"""Content-addressed sample versions; explicit supersession, never mtime selection."""
import csv
import json
from collections import defaultdict
from pathlib import Path

from .contract import digest

POLICY = 'qc-sample-versions-1'


def compare_versions(manifest, *, base=None):
    """Resolve copies and declared version ancestry without editing any package.

    Versions include every sample file, optional ground truth, and source/site
    assignment. Package documents stay bound by the enclosing frozen manifest.
    A declaration is an effective-version choice, never a semantic QC approval.
    """
    base = Path(base or Path.cwd())
    occurrences = []; errors = []
    for package in manifest['packages']:
        if (not isinstance(package, dict) or not isinstance(package.get('path'), str)
                or not isinstance(package.get('package_files_sha256'), dict)):
            raise ValueError('Each versioned package needs a path and complete frozen file hashes')
        root = Path(package['path']); root = (base / root).resolve() if not root.is_absolute() else root.resolve()
        files = package['package_files_sha256']
        try:
            with (root / 'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
                metadata = {row['sample_id']: row for row in csv.DictReader(stream)}
            listing = json.loads((root / 'site-list.json').read_text())
            sites = {row['site_id']: row for row in listing['sites']}
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append({'package': str(root), 'reason': 'version source mapping unavailable: ' + str(error)})
            metadata = {}; sites = {}
        ids = sorted({Path(name).parts[1] for name in files
                      if len(Path(name).parts) == 3 and Path(name).parts[0] == 'samples'
                      and Path(name).name == 'annotation.json'})
        for sid in ids:
            prefix = 'samples/' + sid + '/'
            sample_files = {name[len(prefix):]: value for name, value in files.items() if name.startswith(prefix)}
            row = metadata.get(sid, {}); site = sites.get(row.get('site_id'), {})
            identity = {'files_sha256': sample_files,
                        'ground_truth_sha256': files.get('ground_truth/' + sid + '.json'),
                        'origin': {key: row.get(key) for key in ('site_id', 'site_category')},
                        'site_uri': site.get('uri')}
            occurrences.append({'sample_id': sid, 'version_id': digest(identity),
                                'package': str(root), 'sample_path': str(root / 'samples' / sid),
                                'sample_files_sha256': sample_files})
    grouped = defaultdict(lambda: defaultdict(list))
    for row in occurrences:
        grouped[row['sample_id']][row['version_id']].append(row)
    policy = manifest.get('version_policy', {'schema_version': POLICY, 'supersedes': []})
    if (not isinstance(policy, dict) or set(policy) != {'schema_version', 'supersedes'}
            or policy.get('schema_version') != POLICY or not isinstance(policy.get('supersedes'), list)):
        raise ValueError('Explicit qc-sample-versions-1 supersedes policy required')
    links = defaultdict(dict)
    for link in policy['supersedes']:
        if (not isinstance(link, dict) or set(link) != {'sample_id', 'previous', 'current', 'reason'}
                or any(not isinstance(link.get(key), str) or not link[key].strip() for key in link)):
            raise ValueError('A supersedes relation needs sample_id, previous, current and reason')
        sid, old, new = link['sample_id'], link['previous'], link['current']
        if old == new or old not in grouped.get(sid, {}) or new not in grouped.get(sid, {}):
            errors.append({'sample_id': sid, 'reason': 'supersedes references missing or identical content versions'})
        elif old in links[sid]:
            errors.append({'sample_id': sid, 'reason': 'ambiguous/duplicate supersedes successor'})
        else:
            links[sid][old] = new
    effective = []; copies = []; superseded = []
    for sid, versions in sorted(grouped.items()):
        heads = set(versions) - set(links[sid])
        valid = len(heads) == 1
        head = next(iter(heads)) if valid else None
        for version in versions:
            visited = set(); cursor = version
            while cursor in links[sid] and cursor not in visited:
                visited.add(cursor); cursor = links[sid][cursor]
            if cursor in visited or cursor != head:
                valid = False
        if not valid:
            errors.append({'sample_id': sid, 'reason': 'conflicting repeated sample_id versions need a unique acyclic explicit supersedes chain'})
            continue
        for version, rows in sorted(versions.items()):
            ordered = sorted(rows, key=lambda row: (row['package'], row['sample_path']))
            if version == head:
                effective.append(ordered[0])
                copies.extend({**row, 'same_as': ordered[0]['sample_path']} for row in ordered[1:])
            else:
                superseded.extend({**row, 'superseded_by_version': head} for row in ordered)
    return {'schema_version': 'qc-version-comparison-1', 'status': 'FAIL' if errors else 'PASS',
            'occurrence_count': len(occurrences), 'effective_samples': effective,
            'identical_copies': copies, 'superseded': superseded, 'errors': errors,
            'policy': policy, 'QC_approval': False, 'selection_uses_mtime': False}
