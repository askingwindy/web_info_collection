"""Local installed Google Chrome / isolated profile UI verification. No live websites."""
import argparse,asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
async def main(path):
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True,args=['--allow-file-access-from-files'])
  page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));await page.goto(Path(path).resolve().as_uri());await page.wait_for_selector('article h2');await page.locator('main details').filter(has=page.locator('summary')).first.wait_for();count=await page.locator('nav button').count();images=await page.locator('img').evaluate_all('(imgs)=>imgs.every(i=>i.complete&&i.naturalWidth>0)');await page.locator('nav button').nth(count-1).click();await page.locator('nav button').first.click();await page.select_option('#kind','ai');await page.fill('#name','AUTOMATED UI TEST ONLY');await page.fill('#provenance','Offline UI plumbing test, not actual sample review; all outcomes remain pending')
  async with page.expect_download() as event:await page.get_by_role('button',name='导出质检审核记录').click()
  download=await event.value;temp=await download.path();data=json.loads(Path(temp).read_text());assert len(data['records'])==count;assert all(v['status']=='REVIEW_REQUIRED' for r in data['records'] for v in r['checks'].values());assert not errors;assert images
  print(json.dumps({'browser':'installed Google Chrome, isolated headless context on this computer','sample_buttons':count,'image_loads':images,'JS_errors':errors,'download':'verified pending records in temporary browser download only; not imported','human_review_created':False},ensure_ascii=False));await browser.close()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('html');args=ap.parse_args();asyncio.run(main(args.html))
