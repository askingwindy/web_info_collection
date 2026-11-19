"""离线重放上一轮故宫公告 HTML 和真实往返记录。样式文件由 --assets 指定。"""
import argparse
import asyncio
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

from playwright.async_api import async_playwright
from webcollect import browser
from webcollect.stepwise.session import StepwiseSession

ROOT = Path(__file__).resolve().parents[2]
WORDS = ('开放公告', '关于延禧宫停止开放的公告', '雕版馆临时闭馆公告')


async def replay(assets):
    old_scope = json.loads((ROOT / 'database/sqllite/prod/scope.json').read_text())
    documents = Path(old_scope['pool']).parent / 'producer-evidence'
    html = next(documents.glob('7459*/page-29a4ad4*/rendered-dom.html')).read_text()
    old_js = subprocess.check_output(['git', 'show', '1f4406f:projects/code/webcollect/snapshot.js'],
                                     cwd=ROOT, text=True)
    async with async_playwright() as pw:
        chrome = await pw.chromium.launch(channel='chrome')
        context = await chrome.new_context(viewport={'width': 1280, 'height': 720}, service_workers='block')

        async def route(request):
            if request.request.url == 'https://archive.test/':
                content = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', '', html, flags=re.I)
                return await request.fulfill(content_type='text/html', body=content)
            name = request.request.url.split('?')[0].rsplit('/', 1)[-1]
            if name in ('vendor.css', 'main.css'):
                return await request.fulfill(content_type='text/css', body=(assets / name).read_bytes())
            await request.abort()

        await context.route('**/*', route)
        page = await context.new_page()
        await page.goto('https://archive.test/')
        original = await page.evaluate(old_js, {})
        fixed = await browser.observe(page)
        before = [word in original['visible_text'] for word in WORDS]
        after = [word in fixed['visible_text'] for word in WORDS]
        assert before == [False] * 3 and after == [True] * 3
        assert any(WORDS[1] in (e.get('visible_text') or '') for e in fixed['elements'] if e.get('clickable'))
        await page.add_style_tag(content='.educate1 .list .p::before {left:0!important;top:0!important;'
                                 'width:100%!important;height:100%!important;background:black!important;z-index:9}')
        covered = await browser.observe(page)
        assert WORDS[1] not in covered['visible_text'] and WORDS[2] not in covered['visible_text']
        await chrome.close()

    sample = next(Path(old_scope['output']).glob('20261119221112-91c40522/*/*/execution/capture/evidence/S000265_sample_000060/stepwise'))
    frames = {}
    rows = []
    for path in sorted(sample.glob('observation-???.json')):
        frames['f' + path.stem[-3:]] = {'state': json.loads(path.read_text())}
    for n in range(1, 7):
        dispatch = json.loads((sample / f'dispatch-{n:03d}.json').read_text())
        step = json.loads((sample.parent / f'step_{n:03d}.json').read_text())
        rows.append({'frame_id': dispatch['before_frame'], 'after_frame': step['after_frame'],
                     'element': dispatch['element'], 'operation': dispatch['operation'], 'effective': step['effective']})
    session = StepwiseSession.__new__(StepwiseSession)
    session.journal = SimpleNamespace(frames=frames)
    session.mode = 'autonomous'
    session.dispatch_rows = rows[:4]
    action = rows[4]
    issue = session._proposed_action_issue(frames[action['frame_id']], action['operation'], action['element'])
    assert issue.startswith('REPEATED_DETAIL_ROUNDTRIP')
    assert session._returned_click(rows[:2], frames[rows[2]['frame_id']])
    assert session._returned_click([rows[0], rows[2]], frames[rows[2]['frame_id']]) is None
    return {'original_missing': list(WORDS), 'fixed_recovered': list(WORDS),
            'covered_titles_excluded': True, 'visible_title_on_clickable_link': True,
            'real_roundtrip_advice_after_first_return': True, 'third_identical_open_rejected': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(replay(args.assets)), ensure_ascii=False, indent=2))
