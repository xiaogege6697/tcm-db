#!/usr/bin/env python3
"""tcm-db API 安全回归测试（标准库 unittest，零外部依赖）。

覆盖：
- SQL 注入防护（表名/列名白名单）
- /screenshots/ 目录穿越防护（../、URL 编码 %2e%2e、双重编码、绝对路径、符号链接逃逸）
"""
import unittest
import sys
import os
import pathlib
import tempfile
import threading
import urllib.request
import urllib.error
import json

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import server  # noqa: E402


class TestSqlInjectionWhitelist(unittest.TestCase):
    """白名单防注入：表名/列名一律走静态白名单，参数值用 ? 占位符"""

    def test_allowed_tables_includes_core(self):
        for t in ('herbs', 'formulas', 'symptoms', 'syndromes', 'clinical_cases'):
            self.assertIn(t, server.ALLOWED_TABLES)

    def test_browse_valid_table(self):
        data = server.api_browse('herbs', page=1, per_page=5)
        self.assertIn('data', data)
        self.assertLessEqual(len(data['data']), 5)

    def test_browse_invalid_table_union(self):
        with self.assertRaises(server.HttpError):
            server.api_browse('herbs UNION SELECT sql FROM sqlite_master--')

    def test_browse_invalid_filter_column(self):
        # 任意 query 参数名成为列名 → 必须被白名单拒绝
        with self.assertRaises(server.HttpError):
            server.api_browse('herbs', filters={"1=1 UNION SELECT sql FROM sqlite_master--": 'x'})

    def test_browse_valid_filter_column(self):
        data = server.api_browse('herbs', filters={'nature': '寒'}, per_page=5)
        self.assertIn('data', data)

    def test_detail_invalid_table(self):
        with self.assertRaises(server.HttpError):
            server.api_detail('foo; DROP TABLE formulas--', 1)

    def test_filter_options_invalid_column(self):
        with self.assertRaises(server.HttpError):
            server.api_filter_options('herbs', 'evil_col FROM sqlite_master--')

    def test_filter_options_invalid_table(self):
        with self.assertRaises(server.HttpError):
            server.api_filter_options('evil', 'name')

    def test_export_table_invalid(self):
        with self.assertRaises(server.HttpError):
            server.api_export_table('herbs WHERE 1=1 UNION SELECT sql FROM sqlite_master--')


class TestPathTraversal(unittest.TestCase):
    """/screenshots/ 目录穿越防护"""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix='tcm_shots_'))
        (self.root / 'a.webp').write_bytes(b'img')
        # 符号链接逃逸：root/evil.webp -> root 外的文件
        self.outside_dir = pathlib.Path(tempfile.mkdtemp(prefix='tcm_out_'))
        self.outside = self.outside_dir / 'secret'
        self.outside.write_bytes(b'secret')
        self.link = self.root / 'evil.webp'
        os.symlink(self.outside, self.link)

    def tearDown(self):
        self.link.unlink(missing_ok=True)
        self.outside.unlink(missing_ok=True)
        self.outside_dir.rmdir()
        for p in self.root.iterdir():
            p.unlink()
        self.root.rmdir()

    def test_valid_file(self):
        t = server.resolve_screenshot('a.webp', root=self.root)
        self.assertEqual(t, (self.root / 'a.webp').resolve())

    def test_dotdot(self):
        with self.assertRaises(server.HttpError):
            server.resolve_screenshot('../etc/passwd', root=self.root)

    def test_url_encoded_dotdot(self):
        # %2e%2e%2f -> 解码为 ../  -> 越界
        with self.assertRaises(server.HttpError):
            server.resolve_screenshot('%2e%2e%2fetc%2fpasswd', root=self.root)

    def test_double_encoded_stays_in_root(self):
        # 双重编码 %252e%252e -> 一次解码为字面 %2e%2e（不逃逸）；绝不能返回根外路径
        target = server.resolve_screenshot('%252e%252e%252fetc%252fpasswd', root=self.root)
        self.assertTrue(str(target).startswith(str(self.root.resolve())))

    def test_absolute_path(self):
        with self.assertRaises(server.HttpError):
            server.resolve_screenshot('/etc/passwd', root=self.root)

    def test_symlink_escape(self):
        # root 内的符号链接指向外部 -> resolve 跟随 -> 越界 -> 拒绝
        with self.assertRaises(server.HttpError):
            server.resolve_screenshot('evil.webp', root=self.root)


class TestFormulaRedirect(unittest.TestCase):
    """旧 formula id 透明重定向到 canonical id（复用 evidence merged_from + 启动内存缓存）"""

    def test_canonical_no_redirect(self):
        """canonical id 正常请求不带重定向标记"""
        d = server.api_detail('formulas', 209)
        self.assertIsNotNone(d)
        self.assertNotIn('_redirected_from', d)

    def test_old_id_redirects(self):
        """旧 id 命中重定向，返回 canonical 数据并附重定向信息"""
        d = server.api_detail('formulas', 8)
        self.assertIsNotNone(d)
        self.assertEqual(d['_redirected_from'], 8)
        self.assertEqual(d['_canonical_id'], 209)
        self.assertEqual(d['id'], 209)

    def test_unknown_id_returns_none(self):
        """未知 id（既非 canonical 也非旧 id）返回 None"""
        self.assertIsNone(server.api_detail('formulas', 999999))

    def test_invalid_id_raises_400(self):
        """非法 id 抛出 HttpError 且 code==400"""
        with self.assertRaises(server.HttpError) as cm:
            server.api_detail('formulas', 'abc')
        self.assertEqual(cm.exception.code, 400)

        with self.assertRaises(server.HttpError) as cm:
            server.api_detail('formulas', '0')
        self.assertEqual(cm.exception.code, 400)

        with self.assertRaises(server.HttpError) as cm:
            server.api_detail('formulas', '-1')
        self.assertEqual(cm.exception.code, 400)

    def test_cycle_protection(self):
        """循环重定向检测：成环的映射应返回 None"""
        original_map = server.FORMULA_REDIRECT_MAP
        try:
            server.FORMULA_REDIRECT_MAP = {1: 2, 2: 1}
            self.assertIsNone(server.resolve_formula_redirect(1))
        finally:
            server.FORMULA_REDIRECT_MAP = original_map

    def test_single_mapping_no_collision(self):
        """单射性验证：同一 old_id 只映射到一个 canonical_id，且不映射到自身"""
        for old_id, canon_id in server.FORMULA_REDIRECT_MAP.items():
            self.assertEqual(server.resolve_formula_redirect(old_id), canon_id)
            self.assertNotEqual(canon_id, old_id)
        self.assertIsNone(server.resolve_formula_redirect(777))


class TestHttpDetailLayer(unittest.TestCase):
    """真实 HTTP 层回归：验证 handler 对 api_detail 返回值的转码契约。
    函数层测试只验证 api_detail 返回值，无法捕获 send_json(None)→200 null 这类
    handler 层状态码错误（曾因此漏掉未知id应404）。"""

    @classmethod
    def setUpClass(cls):
        cls.httpd = server.HTTPServer(('127.0.0.1', 0), server.TCMHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 禁系统代理，直连回环
        try:
            r = opener.open(f'http://127.0.0.1:{self.port}{path}', timeout=5)
            return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')

    def test_unknown_formula_returns_404_json(self):
        """未知 formula id → HTTP 404 + JSON 错误体（非 200 null，非 HTML）"""
        code, body = self._get('/api/detail/formulas/999999')
        self.assertEqual(code, 404)
        self.assertEqual(json.loads(body), {'error': 'not found'})

    def test_canonical_returns_200_no_redirect(self):
        """canonical 正常请求 → 200 且无重定向标记"""
        code, body = self._get('/api/detail/formulas/209')
        self.assertEqual(code, 200)
        self.assertNotIn('_redirected_from', json.loads(body))

    def test_old_id_redirects_200(self):
        """旧id → 200 + 重定向字段"""
        code, body = self._get('/api/detail/formulas/8')
        self.assertEqual(code, 200)
        d = json.loads(body)
        self.assertEqual(d['_redirected_from'], 8)
        self.assertEqual(d['_canonical_id'], 209)

    def test_invalid_id_returns_400(self):
        """非法id → HTTP 400"""
        code, _ = self._get('/api/detail/formulas/abc')
        self.assertEqual(code, 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
