#!/usr/bin/env python3
"""schema 一致性测试：脚本 EVIDENCE_DDL 的 CHECK 枚举须覆盖正式库 evidence 表。

防止 create-evidence 用过时 DDL 重建后丢枚举（如 normalized_from 漂移事件重演）。
只读正式库（sqlite_master），不写。
"""
import unittest, re, sqlite3, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
import migrate_formula_dedup as M


def _enum_from_ddl(ddl, col):
    """从 DDL 提取 `col ... CHECK (col IN ('a','b',...))` 的枚举集合；找不到返回 None。"""
    m = re.search(
        rf"\b{col}\b[^,]*?CHECK\s*\(.*?\b{col}\s+IN\s*\(([^)]+)\)",
        ddl, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return set(re.findall(r"'([^']+)'", m.group(1)))


# 与正式库对齐校验的枚举字段（CHECK col IN (...) 结构）
_ENUM_COLS = ['subject_type', 'relation_type', 'evidence_kind', 'source_type',
              'source_record_type', 'extraction_method', 'review_status']


class TestSchemaParity(unittest.TestCase):
    """脚本 EVIDENCE_DDL 与正式库 evidence schema 的枚举一致性（防漂移）"""

    def test_script_ddl_covers_production_enums(self):
        """脚本 DDL 每个 CHECK 枚举字段 ⊇ 正式库 evidence（create-evidence 重建不丢枚举）"""
        conn = sqlite3.connect(str(M.DB_PATH))
        db_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='evidence'").fetchone()[0]
        conn.close()
        missing_all = {}
        for col in _ENUM_COLS:
            script_enum = _enum_from_ddl(M.EVIDENCE_DDL, col)
            db_enum = _enum_from_ddl(db_sql, col)
            self.assertIsNotNone(script_enum, f"脚本 EVIDENCE_DDL 未找到 {col} 枚举")
            self.assertIsNotNone(db_enum, f"正式库 evidence 未找到 {col} 枚举")
            missing = db_enum - script_enum
            if missing:
                missing_all[col] = sorted(missing)
        self.assertEqual(
            missing_all, {},
            f"脚本 EVIDENCE_DDL 枚举落后于正式库（create-evidence 重建会丢失）: {missing_all}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
