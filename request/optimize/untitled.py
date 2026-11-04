#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 0 复用率 PoC
==================
目的:在 100 页同站上,验证"模板化复用"到底帮不帮——产出两个数字:
  (1) 库最终沉淀出几个模板  (期望:个位数)
  (2) 复用率命中率           (期望:>80%)

这两个数字决定 20w 整个方案是否成立(详见《采集Agent方案描述.md》Phase 0)。

工作原理:
  对每个页面 -> 用 Playwright 渲染 -> 算 structure_fingerprint ->
  查模板库最相似 ->
    命中(>= Ts) -> 计为 REUSE(秒级,不规划)
    未命中      -> 计为 PLAN_NEW,沉淀为新模板(入库前 dedup)
  最后统计 reuse / new / templates_sedimented / reuse_rate。

两种运行模式:
  --simulate-only : 纯指纹模拟,不调你现有 ReAct,不真执行。
                     只算"复用率与模板数"——最快,Phase 0 主用这个。
  --full          : 接入你现有 ReAct 与执行器,沉淀真实可回放轨迹。
                     需要替换下方 existing_react_plan() / executor_replay()。

依赖:
  pip install playwright && playwright install chromium

运行示例:
  python phase0_reuse_poc.py --urls urls.txt --simulate-only
  python phase0_reuse_poc.py --urls urls.txt --sample 100 --ts 0.85
  python phase0_reuse_poc.py --urls urls.txt --full   # 接入后

urls.txt: 每行一个 URL(同站点,建议 100 个)。
"""

import argparse
import json
import sqlite3
import re
import sys
from collections import Counter
from itertools import combinations

# ─────────────────────────── CONFIG ────────────────────────────
Ts = 0.85      # 高阈值:命中即复用(Step 0 标定)
Ms = 0.92      # 沉淀 dedup 阈值:近邻模板不再新建,避免库膨胀
DEPTH_CAP = 6
TOP_K = 32     # skeleton 保留元素数
TIMEOUT_MS = 20000   # 单页加载超时

OPERABLE_JS = r"""
() => {
  const sel = 'button, a[href], input, select, textarea, [role="tab"], [aria-expanded], [role="button"]';
  const out = [];
  document.querySelectorAll(sel).forEach((el, i) => {
    const r = el.getBoundingClientRect();
    const visible = r.width > 2 && r.height > 2 &&
                    (el.checkVisibility ? el.checkVisibility() : true);
    let depth = 0, n = el.parentElement;
    while (n) { depth++; n = n.parentElement; }
    out.push({
      order: i, tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      role: el.getAttribute('role') || '',
      ariaExpanded: el.hasAttribute('aria-expanded'),
      href: el.getAttribute('href') || '',
      depth: Math.min(depth, 6),
      area: Math.round(r.width * r.height),
      visible,
      text: (el.innerText || el.value || '').trim().toLowerCase().slice(0, 40)
    });
  });
  return out;
}
"""

# actionClass 关键词映射(只把"类型标签"编进指纹,不编具体文本)
SUBMIT_HINTS = {"提交", "submit", "确认", "confirm", "登录", "login"}
EXPAND_HINTS = {"展开", "更多", "查看更多", "expand", "more"}
QUERY_HINTS = {"搜索", "search", "查询", "query", "筛选", "filter"}


def classify_role(el):
    t, typ = el["tag"], el["type"]
    if t == "button" or el["role"] == "button":
        return "submit" if typ == "submit" else "button"
    if t == "a" and el["href"]:
        return "nav-link"
    if t == "input":
        return "form-" + (typ or "text")
    if t == "select":
        return "form-select"
    if t == "textarea":
        return "form-textarea"
    if el["ariaExpanded"] or el["role"] == "tab":
        return "collapsible"
    return "other"


def infer_action_class(el):
    txt = el["text"]
    if any(k in txt for k in SUBMIT_HINTS):
        return "submit"
    if any(k in txt for k in EXPAND_HINTS):
        return "expand"
    if any(k in txt for k in QUERY_HINTS):
        return "query"
    if el["tag"] == "a":
        return "navigate"
    return "default"


def compute_fingerprint(elems):
    """elements -> Fingerprint(只描述操作面骨架,不描述内容)"""
    skeleton, hist = [], Counter()
    for el in elems:
        if not el["visible"]:
            continue
        role = classify_role(el)
        if role == "other":
            continue
        cell = {
            "role": role,
            "depth": min(el["depth"], DEPTH_CAP),
            "orderQ": el["order"] // 10,
            "actionClass": infer_action_class(el),
            "salience": el["area"],
        }
        skeleton.append(cell)
        hist[role] += 1
    # top-K by salience, 再按 order 回排
    skeleton.sort(key=lambda c: -c["salience"])
    skeleton = skeleton[:TOP_K]
    skeleton.sort(key=lambda c: c["orderQ"])
    role_seq = [f"{c['role']}:{c['actionClass']}" for c in skeleton]
    return {"skeleton": skeleton, "hist": dict(hist), "role_seq": role_seq}


# ─────────────────────────── 相似度 ────────────────────────────
def shingles(seq, n=2):
    if len(seq) < n:
        return set(seq)
    return set("|".join(seq[i:i + n]) for i in range(len(seq) - n + 1))


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def cosine_hist(h1, h2):
    keys = set(h1) | set(h2)
    if not keys:
        return 1.0
    dot = sum(h1.get(k, 0) * h2.get(k, 0) for k in keys)
    n1 = sum(v * v for v in h1.values()) ** 0.5
    n2 = sum(v * v for v in h2.values()) ** 0.5
    return dot / (n1 * n2) if n1 and n2 else 0.0


def similarity(fp1, fp2):
    s_seq = jaccard(shingles(fp1["role_seq"], 2), shingles(fp2["role_seq"], 2))
    s_hist = cosine_hist(fp1["hist"], fp2["hist"])
    return 0.6 * s_seq + 0.4 * s_hist


# ─────────────────────────── 模板库 ────────────────────────────
class TemplateStore:
    def __init__(self, path=":memory:"):
        self.con = sqlite3.connect(path)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS templates(
                id INTEGER PRIMARY KEY,
                fingerprint TEXT, hist TEXT, role_seq TEXT,
                trajectory TEXT, reuse_count INTEGER DEFAULT 0, success TEXT
            )
        """)
        self.con.commit()

    def best_match(self, fp):
        best_id, best_score = None, 0.0
        for rid, fp_json, seq_json in self.con.execute(
            "SELECT id, fingerprint, role_seq FROM templates"
        ):
            other = json.loads(fp_json)
            other["role_seq"] = json.loads(seq_json)
            s = similarity(fp, other)
            if s > best_score:
                best_id, best_score = rid, s
        return best_id, best_score

    def add(self, fp, trajectory):
        self.con.execute(
            "INSERT INTO templates(fingerprint,hist,role_seq,trajectory,reuse_count) "
            "VALUES(?,?,?,?,0)",
            (json.dumps(fp), json.dumps(fp["hist"]),
             json.dumps(fp["role_seq"]), json.dumps(trajectory)),
        )
        self.con.commit()
        cur = self.con.execute("SELECT last_insert_rowid()")
        return cur.fetchone()[0]

    def bump(self, rid):
        self.con.execute(
            "UPDATE templates SET reuse_count = reuse_count + 1 WHERE id=?",
            (rid,),
        )
        self.con.commit()

    def count(self):
        return self.con.execute("SELECT COUNT(*) FROM templates").fetchone()[0]


# ─────────────────────────── 接入点 ────────────────────────────
# TODO[接入你的 ReAct]: 把现有 ReAct 的输出转成下面 Trajectory JSON 格式
def existing_react_plan(page, fp):
    """返回可回放轨迹 JSON。simulate-only 模式下不会被调用。
    期望格式(与《采集Agent系统优化方案.md》§8 Step 契约一致):
    [{"action":"goto","url":page.url},
     {"action":"scroll_loop","until":"networkIdleAndStable"},
     {"action":"expand_all"},
     {"action":"screenshot","mode":"fullPage"},
     {"action":"extract","fields":["title","body_md"]}]
    """
    raise NotImplementedError(
        "接入现有 ReAct:把其输出转成上面 Trajectory JSON 格式即可")


# TODO[接入你的执行器]: 真正回放并截图。simulate-only 模式下不会被调用。
def executor_replay(trajectory, page):
    """回放轨迹并返回是否成功。PoC 仅需 bool,真实实现见技术文档 §8.4-8.6。"""
    raise NotImplementedError("接入执行器:回放 + 截图 + 断言")


# ─────────────────────────── 主流程 ────────────────────────────
def run(urls, mode, sample, ts):
    from playwright.sync_api import sync_playwright

    store = TemplateStore()
    metrics = Counter()
    per_page = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        for i, url in enumerate(urls[:sample] if sample else urls, 1):
            page = ctx.new_page()
            try:
                page.goto(url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                elems = page.evaluate(OPERABLE_JS)
            except Exception as e:
                metrics["skip_load_fail"] += 1
                print(f"[{i:3d}] LOAD_FAIL {url[:60]} :: {str(e)[:60]}", file=sys.stderr)
                page.close()
                continue
            fp = compute_fingerprint(elems)
            page.close()

            rid, score = store.best_match(fp)
            if rid is not None and score >= ts:
                # ── REUSE:绕开 LLM ──
                metrics["reuse"] += 1
                store.bump(rid)
                per_page.append((url, "REUSE", round(score, 3)))
                print(f"[{i:3d}] REUSE  score={score:.3f} (tmpl #{rid})")
            else:
                # ── PLAN_NEW:沉淀 ──
                metrics["plan_new"] += 1
                if mode == "full":
                    traj = existing_react_plan(_PageStub(url), fp)
                    ok = executor_replay(traj, _PageStub(url))
                    if not ok:
                        metrics["plan_exec_fail"] += 1
                        per_page.append((url, "EXEC_FAIL", round(score, 3)))
                        continue
                else:
                    traj = [{"action": "stub_plan", "url": url}]
                # detup:近邻不重复建
                if rid is not None and score >= Ms:
                    metrics["dedup_into"] += 1
                    per_page.append((url, "DEDUP", round(score, 3)))
                    print(f"[{i:3d}] PLAN   (dedup into tmpl #{rid}, score={score:.3f})")
                else:
                    new_id = store.add(fp, traj)
                    per_page.append((url, "PLAN_NEW", round(score, 3)))
                    print(f"[{i:3d}] PLAN   new tmpl #{new_id} (best={score:.3f})")
        browser.close()

    return metrics, store, per_page


class _PageStub:
    def __init__(self, url):
        self.url = url


# ─────────────────────────── 报告 ────────────────────────────
def report(metrics, store, per_page):
    total = metrics["reuse"] + metrics["plan_new"]
    reuse_rate = (metrics["reuse"] / total) if total else 0.0
    print("\n" + "=" * 50)
    print("Phase 0 复用率 PoC 报告")
    print("=" * 50)
    print(f"处理页面总数      : {total}")
    print(f"  REUSE(命中复用) : {metrics['reuse']}")
    print(f"  PLAN_NEW(新规划): {metrics['plan_new']}")
    if metrics["dedup_into"]:
        print(f"    其中 dedup并入  : {metrics['dedup_into']}")
    if metrics["plan_exec_fail"]:
        print(f"    其中 执行失败   : {metrics['plan_exec_fail']}")
    print(f"加载失败跳过       : {metrics['skip_load_fail']}")
    print("-" * 50)
    # === 这就是 Phase 0 的两个关键数字 ===
    print(f"  模板沉淀数       : {store.count()}  (期望个位数)")
    print(f"  复用率命中率     : {reuse_rate:.1%}  (期望 >80%)")
    print("=" * 50)
    print("\n判定:")
    if reuse_rate >= 0.8:
        print("  ✅ 复用率高,推进 Phase 1 最小消费者内核。")
    elif reuse_rate >= 0.5:
        print("  ⚠️  中段,先调 fingerprint 粒度(过细/过粗)再测。")
    else:
        print("  ❌ 偏低,评估分层规划等更重设计。")
    # 沉淀模板的复用分布(看是否真的少数模板吃下多数页)
    rows = store.con.execute(
        "SELECT id, reuse_count FROM templates ORDER BY reuse_count DESC"
    ).fetchall()
    if rows:
        print("\nper-template 复用次数(top10):")
        for tid, c in rows[:10]:
            print(f"  tmpl #{tid}: reused {c} times")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True, help="URL 列表文件,每行一个")
    ap.add_argument("--sample", type=int, default=0, help="只取前 N 个(0=全部)")
    ap.add_argument("--ts", type=float, default=Ts, help="复用阈值(默认 0.85)")
    ap.add_argument("--mode", choices=["simulate-only", "full"],
                    default="simulate-only")
    args = ap.parse_args()
    with open(args.urls) as f:
        urls = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    metrics, store, per_page = run(
        urls, args.mode, args.sample, args.ts
    )
    report(metrics, store, per_page)


if __name__ == "__main__":
    main()
