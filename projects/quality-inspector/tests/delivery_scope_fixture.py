"""Mechanical scope helper for disposable fixture packages only."""
import json
from pathlib import Path

from quality_inspector.cumulative import build_set_manifest, inspect_set
from quality_inspector.profiles import DEFAULT_DELIVERY_PROFILE


def freeze_scope(root, packages, *, supersedes=()):
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=False)
    profile = json.loads(DEFAULT_DELIVERY_PROFILE.read_text())
    profile.update(profile_id='SYNTHETIC-SCOPE-TEST',
                   authority='Explicit one-category offline fixture exception; never a production waiver')
    profile['targets'].update(expected_samples=None, category_share='report-only')
    profile['targets'].pop('expected_sites', None)
    profile_path = root / 'profile.json'; profile_path.write_text(json.dumps(profile))
    manifest_path = root / 'effective-set.json'
    manifest_path.write_text(json.dumps(build_set_manifest(packages, supersedes=supersedes)))
    report = inspect_set(manifest_path, profile_path)
    if report['cross_package_status'] != 'PASS':
        raise AssertionError('Synthetic fixture must mechanically pass: ' + repr(report['errors']))
    report_path = root / 'cross-package-report.json'; report_path.write_text(json.dumps(report))
    return manifest_path, report_path
