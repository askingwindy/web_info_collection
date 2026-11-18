import argparse
from collections import Counter
from datetime import datetime
import json
import os
import subprocess
import time

from progress import ARCHIVE, RUN, SCOPE, history, read, records, snapshot, write
from select_pages import ROOT


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('segment', type=int)
    parser.add_argument('--push', action='store_true')
    args = parser.parse_args()
    stamp = f'run-{args.segment:02d}'
    directory = RUN / stamp
    start = read(directory / 'controller-start.json')
    native = directory / 'summary.json'
    while True:
        try:
            if native.is_file() and 'report_integrity' in read(native):
                break
        except json.JSONDecodeError:
            pass
        try:
            os.kill(start['pid'], 0)
        except ProcessLookupError:
            break
        time.sleep(20)
    scope, baseline = read(SCOPE), read(RUN / 'before.json')
    selection = read(ARCHIVE / 'selection.json')['pages']
    sites = {row['candidate_id']: row['host'].removeprefix('www.') for row in selection}
    status, issues = snapshot(directory, scope, baseline, sites)
    if status['state'] != 'FINISHED':
        status['state'] = 'CONTROLLER_EXIT_WITHOUT_FINAL_REPORT'
    if (directory / 'funnel.json').is_file():
        funnel = read(directory / 'funnel.json')
        status['native_report'] = {key: funnel[key] for key in ('expected_denominator', 'denominator', 'integrity', 'issues', 'saved')}
        status['native_report']['stages'] = {stage: values['independent'] for stage, values in funnel['funnel'].items()}
        status['native_report']['consumer_usage'] = funnel['usage']['consumer']
    paths = [ARCHIVE / f'{stamp}-{suffix}' for suffix in ('final.json', 'final-issues.json', 'ledger-check.json', 'timeline.json', 'final.md')]
    write(paths[0], status)
    write(paths[1], issues)
    audit = history(scope, baseline)
    write(paths[2], audit)
    timeline = [{'at': item['at'], 'state': item['state'], 'claimed': item['unique_claims'], 'formal_attempts': item['formal_attempts'],
                 'saved_pending_review': item['saved_pending_review'], 'issues': item['issues_recorded'],
                 'model_states': item['consumer_model']['states']} for item in records(RUN / f'{stamp}-progress.jsonl')]
    timeline.append({'at': status['at'], 'state': status['state'], 'claimed': status['unique_claims'], 'formal_attempts': status['formal_attempts'],
                     'saved_pending_review': status['saved_pending_review'], 'issues': len(issues), 'model_states': status['consumer_model']['states']})
    write(paths[3], timeline)
    usage = status['consumer_model']
    text = [f'# 三站策略3采集：{stamp} 收口', '', f"核账时间：{status['at']}；批次状态 `{status.get('collection_outcome',status['state'])}`；原生报告完整性 `{status.get('native_report',{}).get('integrity','UNKNOWN')}`。",
        '', '| 站点 | 固定页 | 已领 | 正式尝试 | 正式保存待审 |', '|---|---:|---:|---:|---:|']
    for site, counts in status['by_site'].items():
        text.append(f"| {site} | 50 | {counts['claimed']} | {sum(counts['attempt_states'].values())} | {counts['saved_pending_review']} |")
    text += ['', f"同时运行峰值 {status['worker_peak_observed']}；共领取 {status['unique_claims']}/150，未领 {status['unclaimed']}，正式保存待审 {status['saved_pending_review']}。",
        f"消费者请求状态：`{dict(usage['states'])}`；已证 HTTP {usage['dispatch'].get('dispatched',0)}，未证 {usage['dispatch'].get('unproven',0)}。已知输入/输出 token：{usage['known_input_tokens']}/{usage['known_output_tokens']}，缺 usage {usage['unknown_usage_requests']} 笔，费用 UNKNOWN。",
        f"调度问题记录 {len(issues)} 条，分类 `{dict(Counter(event['disposition'] for event in issues))}`。原生报告与独立账表都保留；缺原件或缺归因不作为通过。",
        f"历史保护字段有差异的行数：`{ {role:len(item['different_or_missing_ids']) for role,item in audit.items()} }`；原未决消费者/生产者作业上新增请求数：{audit['consumer_db']['new_request_rows_on_prior_unsettled_jobs']}/{audit['producer_db']['new_request_rows_on_prior_unsettled_jobs']}。",
        '', '本批未启动自动导出、QC 或人审；数据集未发布，客户验收 UNKNOWN。']
    paths[4].write_text('\n'.join(text) + '\n')
    canonical = [ARCHIVE / f'{stamp}-status.json', ARCHIVE / f'{stamp}-issues.json']
    write(canonical[0], status)
    write(canonical[1], issues)
    if not args.push:
        return
    if git('branch', '--show-current') != 'main':
        raise RuntimeError('Reports saved locally: checkout is no longer main')
    upstream = git('ls-remote', '--exit-code', '--heads', 'origin', 'main').split()[0]
    if git('rev-parse', 'HEAD') != upstream:
        raise RuntimeError('Reports saved locally: local and remote main differ; refusing to include unrelated commits')
    relative = [str(path.relative_to(ROOT)) for path in paths + canonical]
    git('add', '--', *relative)
    git('diff', '--cached', '--check', '--', *relative)
    git('commit', '--only', '-m', f'Archive final stepwise three-site collection evidence ({stamp})', '--', *relative)
    commit = git('rev-parse', 'HEAD')
    git('push', 'origin', commit + ':refs/heads/main')
    remote = git('ls-remote', '--exit-code', '--heads', 'origin', 'main').split()[0]
    if remote != commit:
        raise RuntimeError('Push returned, but remote HEAD no longer matches; check ancestry')
    write(directory / 'git-publication.json', {'at': datetime.now().astimezone().isoformat(), 'ref': 'refs/heads/main', 'commit': commit, 'remote_verified': True})


if __name__ == '__main__':
    main()
