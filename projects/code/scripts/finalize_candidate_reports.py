#!/usr/bin/env python3
"""Render evidence-bound QC documents into a new, still unaccepted candidate.

This is a report transformer, not a checker or reviewer.  Final independent QC
and document review must run outside the output package; their results are never
written back into the package they authenticate.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil


STATES = {"PASS", "FAIL", "REVIEW_REQUIRED"}
SEMANTIC = ["VISUAL_ALIGNMENT", "TERMINAL_SEMANTICS", "LANGUAGE", "PRIVACY", "SUBSTANTIVE_DIFFERENCE"]
DEPENDENCIES = {
    1: ["C01", "C02", "C04"], 2: ["C05"], 3: ["C06"],
    4: ["C06"], 5: ["C05"], 6: ["C11"], 7: ["C08"],
    8: ["C07", "CAPTURE_INTEGRITY", "REVIEW_VISUAL_ALIGNMENT"],
    9: ["C09"], 10: ["C10"],
    11: ["C10", "FINAL_MACHINE_EVIDENCE", "REVIEW_TERMINAL_SEMANTICS"],
    12: ["C03"], 13: ["C12", "REVIEW_LANGUAGE"],
    14: ["C12", "REVIEW_LANGUAGE"], 15: ["C12", "REVIEW_LANGUAGE"],
    16: ["CAPTURE_INTEGRITY", "REVIEW_VISUAL_ALIGNMENT"],
    17: ["REVIEW_PRIVACY"],
}
TITLES = ["字段完整", "截图数量与连续命名", "图树文件存在", "截图分辨率一致", "步骤编号连续",
          "有效操作步数", "坐标与目标框", "目标引用及可见图树一致", "动作工具及参数", "成功状态",
          "末步完成及终态", "任务类型", "中文文字质量", "无内部定位信息", "无采集过程用语",
          "相邻截图与动作结果一致", "无真实个人信息"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def aggregate(values):
    values = list(values)
    return "FAIL" if "FAIL" in values else "REVIEW_REQUIRED" if not values or any(v != "PASS" for v in values) else "PASS"


def child(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Invalid package-relative path: " + str(relative))
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("Outside/symlink package path: " + relative)
    return path


def inventory(root):
    found = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not supported: " + str(path))
        if path.is_file():
            found[path.relative_to(root).as_posix()] = sha(path)
    return found


def sample_evidence(sample, annotation):
    steps = annotation.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Missing sample step evidence: " + str(sample))
    found = {}
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Invalid sample step evidence")
        for key in ["image_path", "ui_tree_path"]:
            relative = step.get(key)
            path = child(sample, relative)
            if not path.is_file():
                raise ValueError("Missing sample evidence: " + str(path))
            found[relative] = sha(path)
    return found


def validate_binding(source, report):
    if not isinstance(report, dict) or report.get("program") != "quality-inspector":
        raise ValueError("An independent quality-inspector report is required")
    if not isinstance(report.get("dataset"), str) or Path(report["dataset"]).resolve() != source:
        raise ValueError("QC report dataset does not match --input")
    files = inventory(source)
    bound = report.get("package_files_sha256")
    if not isinstance(bound, dict) or not bound or bound != files:
        raise ValueError("Stale/incomplete package_files_sha256 binding")
    records = report.get("samples")
    if not isinstance(records, list) or report.get("sample_count") != len(records):
        raise ValueError("Invalid QC sample inventory")
    actual = {p.parent.resolve() for p in source.glob("*/samples/*/annotation.json")}
    if not actual:
        raise ValueError("No checked samples in candidate")
    seen, ids, loaded = set(), set(), []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("sample_path"), str):
            raise ValueError("Missing QC sample path")
        sample = Path(record["sample_path"]).resolve()
        if sample not in actual or sample in seen:
            raise ValueError("Unknown/duplicate QC sample path")
        annotation = read(sample / "annotation.json")
        if not isinstance(annotation, dict) or not annotation.get("sample_id"):
            raise ValueError("Missing sample identity")
        sid = annotation["sample_id"]
        if sid in ids or record.get("sample_id") != sid:
            raise ValueError("Duplicate/inconsistent sample identity")
        if record.get("annotation_sha256") != sha(sample / "annotation.json"):
            raise ValueError("Stale/missing annotation SHA binding: " + sid)
        evidence = sample_evidence(sample, annotation)
        if not evidence or record.get("evidence_sha256") != evidence:
            raise ValueError("Stale/missing image/tree SHA binding: " + sid)
        seen.add(sample)
        ids.add(sid)
        loaded.append((sample, annotation, record))
    if seen != actual:
        raise ValueError("QC report omits actual candidate samples")
    return files, loaded


def mapped_items(record):
    checks = record.get("local_checks", [])
    checks = checks if isinstance(checks, list) else []
    items = []
    for number, dependencies in DEPENDENCIES.items():
        results = []
        for rid in dependencies:
            hits = [c for c in checks if isinstance(c, dict) and c.get("rule_id") == rid]
            results.append({"rule_id": rid, "status": aggregate(c.get("status") for c in hits),
                            "reason": "Missing dependency in sample.local_checks" if not hits else None,
                            "source_results": hits})
        items.append({"item": number, "title": TITLES[number - 1], "status": aggregate(c["status"] for c in results),
                      "depends_on": dependencies, "dependencies": results})
    return items


def coverage(records):
    full = {"ai": [], "human": []}
    rule_counts = {kind: Counter() for kind in full}
    for record in records:
        checks = record.get("local_checks", [])
        checks = checks if isinstance(checks, list) else []
        for kind in full:
            decided = set()
            for check in checks:
                if not isinstance(check, dict):
                    continue
                reviewer = check.get("reviewer", {})
                rid = check.get("rule_id")
                if (rid in {"REVIEW_" + s for s in SEMANTIC} and isinstance(reviewer, dict)
                        and reviewer.get("kind") == kind and reviewer.get("name")
                        and check.get("status") in {"PASS", "FAIL"} and check.get("reason")):
                    decided.add(rid)
            rule_counts[kind].update(decided)
            if len(decided) == len(SEMANTIC):
                full[kind].append(record["sample_id"])
    count = len(records)
    return {"evidence_bound_imported_full_review_samples": full,
            "imported_full_review_counts": {k: len(v) for k, v in full.items()},
            "imported_decided_rule_counts": {k: dict(v) for k, v in rule_counts.items()},
            "imported_human_full_review_ratio": len(full["human"]) / count if count else None,
            "reviews_performed_by_this_tool": {"ai": 0, "human": 0},
            "random_human_sampling_performed_by_this_tool": False,
            "meaning": "Counts only imported, bound, definite semantic rule decisions; acceptance/import alone is not full review. Reviewer identity is not authenticated by this tool."}


def duplicate_counts(report, sample_ids):
    output = {}
    for route, key in [("route1", "pairs"), ("route2", "confirmed_pairs"), ("route3", "candidates"), ("route4", "candidates")]:
        data = report.get("duplicates", {}).get(route, {})
        pairs = data.get(key)
        valid = isinstance(pairs, list) and all(isinstance(p, dict) and isinstance(p.get("sample_ids"), list)
                                               and len(p["sample_ids"]) == 2 for p in pairs)
        if valid:
            within = [p for p in pairs if set(p["sample_ids"]) <= sample_ids]
            crossing = [p for p in pairs if set(p["sample_ids"]) & sample_ids and not set(p["sample_ids"]) <= sample_ids]
        output[route] = {"whole_package_candidates": len(pairs) if valid else None,
                         "within_batch_candidates": len(within) if valid else None,
                         "cross_batch_candidates_involving_this_batch": len(crossing) if valid else None,
                         "within_batch_pairs": within if valid else None,
                         "cross_batch_pairs": crossing if valid else None,
                         "status": "EXECUTED" if valid else "REVIEW_REQUIRED",
                         "algorithm": data.get("algorithm", data.get("comparison")),
                         "customer_algorithm_equivalence": data.get("customer_algorithm_equivalence", "NOT_CLAIMED")}
    return output


def statistics(batch, annotations, manifest):
    metadata = {}
    if (batch / "metadata.csv").is_file():
        with (batch / "metadata.csv").open(encoding="utf-8-sig", newline="") as stream:
            metadata = {row.get("sample_id"): row for row in csv.DictReader(stream)}
    bysite = {row.get("site_id"): row for row in manifest.get("sites", []) if isinstance(row, dict)}
    sites, categories, kinds, steps, effective = Counter(), Counter(), Counter(), Counter(), Counter()
    for annotation in annotations:
        row = metadata.get(annotation["sample_id"], {})
        sid = row.get("site_id")
        if not sid:
            match = re.fullmatch(r"(.+)_sample_\d+", annotation["sample_id"])
            sid = match.group(1) if match else None
        site = bysite.get(sid, {})
        sites[site.get("uri") or sid or "UNKNOWN"] += 1
        categories[row.get("site_category") or site.get("site_category") or "UNKNOWN"] += 1
        kinds.update(annotation.get("task_type", []))
        flow = annotation.get("steps", [])
        steps[str(len(flow))] += 1
        actions = [s.get("action", {}).get("action_type") for s in flow]
        known = {"click", "double_click", "right_click", "drag", "select", "type", "hotkey", "scroll", "back", "open_url", "wait", "complete"}
        effective[str(sum(a not in {"wait", "complete"} for a in actions)) if all(a in known for a in actions) else "UNKNOWN"] += 1
    return {"sample_count": len(annotations), "sites": dict(sites), "site_categories": dict(categories),
            "task_types": dict(kinds), "step_count_distribution": dict(steps),
            "effective_step_distribution": dict(effective), "total_step_frames": sum(len(a.get("steps", [])) for a in annotations),
            "short_flow_samples": sum(a.get("short_flow") is True for a in annotations),
            "unknown_site_or_category_is_not_inferred": True}


def rejection_history(manifest):
    attempts = manifest.get("attempts")
    rejected = [r for r in attempts if isinstance(r, dict) and r.get("status") == "rejected"] if isinstance(attempts, list) else None
    return {"attempt_history_available": rejected is not None, "rejected_count": len(rejected) if rejected is not None else None,
            "reasons": dict(Counter(r.get("error") or r.get("reason") or "recorded rejection without reason" for r in rejected)) if rejected is not None else None,
            "records": rejected, "scope": "Recorded rejected collection attempts only; retained QC FAIL candidates are not silently counted as removed."}


def json_block(value):
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n"


def sums(root):
    manifest = root / "SHA256SUMS"
    manifest.write_text("".join(sha(p) + "  " + p.relative_to(root).as_posix() + "\n"
                                for p in sorted(root.rglob("*")) if p.is_file() and p != manifest), encoding="utf-8")


def finalize(source, qc, output):
    source, qc, output = Path(source).resolve(), Path(qc).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError("Candidate input directory missing")
    if output.exists():
        raise FileExistsError("Refuse to overwrite output candidate")
    if output.is_relative_to(source) or source.is_relative_to(output) or qc.is_relative_to(source) or qc.is_relative_to(output):
        raise ValueError("Candidate input/output and external QC report must be separate")
    report_sha, report = sha(qc), read(qc)
    originals, loaded = validate_binding(source, report)
    grouped = {}
    for sample, annotation, record in loaded:
        grouped.setdefault(sample.parent.parent, []).append((annotation, record))
    rendered, summaries, facts = {}, [], []
    for batch, entries in sorted(grouped.items()):
        relative = batch.relative_to(source).as_posix()
        manifest_path = batch / "manifest.json"
        manifest = read(manifest_path) if manifest_path.is_file() else {}
        records = [r for _, r in entries]
        sample_results = [{"sample_id": a["sample_id"], "reported_local_acceptance_status": r.get("local_acceptance_status", "REVIEW_REQUIRED"),
                           "mapped_seventeen_item_status": aggregate(x["status"] for x in mapped_items(r)),
                           "seventeen_items": mapped_items(r)} for a, r in entries]
        item_results = [{"item": n, "title": TITLES[n - 1], "status": aggregate(s["seventeen_items"][n - 1]["status"] for s in sample_results),
                         "depends_on": DEPENDENCIES[n], "sample_statuses": {s["sample_id"]: s["seventeen_items"][n - 1]["status"] for s in sample_results}}
                        for n in DEPENDENCIES]
        payload = {"input_qc_report": str(qc), "input_qc_report_sha256": report_sha, "input_candidate": str(source),
                   "source_qc_program": report.get("program"), "source_qc_version": report.get("version"),
                   "source_qc_local_acceptance_status": report.get("local_acceptance_status", "REVIEW_REQUIRED"),
                   "source_qc_status_scope": "whole_input_candidate",
                   "source_qc_sample_local_status_counts": dict(Counter(r.get("local_acceptance_status", "REVIEW_REQUIRED") for r in records)),
                   "seventeen_item_status": aggregate(x["status"] for x in item_results), "seventeen_items": item_results,
                   "samples": sample_results, "statistics": statistics(batch, [a for a, _ in entries], manifest),
                   "duplicates": duplicate_counts(report, {r["sample_id"] for r in records}),
                   "rejections": rejection_history(manifest), "review_coverage": coverage(records),
                   "final_document_review": "NOT_EXECUTED_AFTER_REWRITE", "final_independent_qc": "NOT_EXECUTED_ON_NEW_CANDIDATE",
                   "customer_actual_acceptance": "UNKNOWN", "qualified_delivery_count_declared": None}
        rendered[relative + "/qc_report.md"] = "# 本批独立质检证据记录\n\n" + (
            "以下逐项结果来自已绑定输入候选的独立QC报告及 sample.local_checks。缺依赖为待审，"
            "不从整体PASS反推17项，不把审核记录接入成功当成实际全轨迹审核。"
            "本工具只生成报告，没有执行AI或人工审核；本轮实际结论与来源逐项列于下方。\n\n"
            "文档更新后的最终文档审核及最终独立QC尚未执行。最终结果须保存在包外，不回写本包形成哈希与审核循环。\n\n") + json_block(payload)
        summaries.append({"batch": relative, **{k: payload[k] for k in ["statistics", "seventeen_item_status", "source_qc_sample_local_status_counts", "duplicates", "rejections", "review_coverage"]}})
        config = manifest.get("configuration", {})
        account_keys = [k for k in ["account_usage", "accounts", "login", "login_policy", "redaction", "privacy"] if k in manifest]
        facts.append({"batch": relative, "manifest": relative + "/manifest.json", "manifest_sha256": sha(manifest_path) if manifest_path.is_file() else None,
                      "sites_as_recorded": manifest.get("sites"), "sample_kind_as_recorded": manifest.get("sample_kind"),
                      "collection_configuration_as_recorded": config,
                      "collection_implementation_as_recorded": {k: manifest.get(k) for k in ["program_version", "browser_version", "playwright_version"]},
                      "frequency_configuration": {k: config[k] for k in ["task_interval_seconds", "default_settle_ms", "rate_limit", "access_frequency"] if isinstance(config, dict) and k in config},
                      "frequency_audit": "Configuration is not a full network-request frequency audit; unrecorded policy remains REVIEW_REQUIRED.",
                      "account_or_redaction_facts_as_recorded": {k: manifest[k] for k in account_keys},
                      "account_and_redaction_status": "RECORDED_DECLARATION_REQUIRES_REVIEW" if account_keys else "REVIEW_REQUIRED_NOT_RECORDED",
                      "permission_and_compliance_status": "REVIEW_REQUIRED_NOT_AUTHENTICATED_BY_THIS_TOOL"})
    candidate_manifest = read(source / "candidate_manifest.json") if (source / "candidate_manifest.json").is_file() else {}
    roles = candidate_manifest.get("document_roles", {})
    source_doc = roles.get("source", "docs/来源与合规说明.md")
    source_parts = Path(source_doc).parts if isinstance(source_doc, str) else ()
    if not source_parts or source_parts[0] != "docs" or Path(source_doc).suffix != ".md" or source_doc == "docs/质检报告回填说明.md":
        raise ValueError("Source explanation must be a Markdown file under docs/")
    child(source, source_doc)
    rendered[source_doc] = "# 来源与合规事实索引\n\n以下站点清单、类别和配置直接读取各批真实manifest；未记录的账号、脱敏、访问频率或许可事实保留待核对。隔离、公开、未登录等结论不能仅由工具名称或预期策略推断。\n\n" + json_block({"input_qc_report_sha256": report_sha, "facts": facts, "document_review": "NOT_EXECUTED_AFTER_REWRITE"})
    total = {"input_candidate": str(source), "input_qc_report": str(qc), "input_qc_report_sha256": report_sha,
             "source_qc_local_acceptance_status": report.get("local_acceptance_status", "REVIEW_REQUIRED"),
             "sample_count": len(loaded), "batch_count": len(grouped),
             "source_qc_sample_local_status_counts": dict(Counter(r.get("local_acceptance_status", "REVIEW_REQUIRED") for _, _, r in loaded)),
             "review_coverage": coverage([r for _, _, r in loaded]), "batches": summaries,
             "final_document_review": "NOT_EXECUTED_AFTER_REWRITE", "final_independent_qc": "NOT_EXECUTED_ON_NEW_CANDIDATE",
             "customer_actual_acceptance": "UNKNOWN", "qualified_delivery_count_declared": None}
    rendered["README.md"] = "# 独立交付候选与真实质检记录\n\n本候选已据独立QC输入报告补齐逐批17项、四路重复、分布及审核覆盖记录。以下状态属于输入候选和已绑定样本证据；本工具未执行新审核，不宣告本候选最终本地PASS。最终文档审核与独立QC必须在包外执行，不能回写形成循环。\n\n" + json_block(total)
    rendered["docs/质检报告回填说明.md"] = ("# 质检报告生成与证据边界\n\n输入独立报告SHA256：" + report_sha + "。\n\n"
        "先核对报告dataset、完整package_files_sha256、每条annotation及全部引用图树SHA，再复制到新目录。仅改本批qc_report、根README、来源说明、本说明与SHA256SUMS；样本和原始证据不变。\n\n"
        "§7逐项只聚合sample.local_checks依赖：FAIL优先，缺失、无效状态或待审依赖保持REVIEW_REQUIRED；整体PASS不提供任何缺失依赖。AI/人工覆盖只统计有来源及明确PASS/FAIL理由的证据绑定语义规则，不将导入数量当覆盖。\n\n"
        "本工具本轮实际执行AI审核0、人工审核0、随机人工抽检0。既有AI/人工声明与覆盖另按源报告事实记录，不伪造身份。采集拒收仅统计manifest可查记录，缺历史为null，保留中的QC失败不假装已淘汰。\n\n"
        "最终文档审核尚未执行；后续最终独立QC及审核结果在包外保存，不再回写本包。客户真实验收仍UNKNOWN。\n\n" + json_block({str(k): v for k, v in DEPENDENCIES.items()}))
    allowed = set(rendered) | {"SHA256SUMS"} | {b.relative_to(source).as_posix() + "/SHA256SUMS" for b in grouped}
    if inventory(source) != originals or sha(qc) != report_sha:
        raise ValueError("Input changed during report preparation")
    shutil.copytree(source, output)
    for relative, content in rendered.items():
        path = child(output, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for batch in grouped:
        sums(output / batch.relative_to(source))
    sums(output)
    after = inventory(output)
    unchanged = {rel: digest for rel, digest in originals.items() if rel not in allowed}
    changed_business = [rel for rel, digest in unchanged.items() if after.get(rel) != digest]
    unexpected = set(after) - set(originals) - allowed
    if changed_business or unexpected or inventory(source) != originals or sha(qc) != report_sha:
        raise ValueError("Preservation verification failed: " + repr(changed_business or sorted(unexpected)))
    return {"operation": "finalize_candidate_reports", "status": "REPORTS_WRITTEN_PENDING_FINAL_REVIEW", "output": str(output),
            "transformer_sha256": sha(Path(__file__)),
            "input": str(source), "qc": str(qc), "qc_sha256": report_sha, "input_files_unchanged": len(originals),
            "business_files_verified_unchanged": len(unchanged), "business_files_sha256": unchanged,
            "sample_count": len(loaded), "batch_count": len(grouped),
            "source_qc_sample_local_status_counts": total["source_qc_sample_local_status_counts"],
            "modified_documents": sorted(rel for rel in after if originals.get(rel) != after[rel]),
            "final_document_review": "NOT_EXECUTED", "final_local_acceptance": "NOT_DECLARED",
            "customer_actual_acceptance": "UNKNOWN", "output_root_manifest_sha256": sha(output / "SHA256SUMS")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--qc", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        receipt = finalize(args.input, args.qc, args.output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, "finalize_candidate_reports: " + str(error) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
