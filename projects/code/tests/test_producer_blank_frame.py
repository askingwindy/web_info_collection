"""Blank original frames cannot become candidates through later DOM content."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from PIL import Image
import test_producer_v10 as fixture
from site_planner import producer_observation
from site_planner.candidate_discovery import _publish_entry
from site_planner.discovery_tools import reference
from site_planner.page_consumption import blank_frame_exclusion, required_login_exclusion, VISIBLE_FRAME_VERSION
from webcollect.batch_core import file_sha, load_json, save_json


class BlankFrameIntegration(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ProducerV10('test_same_observation_supplies_dom_and_publication_without_get')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_cached_blank_is_rejected_before_model_and_new_publication_but_old_row_survives(self):
        f = self.f
        link = f.link()
        original = f.observation(link['uri'], '')
        hashes = {key: file_sha(original[key]['path']) for key in ('observation', 'image', 'document')}
        with patch('site_planner.producer_observation.DiscoveryBrowser.__aenter__', side_effect=AssertionError('no retry')):
            admitted, records = producer_observation.screen(f.pool, f.ledger, [link], f.root)
        self.assertEqual(admitted, [])
        self.assertEqual(records[0]['decision']['policy'], VISIBLE_FRAME_VERSION)
        self.assertEqual(records[0]['decision']['reason'], 'blank_first_frame')
        header = {'row_id': 'blank-new', 'run_id': 'blank-fixture', 'batch': 0,
                  'request_id': 'original', 'response_sha256': 'original-response', 'raw_index': 0}
        candidate, source = f.f.entry(link['uri']), f.f.source
        rejected = _publish_entry(f.pool, f.ledger, 'blank-fixture', f.root, header, candidate, source, {})
        self.assertEqual((rejected['result'], rejected['reason']), ('REJECTED', 'blank_first_frame'))
        old_header = {**header, 'row_id': 'old-blank'}
        historical = f.pool.publish_row(old_header, candidate, source)
        before = deepcopy(f.pool.rows(protocols=('webcollect-data-candidate-2',)))
        self.assertEqual(_publish_entry(f.pool, f.ledger, 'blank-fixture', f.root, old_header, candidate, source, {}), historical)
        self.assertEqual(f.pool.rows(protocols=('webcollect-data-candidate-2',)), before)
        self.assertEqual({key: file_sha(original[key]['path']) for key in hashes}, hashes)
        with f.ledger.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM model_requests').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM top_level_visits').fetchone()[0], 1)

    def test_empty_text_alone_does_not_reject_graphics_or_visible_controls(self):
        f = self.f
        original = f.observation(f.link()['uri'], '')
        image = Image.new('RGB', (100, 100), 'white')
        image.putpixel((50, 50), (0, 0, 0))
        path = f.root / 'graphic.png'; image.save(path)
        self.assertIsNone(blank_frame_exclusion({**original, 'image': reference(path)}))
        observation = load_json(original['observation']['path'])
        for key, value in (('text', '中文功能'), ('controls', [{'role': 'button'}]), ('links', [{'uri': '/next'}])):
            path = f.root / (key + '.json')
            save_json(path, {**observation, key: value})
            self.assertIsNone(blank_frame_exclusion({**original, 'observation': reference(path)}))

    def test_explicit_mandatory_notice_blocks_screen_and_publish_but_normal_login_link_does_not(self):
        f=self.f;link=f.link();original=f.observation(link['uri'], '公开工具正文')
        observation=load_json(original['observation']['path'])
        path=f.root/'login-notice.json'
        save_json(path,{**observation,'text':'登录即可免费使用\n受服务器资源影响，请先登录后再使用\n公开工具正文',
                        'controls':[{'label':'立即登录','disabled':False}]})
        result={**original,'observation':reference(path)}
        self.assertEqual(required_login_exclusion(result)['reason'],'explicit_login_required_to_use')
        normal=f.root/'optional-login.json'
        save_json(normal,{**observation,'text':'公开工具正文\n登录',
                          'controls':[{'label':'立即登录','disabled':False}]})
        self.assertIsNone(required_login_exclusion({**original,'observation':reference(normal)}))
        from site_planner import page_consumption
        with patch.object(page_consumption,'register',return_value={'status':'UNKNOWN'}), \
             patch.object(f.pool.pool,'connect',wraps=f.pool.pool.connect):
            # Exercise the normal screening path with the controlled new probe.
            fresh={**link,'uri':'https://tools.example.org/new-login'}
            admitted,records=page_consumption.screen(f.pool,f.ledger,[fresh],f.root,probe=lambda *args:result)
        self.assertEqual(admitted,[])
        self.assertEqual(records[0]['decision']['reason'],'explicit_login_required_to_use')
        header={'row_id':'login-new','run_id':'login-fixture','batch':0,'request_id':'original',
                'response_sha256':'original-login','raw_index':0}
        with patch('site_planner.producer_observation.from_pool',return_value=({},result)):
            rejected=_publish_entry(f.pool,f.ledger,'login-fixture',f.root,header,f.f.entry(link['uri']),f.f.source,{})
        self.assertEqual((rejected['result'],rejected['reason']),('REJECTED','explicit_login_required_to_use'))
