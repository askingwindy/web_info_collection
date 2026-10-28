"""The obsolete approved18 cleanup must never affect later campaign evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/cleanup_legacy_process.py"


class RetiredCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / "results/baselines/approved18-20261024"
        self.package = self.root / "results/delivery/20261024-client18-contract-v2"
        for name in (
            "results/baselines/approved18-20261024/frozen.txt",
            "results/delivery/20261024-client18-contract-v2/original.txt",
            "results/delivery/later-release/annotation.json",
            "results/pilot1000-20261028-r01/state/registry.sqlite3",
            "verify_results/client18-contract-20261024/review.json",
            "verify_results/pilot1000-20261028-r01/failure.json",
            "projects/code/webcollect/source.py",
            "projects/code/webcollect/__pycache__/source.pyc",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic preservation fixture\n")
        frozen = self.baseline / "frozen.txt"
        (self.baseline / "SHA256SUMS").write_text(
            hashlib.sha256(frozen.read_bytes()).hexdigest() + "  frozen.txt\n"
        )
        archive = self.package.with_suffix(".zip")
        archive.write_bytes(b"synthetic archive binding")
        receipts = {
            "release.json": {
                "status": "PASS", "package": str(self.package), "baseline": str(self.baseline),
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            },
            "regression.json": {"status": "PASS", "logs": []},
            "isolation.json": {"status": "PASS", "workspace": str(self.root / "absent")},
        }
        for name, content in receipts.items():
            (self.root / name).write_text(json.dumps(content))

    def snapshot(self):
        return {
            p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.root.rglob("*") if p.is_file()
        }

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            capture_output=True, text=True, check=False,
        )

    def legacy_arguments(self):
        return [
            "--repo", str(self.root), "--verified-release", str(self.root / "release.json"),
            "--regression", str(self.root / "regression.json"),
            "--isolation", str(self.root / "isolation.json"),
            "--output", str(self.root / "cleanup-receipt.json"),
        ]

    def test_default_only_reports_retirement_without_mutating_files(self):
        before = self.snapshot()
        completed = self.invoke()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "RETIRED")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["targets"], [])
        self.assertEqual(self.snapshot(), before)

    def test_old_pass_receipts_cannot_enable_execute_or_apply(self):
        before = self.snapshot()
        for option in ("--execute", "--apply"):
            with self.subTest(option=option):
                completed = self.invoke(*self.legacy_arguments(), option)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertEqual(json.loads(completed.stdout)["status"], "REFUSED")
                self.assertEqual(self.snapshot(), before)
                self.assertFalse((self.root / "cleanup-receipt.json").exists())

    def test_legacy_dry_run_does_not_write_former_output_path(self):
        output = self.root / "cleanup-receipt.json"
        output.write_text("preserve existing receipt\n")
        before = self.snapshot()
        completed = self.invoke(*self.legacy_arguments())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_nonexistent_legacy_inputs_are_never_opened(self):
        completed = self.invoke("--repo", "/missing/repository", "--verified-release", "/missing/receipt")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "RETIRED")


if __name__ == "__main__":
    unittest.main()
