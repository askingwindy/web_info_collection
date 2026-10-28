"""Retired compatibility entry point; never inspect, move, or delete files.

The original approved18 cleanup selected entire results/verify_results trees.
Its release receipts cannot authorize cleanup of later production campaigns.
Keep this path so old commands fail safely instead of deleting newer evidence.
"""
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Retired legacy cleanup: report only; all filesystem mutations are disabled.",
        allow_abbrev=False,
    )
    # Accept the old invocation for an explicit retirement result. Values are
    # deliberately never resolved or opened, including the former output path.
    for option in ("--repo", "--verified-release", "--output", "--regression", "--isolation"):
        parser.add_argument(option, help="Deprecated; accepted but never read or written.")
    parser.add_argument("--execute", action="store_true", help="Refused: legacy deletion is retired.")
    parser.add_argument("--apply", action="store_true", help="Refused: this entry point cannot mutate files.")
    args = parser.parse_args(argv)
    refused = args.execute or args.apply
    result = {
        "status": "REFUSED" if refused else "RETIRED",
        "dry_run": True,
        "targets": [],
        "total_files": 0,
        "total_bytes": 0,
        "reason": "The approved18 whole-tree cleanup is retired; old PASS receipts do not authorize deleting later results or verification evidence.",
        "current_policy": "Only identified regenerable non-evidence caches may be handled separately, with a recoverable destination and per-file SHA256 receipt. Preserve original data, failures, ledgers, reviews, and referenced build/verification files.",
        "guidance": [
            "projects/code/README.md",
            "projects/prd/真实试点执行说明-20261028.md",
            "verify_results/pilot1000-20261028-r01/cleanup-manifest-r01.json",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
