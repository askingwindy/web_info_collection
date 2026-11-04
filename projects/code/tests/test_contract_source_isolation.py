"""Capture contract identity uses only installed authority, never old samples."""
from pathlib import Path
import shutil
import tempfile
import unittest
from webcollect.production_quality import contract_identity

REPO = Path(__file__).resolve().parents[3]


class ContractSourceIsolationTests(unittest.TestCase):
    def test_no_request_tree_or_sample_library_is_needed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'projects/quality-inspector/quality_inspector'
            source = REPO / 'projects/quality-inspector/quality_inspector'
            package.mkdir(parents=True)
            shutil.copyfile(source / 'contract-authority.json', package / 'contract-authority.json')
            shutil.copytree(source / 'authority', package / 'authority')
            identity = contract_identity(root)
            self.assertEqual(identity['version'], 3)
            self.assertEqual(identity['authority_source'], 'installed-document-authority')
            self.assertEqual(len(identity['authority_files_sha256']), 7)
            self.assertFalse(any('samples/' in name for name in identity['authority_files_sha256']))
            (package / 'authority/附件A-字段说明.md').write_text('CONTROLLED tamper')
            with self.assertRaisesRegex(ValueError, 'authority document changed'):
                contract_identity(root)


if __name__ == '__main__': unittest.main()
