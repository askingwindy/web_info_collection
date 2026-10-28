"""Hand-built QC records test report binding, not the checker itself."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/finalize_candidate_reports.py"
SPEC = importlib.util.spec_from_file_location("finalize_candidate_reports", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def fixture(root, decisions=None, attempts=True):
    source = root / "A"
    batch = source / "batch"
    batch.mkdir(parents=True)
    manifest = {"sites": [{"site_id": "S000001", "uri": "https://example.org/", "site_category": "学习教育"}],
                "configuration": {"task_interval_seconds": 1}, "sample_kind": "UNIT_TEST_ONLY"}
    if attempts:
        manifest["attempts"] = [{"status": "rejected", "error": "actual test rejection"}]
    write_json(batch / "manifest.json", manifest)
    records = []
    decisions = decisions or [{"REVIEW_VISUAL_ALIGNMENT": "PASS"}]
    rule_ids = sorted({rid for values in MODULE.DEPENDENCIES.values() for rid in values}
                      | {"REVIEW_" + s for s in MODULE.SEMANTIC})
    metadata = ["sample_id,site_id,site_category"]
    for number, overrides in enumerate(decisions, 1):
        sid = "S000001_sample_" + str(number).zfill(6)
        sample = batch / "samples" / sid
        (sample / "images").mkdir(parents=True)
        (sample / "ui_tree").mkdir()
        steps, evidence = [], {}
        for frame in range(1, 7):
            image = "images/step_" + str(frame).zfill(3) + ".png"
            tree = "ui_tree/step_" + str(frame).zfill(3) + ".json"
            (sample / image).write_bytes(("UNIT TEST SYNTHETIC EVIDENCE " + sid + str(frame)).encode())
            write_json(sample / tree, {"unit_test_fixture": True, "frame": frame})
            evidence.update({image: digest(sample / image), tree: digest(sample / tree)})
            steps.append({"step_id": frame, "image_path": image, "ui_tree_path": tree,
                          "action": {"action_type": "complete" if frame == 6 else "click"}})
        annotation = {"sample_id": sid, "task_type": ["数据查看"], "steps": steps}
        write_json(sample / "annotation.json", annotation)
        checks = []
        for rid in rule_ids:
            if overrides.get(rid) == "MISSING":
                continue
            check = {"rule_id": rid, "status": overrides.get(rid, "PASS"), "reason": "UNIT TEST expected rule evidence " + rid}
            if rid.startswith("REVIEW_"):
                check["reviewer"] = {"kind": "ai", "name": "UNIT TEST ONLY"}
            checks.append(check)
        records.append({"sample_id": sid, "sample_path": str(sample), "annotation_sha256": digest(sample / "annotation.json"),
                        "evidence_sha256": evidence, "local_checks": checks,
                        "local_acceptance_status": "PASS"})  # deliberately cannot supply missing decisions
        metadata.append(sid + ",S000001,学习教育")
    (batch / "metadata.csv").write_text("\n".join(metadata) + "\n", encoding="utf-8")
    (batch / "qc_report.md").write_text("Original builder report", encoding="utf-8")
    (source / "README.md").write_text("Original candidate README", encoding="utf-8")
    (source / "docs").mkdir()
    (source / "docs/来源与合规说明.md").write_text("Original source note", encoding="utf-8")
    write_json(source / "candidate_manifest.json", {"document_roles": {"source": "docs/来源与合规说明.md"}})
    for directory in [batch, source]:
        (directory / "SHA256SUMS").write_text("".join(digest(p) + "  " + p.relative_to(directory).as_posix() + "\n"
                                                     for p in sorted(directory.rglob("*")) if p.is_file() and p != directory / "SHA256SUMS"))
    report = {"program": "quality-inspector", "version": "UNIT TEST ONLY", "dataset": str(source),
              "sample_count": len(records), "samples": records, "status": "PASS", "local_acceptance_status": "PASS",
              "review_import": {"accepted_count": 999}, "package_files_sha256": files(source),
              "duplicates": {"route1": {"pairs": []}, "route2": {"confirmed_pairs": []},
                             "route3": {"candidates": []}, "route4": {"candidates": []}}}
    qc = root / "qc.json"
    write_json(qc, report)
    return source, qc, report


def payload(path):
    return json.loads(path.read_text(encoding="utf-8").split("```json\n", 1)[1].split("\n```", 1)[0])


class FinalizeReports(unittest.TestCase):
    def test_duplicate_route_scope_counts_are_actual_pairs(self):
        report = {"duplicates": {"route1": {"pairs": [{"sample_ids": ["a", "b"]}]},
                                  "route2": {"confirmed_pairs": []},
                                  "route3": {"candidates": [{"sample_ids": ["a", "b"]}]},
                                  "route4": {"candidates": []}}}
        within = MODULE.duplicate_counts(report, {"a", "b"})
        crossing = MODULE.duplicate_counts(report, {"a"})
        self.assertEqual(within["route1"]["whole_package_candidates"], 1)
        self.assertEqual(within["route1"]["within_batch_candidates"], 1)
        self.assertEqual(crossing["route1"]["within_batch_candidates"], 0)
        self.assertEqual(crossing["route1"]["cross_batch_candidates_involving_this_batch"], 1)
        self.assertEqual(crossing["route3"]["whole_package_candidates"], 1)
        missing = MODULE.duplicate_counts({}, {"a"})
        self.assertIsNone(missing["route1"]["whole_package_candidates"])

    def test_actual_dependency_fail_and_pending_cannot_become_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, qc, _ = fixture(root, [{"REVIEW_VISUAL_ALIGNMENT": "FAIL"},
                                           {"REVIEW_VISUAL_ALIGNMENT": "REVIEW_REQUIRED"},
                                           {"REVIEW_TERMINAL_SEMANTICS": "REVIEW_REQUIRED"}])
            before = files(source)
            result = MODULE.finalize(source, qc, root / "B")
            data = payload(root / "B/batch/qc_report.md")
            self.assertEqual([s["mapped_seventeen_item_status"] for s in data["samples"]], ["FAIL", "REVIEW_REQUIRED", "REVIEW_REQUIRED"])
            self.assertEqual(data["seventeen_items"][7]["status"], "FAIL")
            self.assertEqual(data["seventeen_items"][15]["status"], "FAIL")
            self.assertEqual(data["seventeen_items"][10]["status"], "REVIEW_REQUIRED")
            self.assertEqual(files(source), before)
            self.assertEqual(result["final_local_acceptance"], "NOT_DECLARED")
            self.assertEqual(data["review_coverage"]["imported_full_review_counts"], {"ai": 1, "human": 0})
            self.assertEqual(data["statistics"]["step_count_distribution"], {"6": 3})
            self.assertEqual(data["statistics"]["effective_step_distribution"], {"5": 3})
            self.assertEqual(data["rejections"]["rejected_count"], 1)
            for relative, expected in result["business_files_sha256"].items():
                self.assertEqual(digest(root / "B" / relative), expected)
            for directory in [root / "B/batch", root / "B"]:
                manifest = directory / "SHA256SUMS"
                entries = dict((rel, h) for h, rel in (line.split("  ", 1) for line in manifest.read_text().splitlines()))
                self.assertEqual(entries, {p.relative_to(directory).as_posix(): digest(p) for p in directory.rglob("*") if p.is_file() and p != manifest})

    def test_missing_dependency_remains_pending_despite_overall_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, qc, _ = fixture(root, [{"C12": "MISSING"}])
            MODULE.finalize(source, qc, root / "B")
            data = payload(root / "B/batch/qc_report.md")
            for number in [13, 14, 15]:
                self.assertEqual(data["seventeen_items"][number - 1]["status"], "REVIEW_REQUIRED")
            self.assertIn("Missing dependency", json.dumps(data))

    def test_stale_package_or_missing_package_binding_rejected_before_copy(self):
        for change in ["mutate_file", "omit_hash", "extra_hash"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, qc, report = fixture(root)
                if change == "mutate_file":
                    (source / "README.md").write_text("changed after QC")
                elif change == "omit_hash":
                    report["package_files_sha256"].pop("README.md")
                    write_json(qc, report)
                else:
                    report["package_files_sha256"]["missing-file"] = "0" * 64
                    write_json(qc, report)
                with self.assertRaisesRegex(ValueError, "package_files_sha256"):
                    MODULE.finalize(source, qc, root / "B")
                self.assertFalse((root / "B").exists())

    def test_annotation_and_evidence_bindings_required(self):
        for change in ["annotation", "missing_tree", "stale_tree"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, qc, report = fixture(root)
                sample = report["samples"][0]
                if change == "annotation":
                    sample["annotation_sha256"] = "0" * 64
                elif change == "missing_tree":
                    sample["evidence_sha256"].pop("ui_tree/step_001.json")
                else:
                    sample["evidence_sha256"]["ui_tree/step_001.json"] = "0" * 64
                write_json(qc, report)
                with self.assertRaisesRegex(ValueError, "SHA binding"):
                    MODULE.finalize(source, qc, root / "B")
                self.assertFalse((root / "B").exists())

    def test_missing_actual_evidence_rejected_even_if_package_inventory_refreshed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, qc, report = fixture(root)
            sample = Path(report["samples"][0]["sample_path"])
            (sample / "images/step_001.png").unlink()
            report["package_files_sha256"] = files(source)
            write_json(qc, report)
            with self.assertRaisesRegex(ValueError, "Missing sample evidence"):
                MODULE.finalize(source, qc, root / "B")

    def test_wrong_dataset_and_omitted_sample_rejected(self):
        for change in ["dataset", "sample"]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, qc, report = fixture(root)
                if change == "dataset":
                    report["dataset"] = str(root / "other")
                else:
                    report["samples"] = []
                    report["sample_count"] = 0
                write_json(qc, report)
                with self.assertRaises(ValueError):
                    MODULE.finalize(source, qc, root / "B")

    def test_no_overwrite_or_nested_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, qc, _ = fixture(root)
            out = root / "B"
            out.mkdir()
            (out / "sentinel").write_text("keep")
            with self.assertRaises(FileExistsError):
                MODULE.finalize(source, qc, out)
            self.assertEqual((out / "sentinel").read_text(), "keep")
            with self.assertRaises(ValueError):
                MODULE.finalize(source, qc, source / "nested")

    def test_missing_history_and_account_facts_not_fabricated(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, qc, _ = fixture(root, attempts=False)
            MODULE.finalize(source, qc, root / "B")
            data = payload(root / "B/batch/qc_report.md")
            self.assertIsNone(data["rejections"]["rejected_count"])
            source_note = payload(root / "B/docs/来源与合规说明.md")
            self.assertEqual(source_note["facts"][0]["account_and_redaction_status"], "REVIEW_REQUIRED_NOT_RECORDED")
            self.assertEqual(source_note["facts"][0]["frequency_configuration"], {"task_interval_seconds": 1})

    def test_missing_local_checks_never_uses_accepted_count_or_global_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, qc, report = fixture(root)
            report["samples"][0].pop("local_checks")
            write_json(qc, report)
            MODULE.finalize(source, qc, root / "B")
            data = payload(root / "B/batch/qc_report.md")
            self.assertEqual({x["status"] for x in data["seventeen_items"]}, {"REVIEW_REQUIRED"})
            self.assertEqual(data["review_coverage"]["imported_full_review_counts"], {"ai": 0, "human": 0})


if __name__ == "__main__":
    unittest.main()
