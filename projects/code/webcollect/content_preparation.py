"""Read-only advice for public-page preparation; every action belongs to collector."""
import asyncio
import hashlib
from importlib.resources import files
from pathlib import Path
import re

ALGORITHM_VERSION = "visible-content-preparation-3"
CONTENT_JS = files("webcollect").joinpath("content_preparation.js").read_text(encoding="utf-8")
OBSERVER_SHA256 = hashlib.sha256(CONTENT_JS.encode()).hexdigest()


def preparation_settings(task):
    """Validate bounded settings. A task may disable preparation explicitly."""
    value = task.get("content_preparation", {})
    if value is False:
        value = {"mode": "off"}
    if not isinstance(value, dict):
        raise ValueError("content_preparation 必须为对象或 false")
    mode = value.get("mode", "auto")
    if mode not in {"auto", "article", "off"}:
        raise ValueError("content_preparation.mode 必须是 auto/article/off")
    settings = {"mode": mode, "max_actions": value.get("max_actions", 6),
                "max_scrolls": value.get("max_scrolls", 4),
                "scroll_step_pixels": value.get("scroll_step_pixels", 240), "close_hints": []}
    for key in ["max_actions", "max_scrolls"]:
        if type(settings[key]) is not int or not 0 <= settings[key] <= 20:
            raise ValueError("content_preparation." + key + " 必须为0至20整数")
    if type(settings["scroll_step_pixels"]) is not int or not 1 <= settings["scroll_step_pixels"] <= 480:
        raise ValueError("content_preparation.scroll_step_pixels 必须是1至480整数")
    hints = value.get("close_hints", [])
    if not isinstance(hints, list) or len(hints) > 20:
        raise ValueError("content_preparation.close_hints 必须是至多20项数组")
    for hint in hints:
        if not isinstance(hint, dict) or not isinstance(hint.get("selector"), str) or not hint["selector"].strip():
            raise ValueError("关闭控件hint必须有明确selector")
        index = hint.get("index", 0)
        evidence = hint.get("evidence")
        if type(index) is not int or not 0 <= index <= 100:
            raise ValueError("关闭控件hint index必须是0至100整数")
        if not isinstance(evidence, dict) or not all(isinstance(evidence.get(k), str) and evidence[k].strip()
                                                    for k in ["path", "sha256", "description"]):
            raise ValueError("关闭控件hint必须绑定path、sha256和实际审阅说明")
        if not re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"]):
            raise ValueError("关闭控件hint必须有完整SHA256")
        path = Path(evidence["path"]).expanduser().resolve()
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
            raise ValueError("关闭控件hint证据缺失或SHA256已变化")
        settings["close_hints"].append({"selector": hint["selector"], "index": index,
                                       "evidence": {**evidence, "path": str(path)},
                                       "evidence_file_hash_verified": True})
    return settings


async def assess_content(page, task, operation=None, timeout=15):
    """Observe, never click, scroll, change DOM/CSS, or infer image-only controls."""
    settings = preparation_settings(task)
    operation = operation or {}
    if "preserve_reading_position" in operation and type(operation["preserve_reading_position"]) is not bool:
        raise ValueError("preserve_reading_position 必须为显式布尔值")
    try:
        result = await asyncio.wait_for(page.evaluate(CONTENT_JS, {
            "settings": settings,
            "instruction": task.get("instruction", ""),
            "operation": {key: operation[key] for key in ["action_type", "selector", "index", "preserve_reading_position"] if key in operation},
        }), timeout=timeout)
    except asyncio.TimeoutError as error:
        raise TimeoutError("正文与广告判断超过时限，停止准备并保留证据") from error
    result["algorithm_version"] = ALGORITHM_VERSION
    result["observer_sha256"] = OBSERVER_SHA256
    result["settings"] = settings
    return result
