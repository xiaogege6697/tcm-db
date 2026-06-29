#!/usr/bin/env python3
"""migrate_formula_dedup 迁移工具回归测试（临时数据库，零外部依赖）。

覆盖（用户要求的 8 类）：
  1. subject 迁移
  2. object 迁移
  3. source_record_id 保持不变（历史来源不改）
  4. dedupe 碰撞：exact 合并 / 非完全一致中止
  5. dry-run 零写入（事务 ROLLBACK 恢复）
  6. 重跑幂等（迁移后 _plan_group 返回 None）
  7. 故障注入整批 ROLLBACK
  8. 多组单一事务
"""
import unittest, sqlite3, tempfile, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
import migrate_formula_dedup as M
from migrate_formula_dedup import EvidenceCollisionError

# 脚本 EVIDENCE_DDL 的 relation_type 枚举过时（缺 normalized_from，db 实际已含），测试补全
_DDL = M.EVIDENCE_DDL.replace(
    "'source_record','field_value','entity_relation','textual','merged_from'",
    "'source_record','field_value','entity_relation','textual','merged_from','normalized_from'")


def _evidence(**over):
    """构造一条 evidence dict（默认合法，可覆盖任意字段）"""
    base = dict(subject_type='formula', subject_id=2, relation_type='merged_from',
                object_type=None, object_id=None, evidence_kind='source_record',
                source_type='database_row', source_record_type='formula',
                source_record_id='1', source_id=None, source_path='p.md',
                field_name=None, evidence_text='t', confidence=None,
                extraction_method='migration', review_status='pending',
                metadata_json='{}')
    base.update(over)
    return base


def make_conn():
    """临时 db：evidence(补枚举) + formulas(含 MERGE_FIELDS) + herbs + formula_herbs(FK→formulas)"""
    db = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None  # autocommit：INSERT 不隐式开事务，测试可显式 BEGIN/ROLLBACK
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_DDL)
    cols = ['id INTEGER PRIMARY KEY', 'name TEXT', 'source_repo TEXT', 'raw_path TEXT']
    cols += [f'{f} TEXT' for f in M.MERGE_FIELDS]
    conn.execute(f"CREATE TABLE formulas({','.join(cols)})")
    conn.execute("CREATE TABLE herbs(id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("""CREATE TABLE formula_herbs(
        formula_id INTEGER NOT NULL REFERENCES formulas(id),
        herb_id INTEGER NOT NULL REFERENCES herbs(id),
        role TEXT, PRIMARY KEY(formula_id, herb_id))""")
    conn.execute("CREATE TABLE clinical_cases(id INTEGER PRIMARY KEY)")
    conn.execute("""CREATE TABLE case_formulas(
        case_id INTEGER NOT NULL REFERENCES clinical_cases(id),
        formula_id INTEGER NOT NULL REFERENCES formulas(id),
        PRIMARY KEY(case_id, formula_id))""")
    return conn, db


def _add_formula(conn, fid, name, **kw):
    cols = {'id': fid, 'name': name}; cols.update(kw)
    fields = ','.join(cols.keys()); ph = ','.join('?' * len(cols))
    conn.execute(f"INSERT INTO formulas ({fields}) VALUES ({ph})", list(cols.values()))


class TestEvidenceMigration(unittest.TestCase):
    """单元层：_migrate_formula_evidence 的 subject/object/source_record_id/碰撞"""

    def setUp(self):
        self.conn, self.db = make_conn()
        for i in (1, 2, 3):
            _add_formula(self.conn, i, '桂枝汤', source_repo='nihaixia')

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db):
            os.unlink(self.db)

    def test_subject_migration(self):
        """1) 旧id(2)作 subject 的 evidence 迁移到 canon(1)，subject_id 变，dedupe_key 重算"""
        M.insert_evidence(self.conn, _evidence(
            subject_id=2, relation_type='normalized_from', source_record_id='2', evidence_text='原名'))
        stats = M._migrate_formula_evidence(self.conn, 2, 1)
        self.assertEqual(stats['subject'], 1)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE subject_id=2").fetchone()[0], 0)
        row = self.conn.execute(
            "SELECT * FROM evidence WHERE subject_id=1 AND relation_type='normalized_from'").fetchone()
        self.assertIsNotNone(row)

    def test_object_migration(self):
        """2) 旧id(2)作 object 的 evidence 迁移到 canon(1)"""
        M.insert_evidence(self.conn, _evidence(
            subject_id=1, relation_type='entity_relation', object_type='formula',
            object_id=2, evidence_text='r'))
        stats = M._migrate_formula_evidence(self.conn, 2, 1)
        self.assertEqual(stats['object'], 1)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE object_id=2").fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE object_id=1 AND object_type='formula'").fetchone()[0], 1)

    def test_source_record_id_unchanged(self):
        """3) 迁移后 source_record_id 保持旧id值（历史来源绝不改成 canonical）"""
        M.insert_evidence(self.conn, _evidence(
            subject_id=2, source_record_id='2', relation_type='normalized_from'))
        M._migrate_formula_evidence(self.conn, 2, 1)
        row = self.conn.execute(
            "SELECT source_record_id FROM evidence WHERE subject_id=1").fetchone()
        self.assertEqual(row['source_record_id'], '2')

    def test_dedupe_exact_merge(self):
        """4a) exact 碰撞（身份+内容全一致）→ 合并，计 merged，不重复"""
        M.insert_evidence(self.conn, _evidence(
            subject_id=1, relation_type='normalized_from', source_record_id='2',
            evidence_text='原名', source_path='p.md'))
        M.insert_evidence(self.conn, _evidence(
            subject_id=3, relation_type='normalized_from', source_record_id='2',
            evidence_text='原名', source_path='p.md'))
        stats = M._migrate_formula_evidence(self.conn, 3, 1)
        self.assertEqual(stats['merged'], 1)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE subject_id=1 AND relation_type='normalized_from'"
        ).fetchone()[0], 1)

    def test_dedupe_collision_abort(self):
        """4b) 非完全一致碰撞（dedupe_key 同但 evidence_text 不同）→ raise，不静默覆盖"""
        M.insert_evidence(self.conn, _evidence(
            subject_id=1, relation_type='normalized_from', source_record_id='2',
            evidence_text='A', source_path='p.md'))
        M.insert_evidence(self.conn, _evidence(
            subject_id=3, relation_type='normalized_from', source_record_id='2',
            evidence_text='B', source_path='p.md'))
        with self.assertRaises(EvidenceCollisionError):
            M._migrate_formula_evidence(self.conn, 3, 1)


class TestApplyGroupAndMigrate(unittest.TestCase):
    """集成层：_apply_group / 事务 的 dry-run/幂等/ROLLBACK/多组"""

    def test_apply_group_migrates_relation_and_evidence(self):
        """_apply_group 完整链：关系归并 canon + 旧id evidence 迁移 + 删旧 formula + 门禁通过"""
        conn, db = make_conn()
        try:
            for i in (1, 2, 3):
                _add_formula(conn, i, '桂枝汤', source_repo='nihaixia')
            conn.execute("INSERT INTO herbs(id,name) VALUES (10,'甘草')")
            for i in (1, 2, 3):
                conn.execute("INSERT INTO formula_herbs(formula_id,herb_id,role) VALUES(?,10,'使')", (i,))
            M.insert_evidence(conn, _evidence(
                subject_id=2, relation_type='normalized_from', source_record_id='2'))
            p = M._plan_group(conn, '桂枝汤')
            self.assertEqual(p['canon_id'], 1)
            conn.execute("BEGIN")
            M._apply_group(conn, p)
            conn.execute("COMMIT")
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM formulas WHERE name='桂枝汤'").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM formula_herbs WHERE formula_id=1").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE subject_id IN (2,3)").fetchone()[0], 0)
        finally:
            conn.close(); os.unlink(db)

    def test_dry_run_zero_write(self):
        """5) dry-run 同代码路径但 ROLLBACK → db 零持久写入"""
        conn, db = make_conn()
        try:
            for i in (1, 2, 3):
                _add_formula(conn, i, '桂枝汤', source_repo='nihaixia')
            conn.execute("BEGIN")
            p = M._plan_group(conn, '桂枝汤')
            M._apply_group(conn, p)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0], 1)  # 事务内已删
            conn.execute("ROLLBACK")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0], 3)  # 回滚恢复
        finally:
            conn.close(); os.unlink(db)

    def test_idempotent_rerun(self):
        """6) 重跑幂等：迁移后该组无重复 → _plan_group 返回 None"""
        conn, db = make_conn()
        try:
            for i in (1, 2, 3):
                _add_formula(conn, i, '桂枝汤', source_repo='nihaixia')
            conn.execute("BEGIN")
            M._apply_group(conn, M._plan_group(conn, '桂枝汤'))
            conn.execute("COMMIT")
            self.assertIsNone(M._plan_group(conn, '桂枝汤'))  # 只剩1行，无重复
        finally:
            conn.close(); os.unlink(db)

    def test_failure_injection_rollback(self):
        """7) 故障注入：迁移中 EvidenceCollisionError raise → 整批 ROLLBACK，formulas 恢复"""
        conn, db = make_conn()
        try:
            for i in (1, 2, 3):
                _add_formula(conn, i, '桂枝汤', source_repo='nihaixia')
            M.insert_evidence(conn, _evidence(
                subject_id=1, relation_type='normalized_from', source_record_id='2',
                evidence_text='A', source_path='p.md'))
            M.insert_evidence(conn, _evidence(
                subject_id=2, relation_type='normalized_from', source_record_id='2',
                evidence_text='B', source_path='p.md'))
            before = conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0]
            conn.execute("BEGIN")
            with self.assertRaises(EvidenceCollisionError):
                M._apply_group(conn, M._plan_group(conn, '桂枝汤'))
            conn.execute("ROLLBACK")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0], before)
        finally:
            conn.close(); os.unlink(db)

    def test_multi_group_single_txn(self):
        """8) 多组单一事务：桂枝汤+麻黄汤一起迁移，一个 COMMIT"""
        conn, db = make_conn()
        try:
            _add_formula(conn, 1, '桂枝汤', source_repo='nihaixia')
            _add_formula(conn, 2, '桂枝汤', source_repo='nihaixia')
            _add_formula(conn, 3, '麻黄汤', source_repo='nihaixia')
            _add_formula(conn, 4, '麻黄汤', source_repo='nihaixia')
            conn.execute("BEGIN")
            M._apply_group(conn, M._plan_group(conn, '桂枝汤'))
            M._apply_group(conn, M._plan_group(conn, '麻黄汤'))
            conn.execute("COMMIT")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0], 2)
            names = [r[0] for r in conn.execute(
                "SELECT name FROM formulas ORDER BY id").fetchall()]
            self.assertEqual(names, ['桂枝汤', '麻黄汤'])
        finally:
            conn.close(); os.unlink(db)


if __name__ == '__main__':
    unittest.main(verbosity=2)
