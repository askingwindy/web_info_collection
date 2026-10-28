import tempfile
import unittest
from pathlib import Path
from webcollect.production_quality import ExactImageIndex, exact_conflicts


class ExactIndexTests(unittest.TestCase):
    def image(self, root, sample, content):
        path = root / 'samples' / sample / 'images' / 'step_001.png'
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        return path

    def test_matches_exhaustive_and_incrementally_adds_accepted_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.image(root / 'old', 'first', b'first')
            index = ExactImageIndex([root, root / 'old'])
            sample = self.image(root / 'new', 'second', b'first').parent.parent
            self.assertEqual(index.conflicts(sample), exact_conflicts(sample, [root]))
            # A rejected candidate is moved away; it never enters the accepted set.
            sample.rename(root / 'rejected')
            accepted = self.image(root / 'new', 'third', b'third').parent.parent
            self.assertEqual(index.conflicts(accepted), [])
            index.add_sample(accepted)
            self.assertEqual(index.verify_snapshot()['image_count'], 2)
            next_sample = self.image(root / 'new', 'fourth', b'third').parent.parent
            self.assertEqual(index.conflicts(next_sample), exact_conflicts(next_sample, [root]))

    def test_boundary_verification_detects_same_size_edit_even_with_restored_mtime(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.image(root, 'old', b'abc')
            before = path.stat()
            index = ExactImageIndex([root])
            path.write_bytes(b'xyz')
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            with self.assertRaisesRegex(ValueError, '未登记变化'):
                index.verify_snapshot()

    def test_unregistered_addition_or_removal_cannot_silently_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.image(root, 'old', b'old')
            index = ExactImageIndex([root])
            extra = self.image(root, 'extra', b'new')
            with self.assertRaises(ValueError):
                index.verify_snapshot()
            extra.unlink()
            path.unlink()
            with self.assertRaises(ValueError):
                index.verify_snapshot()


if __name__ == '__main__':
    unittest.main()
