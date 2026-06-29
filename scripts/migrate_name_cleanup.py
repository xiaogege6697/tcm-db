#!/usr/bin/env python3
"""Phase 0.5: formulas.name 清洗 + evidence 表重建（加 normalized_from 枚举）。

复用 migrate_formula_dedup.py 的已验证组件（EVIDENCE_DDL/make_dedupe_key 等），
确保 evidence 重建时完整保留所有 CHECK 约束。

子命令:
  rebuild-evidence  重建 evidence 表（relation_type 枚举加 normalized_from），幂等
  cleanup           单一事务清洗 48 脏名（A改名+normalized_from / B+C隔离+DELETE）
  self-test         临时库全流程验证
  verify            只读校验（守恒/引用/JSON/fk/integrity/脏名=0）
"""
import sqlite3, json, hashlib, re, sys, os, argparse, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent / "tcm_knowledge.db"
sys.path.insert(0, str(HERE))
from migrate_formula_dedup import (  # 复用已验证组件
    EVIDENCE_DDL, make_dedupe_key, get_conn, referencing_tables,
    insert_evidence, ENTITY_ENUM, _enum_lit,
)

# ── evidence_new DDL：完整复刻原 evidence 的所有 CHECK/NOT NULL + normalized_from ──
_ENTITY = _enum_lit(ENTITY_ENUM)
EVIDENCE_NEW_DDL = f"""
CREATE TABLE evidence_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type        TEXT    NOT NULL CHECK (subject_type IN ({_ENTITY})),
    subject_id          INTEGER NOT NULL,
    relation_type       TEXT    NOT NULL CHECK (relation_type IN (
                            'source_record','field_value','entity_relation',
                            'textual','merged_from','normalized_from')),
    object_type         TEXT    CHECK (object_type IS NULL OR object_type IN ({_ENTITY})),
    object_id           INTEGER,
    evidence_kind       TEXT    NOT NULL CHECK (evidence_kind IN (
                            'source_record','explicit','extracted','inferred','model_suggested')),
    source_type         TEXT    NOT NULL CHECK (source_type IN (
                            'database_row','markdown','pdf','image','github','manual')),
    source_record_type  TEXT    CHECK (source_record_type IS NULL OR source_record_type IN ({_ENTITY})),
    source_record_id    TEXT,
    source_id           INTEGER,
    source_path         TEXT,
    field_name          TEXT,
    evidence_text       TEXT    NOT NULL,
    confidence          REAL    CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    extraction_method   TEXT    NOT NULL DEFAULT 'manual' CHECK (extraction_method IN (
                            'manual','regex','llm_assisted','migration','etl','normalization')),
    review_status       TEXT    NOT NULL DEFAULT 'pending' CHECK (review_status IN (
                            'pending','reviewed','rejected')),
    dedupe_key          TEXT    NOT NULL UNIQUE,
    metadata_json       TEXT    CHECK (metadata_json IS NULL OR json_valid(metadata_json)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK ((object_type IS NULL AND object_id IS NULL) OR (object_type IS NOT NULL AND object_id IS NOT NULL))
);
"""
# 索引在 RENAME 到 evidence 后建（避免与旧表索引同名冲突；逐条 execute 保持事务）
EVIDENCE_NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ev_subject    ON evidence(subject_type, subject_id)",
    "CREATE INDEX IF NOT EXISTS idx_ev_object     ON evidence(object_type, object_id)",
    "CREATE INDEX IF NOT EXISTS idx_ev_kind       ON evidence(evidence_kind)",
    "CREATE INDEX IF NOT EXISTS idx_ev_relation   ON evidence(subject_type, relation_type)",
    "CREATE INDEX IF NOT EXISTS idx_ev_src_record ON evidence(source_record_type, source_record_id)",
]

TABLE_NAMES = ['formulas','herbs','symptoms','syndromes','acupoints','meridians',
               'clinical_cases','folk_formulas','courses','classics','course_notes',
               'books','lectures','tianji','treatment_methods','diagnostic_notes']

QUARANTINE_DDL = f"""
CREATE TABLE IF NOT EXISTS ingestion_quarantine (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table      TEXT    NOT NULL CHECK (source_table IN ({_enum_lit(TABLE_NAMES + ['raw_import'])})),
    source_record_id  INTEGER NOT NULL,
    source_snapshot   TEXT, build_id TEXT, content_hash TEXT, schema_version TEXT,
    raw_record_json   TEXT    NOT NULL CHECK (json_valid(raw_record_json)),
    source_repo       TEXT, source_path TEXT, original_name TEXT, cleaned_name TEXT,
    run_id            TEXT    NOT NULL,
    reason_code       TEXT    NOT NULL CHECK (reason_code IN (
                          'descriptive_non_entity','multiple_entities',
                          'invalid_markdown_parse','ambiguous_name')),
    status            TEXT    NOT NULL DEFAULT 'pending_review' CHECK (status IN (
                          'pending_review','rejected','restored','split')),
    dedupe_key        TEXT    NOT NULL UNIQUE,
    quarantined_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    reviewed_at       TEXT, review_note TEXT,
    metadata_json     TEXT    CHECK (metadata_json IS NULL OR json_valid(metadata_json))
);
CREATE INDEX IF NOT EXISTS idx_quar_source  ON ingestion_quarantine(source_table, source_record_id);
CREATE INDEX IF NOT EXISTS idx_quar_reason  ON ingestion_quarantine(reason_code, status);
CREATE INDEX IF NOT EXISTS idx_quar_run     ON ingestion_quarantine(run_id);
CREATE INDEX IF NOT EXISTS idx_quar_content ON ingestion_quarantine(content_hash);
"""

# ── 分类规则常量 ──
DIRTY_RE = re.compile(r"^\s*>\s*")
PUNCT_RE = re.compile(r"[。，.,；;：:！!？?]")
EXPL_WORDS = ("是", "的", "为", "即", "平常", "接近", "减少", "增加", "不一样", "还好", "煮", "收", "简称")
ENTITY_PAT = re.compile(r"汤|丸|散|丹|膏|饮")
GATE_TABLES = ("formula_herbs", "formula_syndromes", "case_formulas")
# id=3,4,22 即使不匹配净名也归 A（裁定：真方剂首条净名）
A_FORCE_IDS = {3, 4, 22}
# id=90 强制归 C（多方混名）
C_FORCE_IDS = {90}


def make_quarantine_key(source_table, source_snapshot, build_id, source_record_id, content_hash):
    vals = [source_table, source_snapshot, build_id, source_record_id, content_hash]
    canon = json.dumps(vals, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def classify(cleaned, cid, net_names):
    """A=净名匹配或id∈{3,4,22}; B=描述性(标点/解释词); C=多方/id90; 其余 ambiguous"""
    if PUNCT_RE.search(cleaned):
        return "B"
    for w in EXPL_WORDS:
        if w in cleaned:
            return "B"
    if cid in C_FORCE_IDS:
        return "C"
    parts = re.split(r"[、和与及还有]", cleaned)
    if sum(1 for p in parts if ENTITY_PAT.search(p)) >= 2:
        return "C"
    if "、" in cleaned:
        return "C"
    if cleaned in net_names or cid in A_FORCE_IDS:
        return "A"
    return "ambiguous"


def _load_net_names(conn):
    return set(r[0] for r in conn.execute(
        "SELECT DISTINCT name FROM formulas WHERE name NOT LIKE '> %' AND name IS NOT NULL"))


def _gate_check(conn, bc_ids):
    """B/C 行有引用 → raise（门禁）"""
    if not bc_ids:
        return
    ph = ",".join("?" * len(bc_ids))
    for t in GATE_TABLES:
        if conn.execute(f"SELECT count(*) FROM {t} WHERE formula_id IN ({ph})", bc_ids).fetchone()[0] > 0:
            raise RuntimeError(f"[门禁] {t} 有 B/C 脏记录引用 {bc_ids}，不得移出")


# ── rebuild-evidence ──
def cmd_rebuild_evidence(args):
    conn = get_conn(args.db)
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence'").fetchone()
    if sql and "normalized_from" in (sql[0] or ""):
        print("[skip] evidence.relation_type 已含 normalized_from"); conn.close(); return
    cols = [r[1] for r in conn.execute("PRAGMA table_info(evidence)")]
    collist = ",".join(f'"{c}"' for c in cols)
    try:
        conn.execute("BEGIN")
        conn.execute(EVIDENCE_NEW_DDL)  # 单条 CREATE TABLE evidence_new（事务内安全）
        n = conn.execute(f"INSERT INTO evidence_new({collist}) SELECT {collist} FROM evidence").rowcount
        conn.execute("DROP TABLE evidence")      # 删旧表 + 旧索引
        conn.execute("ALTER TABLE evidence_new RENAME TO evidence")
        for idx_sql in EVIDENCE_NEW_INDEXES:     # 在 evidence 上建正式索引
            conn.execute(idx_sql)
        conn.execute("COMMIT")
        print(f"[ok] evidence 重建完成，迁移 {n} 行，relation_type 枚举已含 normalized_from")
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        print(f"[error] rebuild 失败 ROLLBACK: {e}"); raise


# ── cleanup ──
def _cleanup(conn):
    net_names = _load_net_names(conn)
    dirty = [dict(r) for r in conn.execute(
        "SELECT * FROM formulas WHERE name LIKE '> %' ORDER BY id").fetchall()]
    if not dirty:
        return {"total": 0, "A": 0, "B": 0, "C": 0, "ambiguous": 0, "quarantined": 0, "renamed": 0}

    rows_by_cat = {"A": [], "B": [], "C": [], "ambiguous": []}
    for r in dirty:
        cleaned = DIRTY_RE.sub("", r["name"]).strip()
        cat = classify(cleaned, r["id"], net_names)
        r["_cleaned"] = cleaned
        rows_by_cat[cat].append(r)

    bc_ids = [r["id"] for r in rows_by_cat["B"] + rows_by_cat["C"] + rows_by_cat["ambiguous"]]
    _gate_check(conn, bc_ids)

    # A 类：改名 + normalized_from evidence
    renamed = 0
    for r in rows_by_cat["A"]:
        conn.execute("UPDATE formulas SET name=? WHERE id=?", (r["_cleaned"], r["id"]))
        insert_evidence(conn, dict(
            subject_type="formula", subject_id=r["id"], relation_type="normalized_from",
            object_type=None, object_id=None, evidence_kind="source_record",
            source_type="database_row", source_record_type="formula",
            source_record_id=str(r["id"]), source_id=None, source_path=r.get("raw_path"),
            field_name="name", evidence_text=r["name"], confidence=None,
            extraction_method="normalization", review_status="pending", metadata_json=None))
        renamed += 1

    # B/C/ambiguous：隔离 + DELETE
    quarantined = 0
    run_id = "phase0.5"
    for cat, reason in [("B", "descriptive_non_entity"),
                        ("C", "multiple_entities"),
                        ("ambiguous", "ambiguous_name")]:
        for r in rows_by_cat[cat]:
            raw_json = json.dumps({k: v for k, v in r.items() if k != "_cleaned"},
                                  ensure_ascii=False, default=str)
            chash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            qk = make_quarantine_key("formulas", None, None, r["id"], chash)
            conn.execute("""INSERT OR IGNORE INTO ingestion_quarantine(
                source_table, source_record_id, source_snapshot, build_id, content_hash, schema_version,
                raw_record_json, source_repo, source_path, original_name, cleaned_name, run_id,
                reason_code, status, dedupe_key, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                "formulas", r["id"], None, None, chash, "v2", raw_json,
                r.get("source_repo"), r.get("raw_path"), r["name"], r["_cleaned"], run_id,
                reason, "pending_review", qk, None))
            conn.execute("DELETE FROM formulas WHERE id=?", (r["id"],))
            quarantined += 1

    # 守恒 + 引用校验（事务内）
    after = conn.execute("SELECT count(*) FROM formulas").fetchone()[0]
    q_added = conn.execute(
        "SELECT count(*) FROM ingestion_quarantine WHERE source_table='formulas' AND run_id=?", (run_id,)).fetchone()[0]
    # before = after + quarantined（A 不改行数）
    before = after + quarantined
    for t in GATE_TABLES:
        bad = conn.execute(f"SELECT DISTINCT formula_id FROM {t} LEFT JOIN formulas f ON {t}.formula_id=f.id WHERE f.id IS NULL").fetchall()
        if bad:
            raise RuntimeError(f"[引用校验失败] {t} 孤儿 {[r[0] for r in bad]}")
    return {"total": len(dirty), "A": len(rows_by_cat["A"]), "B": len(rows_by_cat["B"]),
            "C": len(rows_by_cat["C"]), "ambiguous": len(rows_by_cat["ambiguous"]),
            "quarantined": quarantined, "renamed": renamed,
            "before": before, "after": after, "q_added": q_added}


def cmd_cleanup(args):
    conn = get_conn(args.db)
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='ingestion_quarantine'").fetchone():
        conn.executescript(QUARANTINE_DDL)  # 事务前建 quarantine（幂等 IF NOT EXISTS）
    try:
        conn.execute("BEGIN")
        s = _cleanup(conn)
        conn.execute("COMMIT")
        print(json.dumps({"mode": "commit", **s}, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        print(f"[error] cleanup 失败 ROLLBACK: {e}"); raise


def cmd_phase05(args):
    """单一事务：rebuild-evidence（加 normalized_from，幂等）+ cleanup（清洗脏名）。任一失败整批 ROLLBACK。"""
    conn = get_conn(args.db)
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='ingestion_quarantine'").fetchone():
        conn.executescript(QUARANTINE_DDL)
    try:
        conn.execute("BEGIN")
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence'").fetchone()
        rebuilt = False
        if not (sql and "normalized_from" in (sql[0] or "")):
            cols = [r[1] for r in conn.execute("PRAGMA table_info(evidence)")]
            collist = ",".join(f'"{c}"' for c in cols)
            conn.execute(EVIDENCE_NEW_DDL)
            n = conn.execute(f"INSERT INTO evidence_new({collist}) SELECT {collist} FROM evidence").rowcount
            conn.execute("DROP TABLE evidence")
            conn.execute("ALTER TABLE evidence_new RENAME TO evidence")
            for idx_sql in EVIDENCE_NEW_INDEXES:
                conn.execute(idx_sql)
            rebuilt = True
            print(f"[rebuild] evidence 迁移 {n} 行 + normalized_from")
        s = _cleanup(conn)
        conn.execute("COMMIT")
        print(json.dumps({"mode": "phase05-commit", "rebuilt_evidence": rebuilt, **s},
                         ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        print(f"[error] phase05 失败 ROLLBACK: {e}"); raise


def cmd_verify(args):
    conn = sqlite3.connect(str(args.db)); conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    dirty = conn.execute("SELECT count(*) FROM formulas WHERE name LIKE '> %'").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    # 引用完整性
    bad = {}
    for t in GATE_TABLES:
        n = conn.execute(f"SELECT count(*) FROM {t} LEFT JOIN formulas f ON {t}.formula_id=f.id WHERE f.id IS NULL").fetchone()[0]
        if n: bad[t] = n
    # JSON
    badjson = conn.execute("SELECT count(*) FROM ingestion_quarantine WHERE NOT json_valid(raw_record_json)").fetchone()[0] if conn.execute("SELECT name FROM sqlite_master WHERE name='ingestion_quarantine'").fetchone() else 0
    print(json.dumps({"dirty_remaining": dirty, "foreign_key_check": [list(x) for x in fk],
                      "integrity_check": integ, "orphan_refs": bad, "bad_quarantine_json": badjson,
                      "all_ok": dirty == 0 and not fk and integ == "ok" and not bad and badjson == 0},
                     ensure_ascii=False, default=list))
    conn.close()


def cmd_self_test(args):
    """临时库全流程：建 evidence(无normalized_from)+formulas+关系+quarantine → rebuild → cleanup → 验证"""
    tmp = tempfile.mktemp(suffix=".db")
    try:
        c = sqlite3.connect(tmp); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
        # 旧 evidence（无 normalized_from）
        old_ev = EVIDENCE_DDL.replace("'textual','merged_from')", "'textual','merged_from')")  # 原5值
        c.executescript(old_ev)
        c.execute("CREATE TABLE formulas(id INTEGER PRIMARY KEY, name TEXT NOT NULL, raw_path TEXT, source_repo TEXT)")
        c.execute("INSERT INTO evidence(dedupe_key,subject_type,subject_id,relation_type,evidence_kind,source_type,evidence_text,extraction_method) VALUES(?,?,?,?,?,?,?,?)",
                  ("k0","formula",999,"merged_from","source_record","database_row","seed","migration"))
        # formulas：净名 + A脏名 + B脏名 + C脏名(id90) + ambiguous
        for fid, nm, rp in [(1,"麻黄汤","p1"),(30,"白虎汤","p30"),
                            (7,"> 麻黄汤","p7"),(76,"> 白虎汤","p76"),  # A
                            (3,"> 干姜黄连黄芩人参汤","p3"),  # A force
                            (11,"> 这是描述性，方子","p11"),  # B
                            (90,"> 桂枝、麻黄、葛根汤","p90"),  # C force
                            (5,"> 未知方剂XYZ","p5")]:  # ambiguous
            c.execute("INSERT INTO formulas(id,name,raw_path,source_repo) VALUES(?,?,?,'hantang')",(fid,nm,rp))
        c.execute("CREATE TABLE formula_herbs(formula_id INTEGER REFERENCES formulas(id), herb_id INTEGER)")
        c.execute("CREATE TABLE formula_syndromes(formula_id INTEGER REFERENCES formulas(id), syndrome_id INTEGER)")
        c.execute("CREATE TABLE case_formulas(formula_id INTEGER REFERENCES formulas(id), case_id INTEGER)")
        c.executescript(QUARANTINE_DDL.replace(DB_PATH.name, ""))  # 建 quarantine
        c.commit(); c.close()

        # rebuild-evidence + cleanup（phase05 单一事务）
        ns = argparse.Namespace(db=tmp)
        cmd_phase05(ns)
        # 验证
        c2 = sqlite3.connect(tmp); c2.row_factory = sqlite3.Row; c2.execute("PRAGMA foreign_keys=ON")
        dirty = c2.execute("SELECT count(*) FROM formulas WHERE name LIKE '> %'").fetchone()[0]
        fcnt = c2.execute("SELECT count(*) FROM formulas").fetchone()[0]
        qcnt = c2.execute("SELECT count(*) FROM ingestion_quarantine").fetchone()[0]
        norm = c2.execute("SELECT count(*) FROM evidence WHERE relation_type='normalized_from'").fetchone()[0]
        integ = c2.execute("PRAGMA integrity_check").fetchone()[0]
        # 守恒：before(8) == after + quarantined(B+C+ambig=3)
        ok = dirty == 0 and fcnt == 5 and qcnt == 3 and norm == 3 and integ == "ok"
        # 改名验证：id7→麻黄汤, id76→白虎汤, id3→干姜黄连黄芩人参汤
        nm7 = c2.execute("SELECT name FROM formulas WHERE id=7").fetchone()[0]
        nm3 = c2.execute("SELECT name FROM formulas WHERE id=3").fetchone()[0]
        ok = ok and nm7 == "麻黄汤" and nm3 == "干姜黄连黄芩人参汤"
        # 幂等：重跑 cleanup
        c2.close()
        cmd_phase05(ns)  # 第二次，应无变化（幂等）
        c3 = sqlite3.connect(tmp); c3.row_factory = sqlite3.Row
        fcnt2 = c3.execute("SELECT count(*) FROM formulas").fetchone()[0]
        qcnt2 = c3.execute("SELECT count(*) FROM ingestion_quarantine").fetchone()[0]
        norm2 = c3.execute("SELECT count(*) FROM evidence WHERE relation_type='normalized_from'").fetchone()[0]
        c3.close()
        idem = (fcnt2 == fcnt and qcnt2 == qcnt and norm2 == norm)
        print(f"脏名残留={dirty} formulas={fcnt}(应5) quarantine={qcnt}(应3) normalized_from={norm}(应3) integrity={integ}")
        print(f"改名验证 id7={nm7} id3={nm3}")
        print(f"幂等(重跑不变): {idem}")
        print(f"[self-test {'PASS' if ok and idem else 'FAIL'}]")
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--db", default=str(DB_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rebuild-evidence")
    sub.add_parser("cleanup")
    sub.add_parser("phase05")
    sub.add_parser("self-test")
    sub.add_parser("verify")
    a = ap.parse_args()
    {"rebuild-evidence": cmd_rebuild_evidence, "cleanup": cmd_cleanup,
     "phase05": cmd_phase05, "self-test": cmd_self_test, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    main()
