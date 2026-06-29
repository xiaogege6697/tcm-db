#!/usr/bin/env python3
"""
tcm-db 数据质量审计闸门
只读审计，绝不写库

用法:
    python scripts/audit_db.py                     # 默认路径审计
    python scripts/audit_db.py --db path/to/db     # 指定数据库
    python scripts/audit_db.py --json              # JSON 输出
    python scripts/audit_db.py --report report.txt # 写报告到文件
    python scripts/audit_db.py self-test           # 自检(临时库)
"""

import sqlite3
import json
import re
import sys
import argparse
import os
import tempfile
from pathlib import Path


# ================================================================
# 常量 (勿写错: VIOLATION 不是 VOLATION)
# ================================================================

VIOLATION_BLOCKQUOTE = "VIOLATION_BLOCKQUOTE"
VIOLATION_DESCRIPTIVE = "VIOLATION_DESCRIPTIVE"
VIOLATION_MULTI_ENTITY = "VIOLATION_MULTI_ENTITY"
VIOLATION_EMPTY = "VIOLATION_EMPTY"
VIOLATION_CONTROL_CHAR = "VIOLATION_CONTROL_CHAR"

# 实体类型 → 表名 (16 个, 单数 → 复数)
TYPE_TO_TABLE = {
    "formula":          "formulas",
    "herb":             "herbs",
    "symptom":          "symptoms",
    "syndrome":         "syndromes",
    "acupoint":         "acupoints",
    "meridian":         "meridians",
    "clinical_case":    "clinical_cases",
    "folk_formula":     "folk_formulas",
    "course":           "courses",
    "classic":          "classics",
    "course_note":      "course_notes",
    "book":             "books",
    "lecture":          "lectures",
    "tianji":           "tianji",
    "treatment_method": "treatment_methods",
    "diagnostic_note":  "diagnostic_notes",
}

# JSON 字段: (表名, 列名) — 必须实际存在，否则 raise
JSON_FIELDS = [
    ("clinical_cases", "disease_tags"),
    ("symptoms",        "differential"),
    ("symptoms",        "required_questions"),
]

# 关系孤儿检查: (关联表, 外键列, 主表)
ORPHAN_CHECKS = [
    ("formula_herbs",      "formula_id",  "formulas"),
    ("formula_herbs",      "herb_id",     "herbs"),
    ("formula_syndromes",  "formula_id",  "formulas"),
    ("formula_syndromes",  "syndrome_id", "syndromes"),
    ("case_formulas",      "case_id",     "clinical_cases"),
    ("case_formulas",      "formula_id",  "formulas"),
    ("case_herbs",         "case_id",     "clinical_cases"),
    ("case_herbs",         "herb_id",     "herbs"),
    ("syndrome_symptoms",  "syndrome_id", "syndromes"),
    ("syndrome_symptoms",  "symptom_id",  "symptoms"),
]

# 方剂后缀 (用于多方疑似检测)
_FORMULA_SUFFIX_RE = re.compile(r"[汤丸散丹膏饮]")


# ================================================================
# 工具函数
# ================================================================

def get_default_db_path():
    """默认 db 路径: 脚本上一级/tcm_knowledge.db (不依赖 cwd)"""
    return Path(__file__).resolve().parent.parent / "tcm_knowledge.db"


def _table_exists(conn, table_name):
    """检查表是否存在"""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_columns(conn, table_name):
    """获取表的列名列表"""
    return [
        r[1]
        for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    ]


# ================================================================
# 各项检查
# ================================================================

def check_integrity(conn):
    """PRAGMA integrity_check"""
    errors = []
    try:
        for row in conn.execute("PRAGMA integrity_check"):
            if row[0] != "ok":
                errors.append(row[0])
    except Exception as e:
        errors.append(f"integrity_check 异常: {e}")
    return errors


def check_foreign_keys(conn):
    """PRAGMA foreign_key_check"""
    errors = []
    try:
        for row in conn.execute("PRAGMA foreign_key_check"):
            errors.append(
                f"table={row[0]}, rowid={row[1]}, "
                f"parent={row[2]}, fkid={row[3]}"
            )
    except Exception as e:
        errors.append(f"foreign_key_check 异常: {e}")
    return errors


def check_orphan_relations(conn):
    """检查关联表中外键 ID 不在主表的孤儿记录"""
    orphans = []
    for junction_tbl, fk_col, main_tbl in ORPHAN_CHECKS:
        if not _table_exists(conn, junction_tbl):
            continue
        if not _table_exists(conn, main_tbl):
            continue
        cols = _get_columns(conn, junction_tbl)
        if fk_col not in cols:
            continue
        try:
            sql = (
                f"SELECT j.rowid, j.{fk_col} "
                f"FROM {junction_tbl} j "
                f"LEFT JOIN {main_tbl} m ON j.{fk_col} = m.id "
                f"WHERE j.{fk_col} IS NOT NULL AND m.id IS NULL"
            )
            for row in conn.execute(sql):
                orphans.append({
                    "table":            junction_tbl,
                    "column":           fk_col,
                    "rowid":            row[0],
                    "missing_id":       row[1],
                    "referenced_table": main_tbl,
                })
        except Exception as e:
            orphans.append({
                "table":  junction_tbl,
                "column": fk_col,
                "error":  str(e),
            })
    return orphans


def check_json_fields(conn):
    """
    检查 JSON 字段有效性 (json_valid)。
    列不存在时 raise — 不静默跳过。
    """
    errors = []
    for tbl, col in JSON_FIELDS:
        if not _table_exists(conn, tbl):
            raise ValueError(
                f"JSON 字段检查失败: 表 {tbl} 不存在"
            )
        columns = _get_columns(conn, tbl)
        if col not in columns:
            raise ValueError(
                f"JSON 字段检查失败: 表 {tbl} 中不存在列 {col}"
            )
        try:
            sql = (
                f"SELECT rowid, {col} FROM {tbl} "
                f"WHERE {col} IS NOT NULL AND json_valid({col}) = 0"
            )
            for row in conn.execute(sql):
                errors.append({
                    "table":         tbl,
                    "column":        col,
                    "rowid":         row[0],
                    "value_preview": str(row[1])[:100],
                })
        except sqlite3.OperationalError as e:
            errors.append({
                "table":  tbl,
                "column": col,
                "error":  f"json_valid 不可用或查询失败: {e}",
            })
    return errors


def check_evidence_references(conn):
    """检查 evidence 表的多态引用 (subject / object)"""
    errors = []
    if not _table_exists(conn, "evidence"):
        return errors

    cols = _get_columns(conn, "evidence")

    # — subject_type / subject_id —
    if "subject_type" in cols and "subject_id" in cols:
        try:
            for row in conn.execute(
                "SELECT rowid, subject_type, subject_id "
                "FROM evidence "
                "WHERE subject_type IS NOT NULL AND subject_id IS NOT NULL"
            ):
                rowid, stype, sid = row
                target = TYPE_TO_TABLE.get(stype)
                if target and _table_exists(conn, target):
                    cnt = conn.execute(
                        f"SELECT COUNT(*) FROM {target} WHERE id=?",
                        (sid,),
                    ).fetchone()[0]
                    if cnt == 0:
                        errors.append({
                            "table":        "evidence",
                            "rowid":        rowid,
                            "ref_type":     "subject",
                            "entity_type":  stype,
                            "missing_id":   sid,
                            "target_table": target,
                        })
        except Exception as e:
            errors.append({
                "table":    "evidence",
                "ref_type": "subject",
                "error":    str(e),
            })

    # — object_type / object_id —
    ot_col = "object_type" if "object_type" in cols else None
    oi_col = "object_id" if "object_id" in cols else None
    if ot_col and oi_col:
        try:
            for row in conn.execute(
                f"SELECT rowid, {ot_col}, {oi_col} "
                f"FROM evidence "
                f"WHERE {ot_col} IS NOT NULL AND {oi_col} IS NOT NULL"
            ):
                rowid, otype, oid = row
                # source_record_id 属 historical, 不计 orphan
                if otype == "historical":
                    continue
                target = TYPE_TO_TABLE.get(otype)
                if target and _table_exists(conn, target):
                    cnt = conn.execute(
                        f"SELECT COUNT(*) FROM {target} WHERE id=?",
                        (oid,),
                    ).fetchone()[0]
                    if cnt == 0:
                        errors.append({
                            "table":        "evidence",
                            "rowid":        rowid,
                            "ref_type":     "object",
                            "entity_type":  otype,
                            "missing_id":   oid,
                            "target_table": target,
                        })
        except Exception as e:
            errors.append({
                "table":    "evidence",
                "ref_type": "object",
                "error":    str(e),
            })

    return errors


def check_quarantine_json(conn):
    """检查 ingestion_quarantine.raw_record_json"""
    errors = []
    if not _table_exists(conn, "ingestion_quarantine"):
        return errors
    cols = _get_columns(conn, "ingestion_quarantine")
    if "raw_record_json" not in cols:
        return errors
    try:
        for row in conn.execute(
            "SELECT rowid, raw_record_json "
            "FROM ingestion_quarantine "
            "WHERE raw_record_json IS NOT NULL "
            "AND json_valid(raw_record_json) = 0"
        ):
            errors.append({
                "table":         "ingestion_quarantine",
                "rowid":         row[0],
                "value_preview": str(row[1])[:100],
            })
    except sqlite3.OperationalError as e:
        errors.append({
            "table": "ingestion_quarantine",
            "error": str(e),
        })
    return errors


def check_formula_name_quality(conn):
    """
    方剂名称质量检查 (两级)
    返回 (hard_violations, warnings)
    """
    hard = []
    warns = []

    if not _table_exists(conn, "formulas"):
        return hard, warns
    cols = _get_columns(conn, "formulas")
    if "name" not in cols:
        return hard, warns

    for row in conn.execute("SELECT rowid, name FROM formulas"):
        rowid, name = row
        ns = name if isinstance(name, str) else ""

        # ========== HARD VIOLATIONS (导致 exit 1) ==========

        # 空名或纯空白 (TRIM 后)
        if not ns.strip():
            hard.append({
                "type":    VIOLATION_EMPTY,
                "table":   "formulas",
                "rowid":   rowid,
                "name":    ns,
                "message": "方剂名称为空或纯空白",
            })
            continue

        # blockquote 脏名: 以 > 开头
        if re.match(r"^\s*>\s*", ns):
            hard.append({
                "type":    VIOLATION_BLOCKQUOTE,
                "table":   "formulas",
                "rowid":   rowid,
                "name":    ns,
                "message": f"方剂名称为 blockquote 脏名: {ns!r}",
            })
            continue

        # 含控制字符
        if re.search(r"[\x00-\x1f]", ns):
            hard.append({
                "type":    VIOLATION_CONTROL_CHAR,
                "table":   "formulas",
                "rowid":   rowid,
                "name":    ns,
                "message": f"方剂名称含控制字符: {ns!r}",
            })
            continue

        # ========== WARNINGS (只报告，不导致失败) ==========

        # 长名含标点 (len > 8 且含中文/英文标点)
        if len(ns) > 8 and re.search(r"[。，.,；;：:！!？?]", ns):
            warns.append({
                "type":    VIOLATION_DESCRIPTIVE,
                "table":   "formulas",
                "rowid":   rowid,
                "name":    ns,
                "message": f"疑似描述性方名 (长名含标点): {ns!r}",
            })

        # 多方疑似: 按 、和与及 拆分后 >=2 段含汤丸散丹膏饮
        parts = re.split(r"[、和与及]", ns)
        suffix_count = sum(
            1 for p in parts if _FORMULA_SUFFIX_RE.search(p)
        )
        if suffix_count >= 2:
            warns.append({
                "type":    VIOLATION_MULTI_ENTITY,
                "table":   "formulas",
                "rowid":   rowid,
                "name":    ns,
                "message": f"疑似多方合并: {ns!r} ({suffix_count} 段含方剂后缀)",
            })

    return hard, warns


def check_duplicate_formulas(conn):
    """检查重名方剂 — 仅报告，不算失败"""
    dups = []
    if not _table_exists(conn, "formulas"):
        return dups
    cols = _get_columns(conn, "formulas")
    if "name" not in cols:
        return dups
    try:
        for row in conn.execute(
            "SELECT name, COUNT(*) AS cnt, GROUP_CONCAT(rowid) AS rowids "
            "FROM formulas "
            "WHERE name IS NOT NULL AND TRIM(name) != '' "
            "GROUP BY TRIM(name) "
            "HAVING cnt > 1"
        ):
            dups.append({
                "name":   row[0],
                "count":  row[1],
                "rowids": row[2],
            })
    except Exception as e:
        dups.append({"error": str(e)})
    return dups


# ================================================================
# 输出格式化
# ================================================================

def _format_human(report):
    """生成人类可读的审计摘要"""
    lines = []

    def a(s=""):
        lines.append(s)

    a("=" * 60)
    a("  tcm-db 数据质量审计报告")
    a("=" * 60)
    a(f"数据库: {report['db_path']}")
    a()

    def hdr(tag, label, items):
        if items:
            a(f"[{tag}] {label}: {len(items)} 个")
        else:
            a(f"[PASS] {label}")

    # 1. integrity
    hdr("FAIL", "PRAGMA integrity_check", report["integrity_errors"])
    for e in report["integrity_errors"]:
        a(f"    - {e}")

    # 2. foreign keys
    hdr("FAIL", "PRAGMA foreign_key_check", report["foreign_key_errors"])
    for e in report["foreign_key_errors"]:
        a(f"    - {e}")

    # 3. orphans
    hdr("FAIL", "关系孤儿", report["orphan_relations"])
    for o in report["orphan_relations"]:
        if "error" in o:
            a(f"    - {o['table']}.{o['column']}: 错误 - {o['error']}")
        else:
            a(f"    - {o['table']}.{o['column']}: rowid={o['rowid']}, "
              f"缺失 ID={o['missing_id']} (应在 {o['referenced_table']})")

    # 4. JSON
    hdr("FAIL", "JSON 字段验证", report["json_errors"])
    for e in report["json_errors"]:
        if "error" in e:
            a(f"    - {e['table']}.{e['column']}: {e['error']}")
        else:
            a(f"    - {e['table']}.{e['column']}: rowid={e['rowid']}, "
              f"值={e['value_preview']}")

    # 5. evidence
    hdr("FAIL", "Evidence 多态引用", report["evidence_errors"])
    for e in report["evidence_errors"]:
        if "error" in e:
            a(f"    - evidence({e['ref_type']}): {e['error']}")
        else:
            a(f"    - evidence({e['ref_type']}): rowid={e['rowid']}, "
              f"{e['entity_type']}#{e['missing_id']} 不在 {e['target_table']}")

    # 6. quarantine
    hdr("FAIL", "隔离区 JSON", report["quarantine_json_errors"])
    for e in report["quarantine_json_errors"]:
        if "error" in e:
            a(f"    - {e['error']}")
        else:
            a(f"    - rowid={e['rowid']}, 值={e['value_preview']}")

    # 7. name hard
    hdr("FAIL", "方剂名称 (Hard)", report["hard_violations"])
    for v in report["hard_violations"]:
        a(f"    - [{v['type']}] {v['message']}")

    # 8. name warnings
    if report["name_warnings"]:
        a(f"[WARN] 方剂名称 (Warning): {len(report['name_warnings'])} 个")
        for w in report["name_warnings"]:
            a(f"    - [{w['type']}] {w['message']}")
    else:
        a("[PASS] 方剂名称质量 (Warning)")

    # 9. duplicates
    if report["duplicate_formulas"]:
        a(f"[INFO] 重名方剂: {len(report['duplicate_formulas'])} 组")
        for d in report["duplicate_formulas"]:
            if "error" in d:
                a(f"    - 错误: {d['error']}")
            else:
                a(f"    - \"{d['name']}\" × {d['count']} "
                  f"(rowids: {d['rowids']})")
    else:
        a("[INFO] 无重名方剂")

    # fatal error
    if "fatal_error" in report:
        a(f"\n[FATAL] 审计异常: {report['fatal_error']}")

    a()
    a("=" * 60)

    # 总结
    has_data_err = any([
        report["integrity_errors"],
        report["foreign_key_errors"],
        report["orphan_relations"],
        report["json_errors"],
        report["evidence_errors"],
        report["quarantine_json_errors"],
    ])
    hard_cnt = len(report["hard_violations"])
    warn_cnt = len(report["name_warnings"])
    dup_cnt = len(report["duplicate_formulas"])

    if has_data_err or hard_cnt > 0 or "fatal_error" in report:
        a(f"结果: ❌ 审计失败 "
          f"(hard_violations={hard_cnt}, data_errors={has_data_err})")
    else:
        a(f"结果: ✅ 审计通过 "
          f"(warnings={warn_cnt}, duplicates={dup_cnt})")

    a("=" * 60)
    return "\n".join(lines)


# ================================================================
# 主审计流程
# ================================================================

def run_audit(db_path, output_json=False, report_path=None):
    """
    执行完整的只读审计。
    返回 (failed: bool, report: dict)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    report = {
        "db_path":               str(db_path),
        "integrity_errors":      [],
        "foreign_key_errors":    [],
        "orphan_relations":      [],
        "json_errors":           [],
        "evidence_errors":       [],
        "quarantine_json_errors": [],
        "hard_violations":       [],
        "name_warnings":         [],
        "duplicate_formulas":    [],
    }

    failed = False

    # 只读模式连接
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # 1) 完整性
        report["integrity_errors"] = check_integrity(conn)
        if report["integrity_errors"]:
            failed = True

        # 2) 外键
        report["foreign_key_errors"] = check_foreign_keys(conn)
        if report["foreign_key_errors"]:
            failed = True

        # 3) 关系孤儿
        report["orphan_relations"] = check_orphan_relations(conn)
        if report["orphan_relations"]:
            failed = True

        # 4) JSON 字段
        report["json_errors"] = check_json_fields(conn)
        if report["json_errors"]:
            failed = True

        # 5) evidence 多态引用
        report["evidence_errors"] = check_evidence_references(conn)
        if report["evidence_errors"]:
            failed = True

        # 6) 隔离区 JSON
        report["quarantine_json_errors"] = check_quarantine_json(conn)
        if report["quarantine_json_errors"]:
            failed = True

        # 7) 名称质量
        hv, wn = check_formula_name_quality(conn)
        report["hard_violations"] = hv
        report["name_warnings"] = wn
        if hv:
            failed = True

        # 8) 重名方剂 (仅报告)
        report["duplicate_formulas"] = check_duplicate_formulas(conn)

    except Exception as exc:
        print(f"审计异常: {exc}", file=sys.stderr)
        failed = True
        report["fatal_error"] = str(exc)
    finally:
        conn.close()

    # 输出
    if output_json:
        text = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        text = _format_human(report)
    print(text)

    # 写文件
    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(text, encoding="utf-8")
        print(f"\n报告已写入: {rp}", file=sys.stderr)

    return failed, report


# ================================================================
# self-test 子命令 (临时库，不碰正式)
# ================================================================

def run_self_test():
    """自检: 创建临时库 → 插样本 → 审计 → 验证"""
    print("=" * 60)
    print("  self-test: 创建临时数据库并运行审计")
    print("=" * 60)

    tmpdir = tempfile.mkdtemp(prefix="tcm_audit_test_")
    db_path = Path(tmpdir) / "test.db"

    # 建表 & 插样本（建全 JSON_FIELDS 涉及的表，避免 check_json_fields 对缺失表 raise）
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE formulas (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE clinical_cases (id INTEGER PRIMARY KEY, disease_tags TEXT)")
    conn.execute("CREATE TABLE symptoms (id INTEGER PRIMARY KEY, differential TEXT, required_questions TEXT)")
    conn.execute("CREATE TABLE ingestion_quarantine (id INTEGER PRIMARY KEY, raw_record_json TEXT)")
    conn.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, subject_type TEXT, subject_id INTEGER, object_type TEXT, object_id INTEGER)")

    samples = [
        # blockquote 脏名 (HARD)
        (1,  ">麻黄汤"),
        (2,  ">白虎汤"),
        (3,  ">桂枝、麻黄汤"),
        # 空名 (HARD)
        (4,  ""),
        (5,  "   "),
        (6,  None),
        # 含控制字符 (HARD)
        (7,  "麻黄\n汤"),
        (8,  "白虎\t汤"),
        # 正常方名 (不应误报)
        (9,  "麻黄汤"),
        (10, "桂枝汤"),
        (11, "小柴胡汤"),
        # 长名 (WARNING 或不触发)
        (12, "这是一张普通的方子"),
        # 重名 — 麻黄汤 ×2 (仅报告)
        (13, "麻黄汤"),
    ]

    conn.executemany("INSERT INTO formulas VALUES (?, ?)", samples)
    conn.commit()
    conn.close()

    print(f"临时数据库: {db_path}\n")

    # 跑审计
    failed, report = run_audit(db_path, output_json=False)

    print()
    print("=" * 60)
    print("  self-test 验证")
    print("=" * 60)

    all_ok = True

    # 1) blockquote 全命中 hard
    bq = [v for v in report["hard_violations"]
          if v["type"] == VIOLATION_BLOCKQUOTE]
    if len(bq) == 3:
        print("[PASS] blockquote 脏名: 3 个全部命中 hard")
    else:
        print(f"[FAIL] blockquote 脏名: 期望 3, 实际 {len(bq)}")
        all_ok = False

    # 2) 空名命中 hard
    em = [v for v in report["hard_violations"]
          if v["type"] == VIOLATION_EMPTY]
    if len(em) >= 2:
        print(f"[PASS] 空名: {len(em)} 个命中 hard")
    else:
        print(f"[FAIL] 空名: 期望 >=2, 实际 {len(em)}")
        all_ok = False

    # 3) 控制字符命中 hard
    cc = [v for v in report["hard_violations"]
          if v["type"] == VIOLATION_CONTROL_CHAR]
    if len(cc) == 2:
        print("[PASS] 控制字符: 2 个命中 hard")
    else:
        print(f"[FAIL] 控制字符: 期望 2, 实际 {len(cc)}")
        all_ok = False

    # 4) 正常方名不误报 (hard)
    normal_set = {"麻黄汤", "桂枝汤", "小柴胡汤"}
    fp_hard = [v for v in report["hard_violations"]
               if v["name"] in normal_set]
    if not fp_hard:
        print("[PASS] 正常方名: 未误报 (hard)")
    else:
        print(f"[FAIL] 正常方名误报 (hard): {fp_hard}")
        all_ok = False

    # 5) 正常方名不误报 (warning)
    fp_warn = [w for w in report["name_warnings"]
               if w["name"] in normal_set]
    if not fp_warn:
        print("[PASS] 正常方名: 未误报 (warning)")
    else:
        print(f"[FAIL] 正常方名误报 (warning): {fp_warn}")
        all_ok = False

    # 6) 重名方剂已报告
    dup_ok = any(
        d.get("name") == "麻黄汤" and d.get("count") == 2
        for d in report["duplicate_formulas"]
    )
    if dup_ok:
        print("[PASS] 重名方剂: 麻黄汤 ×2 已报告")
    else:
        print(f"[FAIL] 重名方剂: 未检测到 麻黄汤 ×2 "
              f"(got {report['duplicate_formulas']})")
        all_ok = False

    # 7) hard > 0 → exit 非 0
    if failed:
        print("[PASS] hard > 0 → exit 非 0")
    else:
        print("[FAIL] hard > 0 但 exit = 0")
        all_ok = False

    # 清理
    try:
        os.remove(str(db_path))
        os.rmdir(tmpdir)
    except OSError:
        pass

    print()
    if all_ok:
        print("✅ self-test 全部通过!")
        return 0
    else:
        print("❌ self-test 存在失败项!")
        return 1


# ================================================================
# CLI 入口
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="tcm-db 数据质量审计闸门 (只读, 绝不写库)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="数据库路径 (默认: 项目根/tcm_knowledge.db)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="以 JSON 格式输出",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="将报告写入指定文件路径",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "self-test",
        help="运行自检 (临时库, 不碰正式)",
    )

    args = parser.parse_args()

    # self-test 子命令
    if args.command == "self-test":
        sys.exit(run_self_test())

    # 默认审计
    db_path = args.db if args.db else get_default_db_path()

    try:
        failed, _ = run_audit(
            db_path,
            output_json=args.output_json,
            report_path=args.report,
        )
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
