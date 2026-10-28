"""Real Chrome UI plumbing test on synthetic local evidence only."""
import argparse
import asyncio
import functools
import hashlib
import json
from pathlib import Path
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parents[1]))
from make_fixture import fixture
from quality_inspector.blind import write_workspace
from quality_inspector.contract import fingerprint
from quality_inspector.reviews import intake


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


async def run(output):
    output.mkdir(parents=True, exist_ok=False)
    dataset = output / 'synthetic-source'
    sample = fixture(dataset)
    evidence = {p.relative_to(sample).as_posix(): digest(p)
                for folder in ['images', 'ui_tree'] for p in (sample / folder).iterdir()}
    _, contract_sha = fingerprint()
    report = {'scope': 'delivery', 'dataset': str(dataset),
              'baseline': {'config_sha256': contract_sha},
              'review_import': {'secret': 'AI_OLD_JUDGMENT_SENTINEL'},
              'samples': [{'sample_id': sample.name, 'sample_path': str(sample),
                           'annotation_sha256': digest(sample / 'annotation.json'),
                           'evidence_sha256': evidence,
                           'checks': [{'status': 'FAIL', 'reason': 'QC_OUTCOME_SENTINEL'}]}]}
    report_path = output / 'synthetic-report.json'; report_path.write_text(json.dumps(report))
    context = output / 'neutral-context.json'
    context.write_text(json.dumps({'source_statement': '这是离线合成测试夹具，不是真实网站或生产数据。',
                                   'input_statement': '输入文字“测试”，无真实账号或个人资料。'}, ensure_ascii=False))
    workspace = output / 'workspace'
    receipt = write_workspace(report_path, workspace, context_path=context,
                              receipt_path=output / 'workspace-receipt.json',
                              reviewer_name='AUTOMATED UI TEST ONLY')
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(workspace))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}/review.html'
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1050})
            errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
            old_key = 'webcollect-human-review:' + receipt['data_id']
            await page.add_init_script('localStorage.setItem(' + json.dumps(old_key) + ', JSON.stringify({previous:"OLD_DRAFT_SENTINEL"}));')
            await page.goto(url)
            await page.locator('#closeHelp').click()
            await page.wait_for_function('imageStatus.before && imageStatus.after')
            assert await page.locator('#doneCount').inner_text() == '0'
            assert await page.locator('#packageButton').is_hidden()
            assert 'OLD_DRAFT_SENTINEL' not in await page.locator('body').inner_text()
            assert 'AI_OLD_JUDGMENT_SENTINEL' not in await page.content()
            assert 'QC_OUTCOME_SENTINEL' not in await page.content()
            assert await page.evaluate('Object.keys(state.samples[sampleData[0].sample_id].steps).length') == 0
            await page.screenshot(path=str(output / 'initial-workspace.png'), full_page=True)
            for choice in ['#stepIssue', '#stepUnclear']:
                await page.locator(choice).click()
                assert await page.locator('#stepNote').input_value() == ''
                await page.locator('#saveStepNote').click()
                assert await page.evaluate('step') == 0
                assert '请写' in await page.locator('#toast').inner_text()
            for i in range(6):
                await page.wait_for_function('imageStatus.before && imageStatus.after')
                await page.locator('#stepOK').click()
                assert await page.evaluate(f'entry().steps[{i + 1}].decision') == 'ok'
                assert await page.evaluate(f'entry().steps[{i + 1}].note') == ''
                if i < 5:
                    assert await page.evaluate('step') == i + 1
                if i == 2:
                    await page.reload()
                    await page.wait_for_function('imageStatus.before && imageStatus.after')
                    assert await page.evaluate('step') == 3
                    assert await page.evaluate('Object.keys(entry().steps).length') == 3
                    assert await page.evaluate('Object.values(entry().steps).every(v => v.decision === "ok" && v.note === "")')
            assert await page.evaluate('phase') == 'questions'
            assert '程序检查详情' not in await page.locator('#workspace').inner_text()
            for name in ['visual_alignment', 'terminal_semantics', 'language', 'privacy', 'substantive_difference']:
                await page.locator(f'[data-rule="{name}"][data-answer="PASS"]').click()
                assert await page.locator(f'[data-note="{name}"]').input_value() == ''
                await page.locator(f'[data-note="{name}"]').fill('合成测试明确输入的判断，用于验证导出接口；不是实际人审、不是样本通过。')
            await page.locator('#finishSample').click()
            assert '保存你的首轮判断' in await page.locator('#workspace').inner_text()
            async with page.expect_download() as event:
                await page.locator('#exportAtEnd').click()
            download = await event.value
            exported = output / 'SYNTHETIC_UI_TEST_EXPORT_NOT_HUMAN_REVIEW.json'
            await download.save_as(exported)
            value = json.loads(exported.read_text())
            assert value['ui_review']['review_mode'] == 'blind'
            assert 'delivery_document_review' not in value
            assert value['records'][0]['annotation_sha256'] == digest(sample / 'annotation.json')
            assert value['records'][0]['provenance']['frames_viewed'] == [1, 2, 3, 4, 5, 6]
            assert [(s['step_id'], s['decision'], s['note']) for s in value['records'][0]['step_observations']] == [
                (i, 'ok', '') for i in range(1, 7)]
            records, invalid, migrations = intake(exported, report['samples'], contract_sha)
            assert len(records) == 1 and not invalid and not migrations
            await page.locator('#importFile').set_input_files(str(exported))
            assert '备份已恢复' in await page.locator('#toast').inner_text()
            old = json.loads(exported.read_text()); old['ui_review']['review_mode'] = 'standard'
            old_path = output / 'SYNTHETIC_OLD_MODE_IMPORT_REJECTED.json'; old_path.write_text(json.dumps(old))
            await page.locator('#importFile').set_input_files(str(old_path))
            assert '首轮盲审只能恢复' in await page.locator('#toast').inner_text()
            assert not errors
            await browser.close()
        result = {'status': 'PASS', 'data_type': 'SYNTHETIC_UI_TEST_ONLY',
                  'browser': 'installed Chrome; isolated headless context; local HTTP only',
                  'baseline_sha256': contract_sha,
                  'frames': 6, 'page_errors': errors, 'old_standard_draft_ignored': True,
                  'AI_and_QC_sentinels_absent': True,
                  'normal_explicit_acknowledgment_accepts_empty_note': True,
                  'issue_and_unclear_still_require_note': True,
                  'normal_notes_not_fabricated': True, 'empty_note_progress_survives_reload': True,
                  'v2_export_original_hashes_preserved': True, 'v2_intake_valid': True,
                  'own_blind_backup_restores': True, 'standard_backup_rejected': True,
                  'actual_human_reviews_created': 0, 'production_data_used': False}
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=Path, required=True)
    asyncio.run(run(ap.parse_args().output.resolve()))
