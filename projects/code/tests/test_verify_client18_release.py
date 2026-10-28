"""Synthetic preservation probes; these fixtures are never dataset acceptance."""
import csv
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import tempfile
import unittest
import zipfile
import zlib


SCRIPT = Path(__file__).parents[1] / 'scripts/verify_client18_release.py'
spec = importlib.util.spec_from_file_location('release_verifier', SCRIPT)
verifier = importlib.util.module_from_spec(spec); spec.loader.exec_module(verifier)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(root):
    # Fixture authoring deliberately does not call the verifier's manifest code.
    rows = [(p.relative_to(root).as_posix(), sha(p)) for p in sorted(root.rglob('*'))
            if p.is_file() and p != root / 'SHA256SUMS']
    (root / 'SHA256SUMS').write_text(''.join(value + '  ' + name + '\n' for name, value in rows))


def png(red):
    def chunk(kind, value):return struct.pack('!I', len(value)) + kind + value + struct.pack('!I', zlib.crc32(kind + value))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes([0, red, 17, 31]))) + chunk(b'IEND', b'')


class ReleaseVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.baseline = self.root / 'baseline'; self.package = self.root / 'release'; self.qc = self.root / 'qc.json'; self.archive = self.root / 'release.zip'
        original = self.baseline / 'client-original'; rows = []; ids = []
        for number in range(1, 19):
            sid = f'S{number:06}_sample_000001'; ids.append(sid); sample = original / 'samples' / sid
            steps = []
            for step in range(1, (7 if number <= 16 else 6) + 1):
                image = sample / 'images' / f'step_{step:03}.png'; image.parent.mkdir(parents=True, exist_ok=True); image.write_bytes(png(number * 8 + step))
                tree_path = f'ui_tree/step_{step:03}.json'; image_path = f'images/step_{step:03}.png'
                put(sample / tree_path, {'image_path': image_path, 'screen_resolution': [1, 1], 'elements': []})
                steps.append({'step_id': step, 'image_path': image_path, 'ui_tree_path': tree_path,
                    'action': {'action_type': 'click', 'coordinate': [0, 0], 'target_element_id': 'fixture', 'precondition': '合成测试', 'expected_result': '测试'},
                    'tool_call': {'tool_name': 'click', 'arguments': {'x': 0, 'y': 0}, 'call_id': sid + str(step), 'timestamp': '', 'context': '合成测试'}})
            data = {'sample_id': sid, 'steps': steps, 'task_instruction': '独立保全测试，不能交付。', 'task_type': ['数据查看'],
                    'completion_status': 'success', 'app_info': {'app_name': '离线测试'}, 'device_info': {'screen_resolution': [1, 1]}}
            put(sample / 'annotation.json', data); put(original / 'ground_truth' / (sid + '.json'), [])
            rows.append({'sample_id': sid, 'site_id': f'S{number:06}', 'site_category': '独立测试', 'app_name': data['app_info']['app_name'],
                'task_type': json.dumps(data['task_type']), 'task_instruction': data['task_instruction'], 'steps': str(len(steps)), 'screen_resolution': '[1, 1]',
                'completion_status': 'success', 'actions': json.dumps(['click'] * len(steps)), 'bytes': str(sum(p.stat().st_size for p in sample.rglob('*') if p.is_file()))})
        with (original / 'metadata.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=verifier.METADATA_COLUMNS); writer.writeheader(); writer.writerows(rows)
        put(original / 'site-list.json', {'sites': [{'site_id': row['site_id'], 'site_category': row['site_category']} for row in rows],
                                        'samples': [{'sample_id': row['sample_id'], 'site_id': row['site_id']} for row in rows]})
        (original / 'qc_report.md').write_text('合成发布验证夹具，不是数据集质检结论。\n'); seal(original)
        shutil.copytree(original, self.package)
        put(self.baseline / 'freeze-receipt.json', {'selected_sample_ids': ids, 'frames': 124})
        state = self.baseline / 'state'; state.mkdir()
        self.database(state / 'production-registry.sqlite3', real=True)
        self.database(state / 'synthetic-registry.sqlite3', real=False)
        put(state / 'registry-coverage.json', {'primary_row_counts': {'sites': 19, 'batches': 34, 'allocations': 203},
            'coverage': [{'site_identity_and_counter_coverage': True, 'missing_rows': {'batches': [], 'allocations': []}}]})
        seal(self.baseline); self.bind_qc_and_archive()

    def tearDown(self):self.temp.cleanup()

    def database(self, path, real):
        with closing(sqlite3.connect(path)) as con, con:
            con.executescript('CREATE TABLE sites(id INTEGER PRIMARY KEY,uri TEXT,category TEXT,kind TEXT,next_sample INTEGER); CREATE TABLE batches(id TEXT PRIMARY KEY,kind TEXT); CREATE TABLE allocations(sample_id TEXT PRIMARY KEY,site_id TEXT,batch_id TEXT);')
            if real:
                con.executemany('INSERT INTO sites VALUES(?,?,?,?,?)', [(n, 'https://fixture.invalid/' + str(n), '测试', 'real', 187 if n == 1 else 2) for n in range(1, 20)])
                con.executemany('INSERT INTO batches VALUES(?,?)', [(f'B{n:03}', 'real') for n in range(1, 35)])
                records = [(f'S{n:06}_sample_000001', f'S{n:06}', 'B001') for n in range(1, 19)]
                records += [(f'S000001_sample_{n:06}', 'S000001', 'B001') for n in range(2, 187)]
                con.executemany('INSERT INTO allocations VALUES(?,?,?)', records)
            else:
                con.execute('INSERT INTO sites VALUES(1,?,?,?,2)', ('https://synthetic.invalid', '测试', 'integration'))
                con.execute('INSERT INTO batches VALUES(?,?)', ('T001', 'integration'))
                con.execute('INSERT INTO allocations VALUES(?,?,?)', ('S000001_sample_000001', 'S000001', 'T001'))

    def bind_qc_and_archive(self):
        actual = {p.relative_to(self.package).as_posix(): sha(p) for p in self.package.rglob('*') if p.is_file()}
        samples = []
        for sample in sorted((self.package / 'samples').iterdir()):
            samples.append({'sample_id': sample.name, 'sample_path': str(sample.resolve()), 'annotation_sha256': sha(sample / 'annotation.json'),
                'evidence_sha256': {p.relative_to(sample).as_posix(): sha(p) for p in sample.rglob('*') if p.is_file() and p.name != 'annotation.json'}})
        put(self.qc, {'program': 'quality-inspector', 'scope': 'delivery', 'inspection_stage': 'final', 'release_ready': True,
            'status': 'PASS', 'delivery_status': 'PASS', 'contract_status': 'PASS', 'local_acceptance_status': 'PASS', 'dataset': str(self.package.resolve()),
            'input_files_sha256': actual, 'input_integrity': {'status': 'PASS'}, 'root_checksum': {'pass': True}, 'sample_count': 18,
            'local_sample_status_counts': {'PASS': 18}, 'samples': samples, 'test_only': 'Synthetic report binding fixture, never actual QC or human acceptance.'})
        with zipfile.ZipFile(self.archive, 'w') as zipped:
            for relative in sorted(actual):zipped.write(self.package / relative, self.package.name + '/' + relative)

    def report(self):return verifier.verify_release(self.baseline, self.package, self.qc, self.archive)

    def test_complete_preservation_and_receipt_pass_without_old_directories(self):
        result = self.report(); self.assertEqual(result['status'], 'PASS', result['errors'])
        self.assertEqual(result['statistics']['preserved_samples']['png'], 124)
        self.assertEqual(result['statistics']['production_registry']['allocations'], 203)
        self.assertEqual(result['archive_sha256'], sha(self.archive)); self.assertEqual(result['qc_report_sha256'], sha(self.qc))
        self.assertEqual(verifier.main(['--baseline', str(self.baseline), '--package', str(self.package), '--qc-report', str(self.qc),
            '--archive', str(self.archive), '--output', str(self.root / 'receipt.json')]), 0)

    def test_resealed_asset_change_fails_even_if_qc_and_zip_bindings_are_updated(self):
        image = next(self.package.glob('samples/*/images/step_001.png')); image.write_bytes(png(250)); seal(self.package); self.bind_qc_and_archive()
        result = self.report(); self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['checks']['preserved_samples']['status'], 'FAIL')

    def test_action_and_tool_type_changes_cannot_hide_as_prose_edits(self):
        path = next(self.package.glob('samples/*/annotation.json')); original = path.read_text(); data = json.loads(original)
        data['steps'][0]['action']['coordinate'][0] = False; put(path, data); seal(self.package); self.bind_qc_and_archive()
        self.assertEqual(self.report()['checks']['preserved_samples']['status'], 'FAIL')
        path.write_text(original); data = json.loads(original); data['steps'][0]['tool_call']['arguments']['x'] = False
        put(path, data); seal(self.package); self.bind_qc_and_archive()
        self.assertEqual(self.report()['checks']['preserved_samples']['status'], 'FAIL')

    def test_false_or_wrong_directory_qc_report_is_rejected(self):
        value = json.loads(self.qc.read_text()); value['release_ready'] = False; put(self.qc, value)
        self.assertEqual(self.report()['checks']['final_qc_binding']['status'], 'FAIL')
        value['release_ready'] = True; value['dataset'] = str(self.baseline); put(self.qc, value)
        self.assertEqual(self.report()['checks']['final_qc_binding']['status'], 'FAIL')

    def test_archive_traversal_extra_root_and_duplicate_member_are_rejected(self):
        for name in ('../escape.txt', 'another-root/file.txt', self.package.name + '/qc_report.md'):
            with self.subTest(member=name):
                self.bind_qc_and_archive()
                with zipfile.ZipFile(self.archive, 'a') as zipped:zipped.writestr(name, b'not part of release')
                self.assertEqual(self.report()['checks']['archive']['status'], 'FAIL')

    def test_baseline_seal_and_complete_ledger_are_required(self):
        path = self.baseline / 'state/registry-coverage.json'; path.write_text(path.read_text() + ' ')
        self.assertEqual(self.report()['checks']['baseline_manifest']['status'], 'FAIL')
        seal(self.baseline)
        with closing(sqlite3.connect(self.baseline / 'state/production-registry.sqlite3')) as con, con:con.execute("DELETE FROM allocations WHERE sample_id='S000001_sample_000186'")
        seal(self.baseline)
        self.assertEqual(self.report()['checks']['production_registry']['status'], 'FAIL')


if __name__ == '__main__':unittest.main()
