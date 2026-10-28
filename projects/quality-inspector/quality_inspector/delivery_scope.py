"""Read-only delivery membership and cross-package mechanical binding."""
import json
from pathlib import Path

from .contract import digest
from .cumulative import inspect_set
from .profiles import package_files
from .reviews import sha

WRAPPING_FILES = frozenset({'qc_report.md', 'SHA256SUMS'})


def _path(value):
    path = Path(value).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Delivery scope paths cannot contain symlinks')
    return path.resolve()


def _ref(value):
    path = _path(value)
    if not path.is_file():
        raise ValueError('Delivery scope bound file is missing: ' + str(path))
    return {'path': str(path), 'sha256': sha(path)}


def payload_files(files):
    """Only the existing report/checksum wrapping cycle is excluded."""
    return {key: value for key, value in files.items() if key not in WRAPPING_FILES}


def verify_delivery_scope(effective_set_path, cross_package_report_path, *, dataset,
                          phase='payload', expected_contract=None):
    """Verify a declared member or its byte-identical final relocation.

    Rechecks existing deterministic rules; never dispatches a model or infers a
    semantic decision. A package containing superseded samples must first have
    an explicit effective payload assembled/frozen; it cannot be sealed as-is.
    """
    if effective_set_path is None or cross_package_report_path is None:
        raise ValueError('Explicit effective-set and cross-package report are required for delivery')
    if phase not in ('payload', 'final'):
        raise ValueError('Delivery scope phase must be payload or final')
    manifest_ref = _ref(effective_set_path); report_ref = _ref(cross_package_report_path)
    manifest = json.loads(Path(manifest_ref['path']).read_text())
    report = json.loads(Path(report_ref['path']).read_text())
    if (report.get('schema_version') != 'qc-cumulative-report-1'
            or any(report.get(key) != 'PASS' for key in ('status', 'mechanical_status', 'cross_package_status'))
            or report.get('manifest') != manifest or report.get('manifest_sha256') != digest(manifest)):
        raise ValueError('A PASS cross-package report bound to the exact effective-set is required')
    profile = report.get('local_profile', {})
    profile_ref = _ref(profile.get('path', ''))
    if profile_ref['sha256'] != profile.get('sha256'):
        raise ValueError('Cross-package profile changed')
    current = inspect_set(manifest_ref['path'], profile_ref['path'])
    if current['cross_package_status'] != 'PASS':
        raise ValueError('Current effective-set no longer passes cross-package checks')
    for key in ('manifest_sha256', 'contract_sha256', 'local_profile', 'sample_count', 'site_count',
                'input_files_sha256', 'version_comparison', 'statistics'):
        if report.get(key) != current[key]:
            raise ValueError('Cross-package report binding changed: ' + key)
    if expected_contract is not None and current['contract_sha256'] != expected_contract:
        raise ValueError('Cross-package and payload contract identities differ')
    dataset = _path(dataset); actual = package_files(dataset)
    actual_payload = payload_files(actual)
    versions = current['version_comparison']
    usable = {row['sample_path'] for row in versions['effective_samples'] + versions['identical_copies']}
    candidates = []
    for root, files in current['input_files_sha256'].items():
        sample_paths = {str(Path(root) / 'samples' / Path(name).parts[1]) for name in files
                        if len(Path(name).parts) == 3 and Path(name).parts[0] == 'samples'
                        and Path(name).name == 'annotation.json'}
        if (sample_paths and sample_paths <= usable and actual_payload == payload_files(files)
                and (phase == 'final' or dataset == Path(root))):
            candidates.append(root)
    if not candidates:
        raise ValueError('Dataset is not an exact current effective member payload; superseded/partial/changed inputs cannot be sealed')
    member = min(candidates)
    if (package_files(dataset) != actual or _ref(effective_set_path) != manifest_ref
            or _ref(cross_package_report_path) != report_ref or _ref(profile_ref['path']) != profile_ref
            or any(package_files(root) != files for root, files in current['input_files_sha256'].items())):
        raise ValueError('Delivery scope inputs changed during verification')
    return {'schema_version': 'qc-delivery-scope-1', 'effective_set': manifest_ref,
            'cross_package_report': report_ref, 'manifest_sha256': current['manifest_sha256'],
            'contract_sha256': current['contract_sha256'], 'source_member': member,
            'package_roots': sorted(current['input_files_sha256']),
            'payload_files_sha256': actual_payload, 'payload_sha256': digest(actual_payload),
            'effective_sample_count': current['sample_count'], 'cross_package_status': 'PASS',
            'semantic_review_repeated': False, 'QC_approval': False}
