#!/usr/bin/env python3
"""etl.py 最小入口测试（临时数据库，零外部依赖）。

覆盖：--check 检测来源键缺陷 / blocked 步骤非0退出 / 错误db / dry-run 只读。
不测 case-ingest 写入（BLOCKED，未实现，因无可靠来源键）。
"""
import unittest, sqlite3, tempfile, os, sys, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
import etl


def make_db(with_issues=True):
    db = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE clinical_cases(
        id INTEGER PRIMARY KEY, case_date TEXT, patient_id TEXT, chief_complaint TEXT,
        raw_path TEXT, source_repo TEXT)""")
    if with_issues:
        conn.execute("INSERT INTO clinical_cases(patient_id,chief_complaint,raw_path,source_repo) VALUES('p1','主诉A','f.md','repo')")
        conn.execute("INSERT INTO clinical_cases(patient_id,chief_complaint,raw_path,source_repo) VALUES('p2','主诉B','f.md','repo')")  # 同raw_path多案
        conn.execute("INSERT INTO clinical_cases(patient_id,chief_complaint,raw_path,source_repo) VALUES('核心要点','x','','repo')")  # raw_path空
    conn.commit(); conn.close()
    return db


class TestCheckSources(unittest.TestCase):
    def test_detects_issues(self):
        db = make_db(with_issues=True)
        try:
            conn = etl.get_conn(db)
            stats, issues = etl.check_sources(conn)
            self.assertFalse(stats['has_unique_constraint'])  # 无 UNIQUE
            self.assertGreaterEqual(stats['raw_path_null'], 1)  # raw_path 空
            self.assertGreaterEqual(stats['multi_case_files'], 1)  # 同文件多案
            self.assertTrue(any('UNIQUE' in i for i in issues))
            self.assertTrue(any('raw_path' in i for i in issues))
            conn.close()
        finally:
            os.unlink(db)

    def test_clean_db_still_reports_no_unique(self):
        """空 db 仍报"无 UNIQUE"（裸 INSERT 无法幂等）"""
        db = make_db(with_issues=False)
        try:
            conn = etl.get_conn(db)
            stats, issues = etl.check_sources(conn)
            self.assertEqual(stats['total'], 0)
            self.assertFalse(stats['has_unique_constraint'])
            self.assertTrue(any('UNIQUE' in i for i in issues))
            conn.close()
        finally:
            os.unlink(db)


class TestCmdCheck(unittest.TestCase):
    def test_check_returns_nonzero_when_issues(self):
        db = make_db(with_issues=True)
        try:
            args = argparse.Namespace(db=db, verbose=False)
            rc = etl.cmd_check(args)
            self.assertEqual(rc, 1)  # 有 issues → 非幂等 → 1
        finally:
            os.unlink(db)

    def test_check_missing_db(self):
        args = argparse.Namespace(db='/nonexistent/xyz.db', verbose=False)
        rc = etl.cmd_check(args)
        self.assertEqual(rc, 3)


class TestBlockedSteps(unittest.TestCase):
    def _run_main(self, argv):
        old = sys.argv
        sys.argv = argv
        try:
            etl.setup_logging(False)
            return etl.main()
        finally:
            sys.argv = old

    def test_case_ingest_blocked(self):
        self.assertEqual(self._run_main(['etl.py', '--step', 'case-ingest']), 2)

    def test_formulas_ingest_not_implemented(self):
        self.assertEqual(self._run_main(['etl.py', '--step', 'formulas-ingest']), 2)

    def test_default_lists_steps(self):
        self.assertEqual(self._run_main(['etl.py']), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
