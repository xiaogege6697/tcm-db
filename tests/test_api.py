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


if __name__ == '__main__':
    unittest.main(verbosity=2)
