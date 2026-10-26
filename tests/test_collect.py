import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/maayuan-issue-helper/scripts/collect.py'
spec = importlib.util.spec_from_file_location('collector', SCRIPT)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'MaaYuan 中文副本 v0.0'
        self.root.mkdir()
        self.put('interface.json', '{"version":"v2.2.1-beta.1","token":"CONFIG-SECRET"}')

    def put(self, relative, content, encoding='utf-8'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)
        return path

    def run_collect(self, **overrides):
        options = dict(root=str(self.root), out=str(self.base / 'output'), date='2026-10-22',
                       max_file_mib=4, max_total_mib=24, max_scan_mib=64)
        options.update(overrides)
        return c.collect(argparse.Namespace(**options))

    def test_date_context_redaction_archive_and_no_source_mutation(self):
        source = self.put('debug/maa.log', '[2026-10-21 23:59:00][ERR] OTHER-DATE\n'
                          '[2026-10-22 09:00:00][ERR] token="TOP-SECRET"\n'
                          'Traceback line password=SUPER-SECRET\n'
                          '[2026-10-22 09:01:00] task_id=42 node=启动\n'
                          '[2026-10-23 00:01:00] NEXT-DATE\n')
        self.put('debug/maa.bak.log', '[2026-10-22 08:00:00] startup\n')
        self.put('logs/log-20261022.log', '[2026-10-22 09:00:00] MFA version: v2.6.8\n')
        self.put('debug/custom/2026-10-22.log', '2026-10-22 09:00:00 | AgentServer 启动\n')
        self.put('config/config.json', '{"password":"PRIVATE-CONFIG"}')
        self.put('debug/on_error/private.png', 'PRIVATE-IMAGE')
        before = source.read_bytes()
        result = self.run_collect()
        out = Path(result['bundle'])
        text = (out / 'logs/debug/maa.log').read_text(encoding='utf-8')
        for secret in ['TOP-SECRET', 'SUPER-SECRET', 'OTHER-DATE', 'NEXT-DATE']:
            self.assertNotIn(secret, text)
        self.assertIn('L3\tTraceback', text)
        self.assertIn('task_id=42 node=启动', text)
        self.assertEqual(before, source.read_bytes())
        meta = json.loads((out / 'metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['current_resource_version'], 'v2.2.1-beta.1')
        self.assertEqual(meta['observed_runtime_versions'][0]['value'], 'v2.6.8')
        (out / 'report.md').write_text('# 已完成的测试报告', encoding='utf-8')
        packed = c.pack(argparse.Namespace(bundle=str(out)))
        with zipfile.ZipFile(packed['zip']) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read('report.md').decode('utf-8'), '# 已完成的测试报告')
            self.assertFalse(any('config/' in name or name.endswith('.png') for name in archive.namelist()))
            manifest = json.loads(archive.read('manifest.json'))
            for name, digest in manifest['sha256'].items():
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())
        with self.assertRaises(FileExistsError):
            self.run_collect()

    def test_missing_and_nonmatching_are_explicit(self):
        self.put('debug/maa.log', '[2026-01-01 00:00:00] old\n')
        out = Path(self.run_collect()['bundle'])
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['files'][0]['status'], 'no_matching_lines_in_scanned_range')
        self.assertTrue(manifest['excluded'])

    def test_utf16_and_gb18030(self):
        self.put('debug/maa.log', '[2026-10-22 00:00:00] 中文错误\n', 'utf-16')
        self.put('debug/maa.bak.log', '[2026-10-22 00:00:00] 中文启动\n', 'gb18030')
        out = Path(self.run_collect()['bundle'])
        self.assertIn('中文错误', (out / 'logs/debug/maa.log').read_text(encoding='utf-8'))
        self.assertIn('中文启动', (out / 'logs/debug/maa.bak.log').read_text(encoding='utf-8'))

    def test_limits_and_binary_are_visible(self):
        self.put('debug/maa.log', '[2026-10-22 00:00:00] ' + ('x' * 200 + '\n') * 12000)
        self.put('debug/maa.bak.log', '\x00\x01\x00')
        out = Path(self.run_collect(max_file_mib=1, max_scan_mib=1)['bundle'])
        records = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))['files']
        self.assertTrue(any(r.get('scan_truncated') for r in records))
        self.assertTrue(any(r.get('output_truncated') for r in records))
        self.assertTrue(any(r['status'] == 'read_failed' for r in records))

    def test_pack_rejects_path_escape(self):
        out = Path(self.run_collect()['bundle'])
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        manifest['files'].append({'status': 'included', 'export': 'logs/../../secret.log'})
        c.write_json(out / 'manifest.json', manifest)
        with self.assertRaises(ValueError):
            c.pack(argparse.Namespace(bundle=str(out)))

    def test_symlink_excluded(self):
        outside = self.base / 'private.log'
        outside.write_text('[2026-10-22 00:00:00] PRIVATE')
        (self.root / 'debug').mkdir()
        try:
            (self.root / 'debug/maa.log').symlink_to(outside)
        except OSError:
            self.skipTest('OS does not permit symlink creation')
        out = Path(self.run_collect()['bundle'])
        self.assertFalse((out / 'logs/debug/maa.log').exists())

    def test_redacts_common_identity_and_credentials(self):
        text = 'Authorization: Bearer THIS-IS-SECRET\n' + r'C:\Users\Alice\folder\file.log' + '\n'
        text += 'email=alice@example.com uid=123456 access_token="TOKENVALUE"\n'
        text += 'https://example.org/?credential=URLSECRET 192.168.1.2 13812345678\n'
        cleaned = c.redact(text)
        for value in ['THIS-IS-SECRET', 'Alice', 'alice@example.com', '123456', 'TOKENVALUE', 'URLSECRET', '192.168.1.2', '13812345678']:
            self.assertNotIn(value, cleaned)


if __name__ == '__main__':
    unittest.main()
