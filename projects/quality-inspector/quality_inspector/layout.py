"""Discover customer packages and legacy batches without guessing their contents.

All consumers use this module so a flat customer package is the QC input, rather
than an internal capture directory that happens to contain similar samples.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Layout:
    root: Path
    kind: str
    samples: list[Path]
    errors: list[str]

    @property
    def annotations(self):
        return [sample / 'annotation.json' for sample in self.samples]

    @property
    def batches(self):
        return sorted({self.batch_for(sample) for sample in self.samples})

    def batch_for(self, sample):
        return self.root if self.kind == 'customer-flat' else Path(sample).parent.parent

    def ground_truth(self, sample):
        sample = Path(sample)
        if self.kind == 'customer-flat':
            return self.root / 'ground_truth' / (sample.name + '.json')
        return self.batch_for(sample) / 'evidence' / sample.name / 'ground_truth.json'

    def native_evidence(self, sample):
        if self.kind == 'customer-flat':
            return None  # Internal logs are not part of the customer contract.
        return self.batch_for(sample) / 'evidence' / Path(sample).name


def discover(dataset):
    root = Path(dataset).resolve()
    errors = []
    flat = root / 'samples'
    legacy = sorted(p / 'samples' for p in root.iterdir()
                    if p.is_dir() and p.name != 'samples' and (p / 'samples').exists()) if root.is_dir() else []
    if flat.exists() and legacy:
        errors.append('Mixed flat samples/ and legacy batch samples/ layouts are ambiguous.')
    kind = 'customer-flat' if flat.exists() else 'legacy-batches'
    containers = [flat] if flat.exists() else legacy
    samples = []
    for container in containers:
        if not container.is_dir() or container.is_symlink():
            errors.append('Samples container is not an ordinary directory: ' + str(container))
            continue
        for child in sorted(container.iterdir()):
            if not child.is_dir() or child.is_symlink():
                errors.append('Unexpected file or symlink in samples/: ' + str(child))
                continue
            # Include incomplete sample directories so they fail rather than vanish.
            samples.append(child)
            if not (child / 'annotation.json').is_file():
                errors.append('Sample directory has no annotation.json: ' + str(child))
    if not samples:
        errors.append('No samples found under samples/<id>/ or <batch>/samples/<id>/.')
    return Layout(root, kind, samples, errors)


def package_document_paths(root):
    """Document roles are filenames/explicit declarations, never internal logs."""
    return {
        'readme': ['README.md'],
        'fields': ['附件A-字段说明.md', '字段说明.md', 'docs/字段说明.md', 'docs/附件A-字段说明.md'],
        'synthesis': ['合成方式说明.md', 'docs/合成方式说明.md', 'docs/本候选标注修订说明.md'],
        'source': ['来源与合规说明.md', '来源说明.md', 'docs/来源与合规说明.md',
                   'docs/历史来源与采集方式说明.md', 'docs/合成方式说明.md'],
    }


def sample_root(path):
    """Normalize a report's sample directory through the shared layout contract."""
    return Path(path).resolve()
