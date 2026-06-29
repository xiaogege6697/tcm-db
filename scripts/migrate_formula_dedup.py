#!/usr/bin/env python3
"""formula 去重迁移工具（含 evidence 表）。纯标准库。

子命令:
  self-test                临时库验证 DDL / UNIQUE / INSERT OR IGNORE / UPSERT / NULL≠'' / metadata CHECK / object 配对 CHECK
  create-evidence          正式库建 evidence 表 + 索引
  migrate --name X         迁移某方剂组（事务：先写 evidence → 迁关系 → 删冗余 → 对账；失败 ROLLBACK）
  idempotent --name X      重跑迁移，验证 evidence 行数不变
  audit-evidence           多态引用孤儿审计
"""
import sqlite3, json, hashlib, sys, argparse, tempfile, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent / "tcm_knowledge.db"

ENTITY_ENUM = ['formula', 'herb', 'symptom', 'syndrome', 'acupoint', 'meridian',
               'clinical_case', 'folk_formula', 'course', 'classic', 'course_note',
               'book', 'lecture', 'tianji', 'treatment_method', 'diagnostic_note']
TYPE_TO_TABLE = {
    'formula': 'formulas', 'herb': 'herbs', 'symptom': 'symptoms', 'syndrome': 'syndromes',
    'acupoint': 'acupoints', 'meridian': 'meridians', 'clinical_case': 'clinical_cases',
    'folk_formula': 'folk_formulas', 'course': 'courses', 'classic': 'classics',
    'course_note': 'course_notes', 'book': 'books', 'lecture': 'lectures', 'tianji': 'tianji',
    'treatment_method': 'treatment_methods', 'diagnostic_note': 'diagnostic_notes',
}


def _enum_lit(vals):
    return ",".join(f"'{v}'" for v in vals)


EVIDENCE_DDL = f"""
CREATE TABLE IF NOT EXISTS evidence (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type        TEXT    NOT NULL CHECK (subject_type IN ({_enum_lit(ENTITY_ENUM)})),
    subject_id          INTEGER NOT NULL,
    relation_type       TEXT    NOT NULL CHECK (relation_type IN ('source_record','field_value','entity_relation','textual','merged_from')),
    object_type         TEXT    CHECK (object_type IS NULL OR object_type IN ({_enum_lit(ENTITY_ENUM)})),
    object_id           INTEGER,
    evidence_kind       TEXT    NOT NULL CHECK (evidence_kind IN ('source_record','explicit','extracted','inferred','model_suggested')),
    source_type         TEXT    NOT NULL CHECK (source_type IN ('database_row','markdown','pdf','image','github','manual')),
    source_record_type  TEXT    CHECK (source_record_type IS NULL OR source_record_type IN ({_enum_lit(ENTITY_ENUM)})),
    source_record_id    TEXT,
    source_id           INTEGER,
    source_path         TEXT,
    field_name          TEXT,
    evidence_text       TEXT    NOT NULL,
    confidence          REAL    CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    extraction_method   TEXT    NOT NULL DEFAULT 'manual' CHECK (extraction_method IN ('manual','regex','llm_assisted','migration','etl')),
    review_status       TEXT    NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','reviewed','rejected')),
    dedupe_key          TEXT    NOT NULL UNIQUE,
    metadata_json       TEXT    CHECK (metadata_json IS NULL OR json_valid(metadata_json)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK ((object_type IS NULL AND object_id IS NULL) OR (object_type IS NOT NULL AND object_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_ev_subject    ON evidence(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_ev_object     ON evidence(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_ev_kind       ON evidence(evidence_kind);
CREATE INDEX IF NOT EXISTS idx_ev_relation   ON evidence(subject_type, relation_type);
CREATE INDEX IF NOT EXISTS idx_ev_src_record ON evidence(source_record_type, source_record_id);
"""

# dedupe_key 身份字段（不含 confidence/review_status/metadata/created_at）
DEDUPE_FIELDS = ['subject_type', 'subject_id', 'relation_type', 'object_type', 'object_id',
                 'evidence_kind', 'source_type', 'source_record_type', 'source_record_id',
                 'field_name', 'source_path', 'source_id']


def make_dedupe_key(rec):
    """规范 JSON 数组 → SHA-256。保留 None/''/int/str 类型差异，NULL 与 '' 不合并。"""
    values = [rec.get(f) for f in DEDUPE_FIELDS]
    canon = json.dumps(values, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def insert_evidence(conn, rec):
    """INSERT OR IGNORE（dedupe_key 冲突则忽略），幂等。"""
    rec = dict(rec)
    rec['dedupe_key'] = make_dedupe_key(rec)
    cols = list(rec.keys())
    placeholders = ','.join('?' * len(cols))
    collist = ','.join(f'"{c}"' for c in cols)
    conn.execute(f"INSERT OR IGNORE INTO evidence ({collist}) VALUES ({placeholders})",
                 [rec[c] for c in cols])


def get_conn(path):
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def referencing_tables(conn):
    """动态发现引用 formulas.id 的 {table, column}"""
    refs = []
    for (t,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")'):
            if fk[2] == 'formulas':
                refs.append({'table': t, 'column': fk[3]})
    return refs


def _in_ph(n):
    return ','.join('?' * n)


def pick_canonical(rows_d):
    rank = {'nihaixia': 0, 'hantang': 1}
    def full(r):
        return sum(1 for k, v in r.items()
                   if k not in ('id', 'raw_path', 'source_repo', 'name') and v not in (None, ''))
    c = [x for x in rows_d if (x.get('six_channel') or '').strip() and x.get('source_repo') == 'nihaixia']
    if c:
        return min(c, key=lambda x: x['id'])
    c = [x for x in rows_d if (x.get('six_channel') or '').strip()]
    if c:
        return min(c, key=lambda x: x['id'])
    fb = max(full(x) for x in rows_d)
    tie = [x for x in rows_d if full(x) == fb]
    tie.sort(key=lambda x: (rank.get(x.get('source_repo'), 9), x['id']))
    return tie[0]


# ============================================================
# 子命令：self-test
# ============================================================
def cmd_self_test(args):
    tmp = tempfile.mktemp(suffix='.db')
    try:
        conn = sqlite3.connect(tmp)
        conn.executescript(EVIDENCE_DDL)

        base = dict(subject_type='formula', subject_id=209, relation_type='merged_from',
                    object_type=None, object_id=None, evidence_kind='source_record',
                    source_type='database_row', source_record_type='formula',
                    source_record_id='8', source_id=None, source_path='p.md',
                    field_name=None, evidence_text='t', confidence=None,
                    extraction_method='migration', review_status='pending',
                    metadata_json='{"k":1}')

        # 1. 正常插入
        insert_evidence(conn, base)
        n1 = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
        assert n1 == 1, f"插入后应 1 条，实 {n1}"

        # 2. 裸 INSERT 重复 dedupe_key → IntegrityError(UNIQUE)
        try:
            conn.execute(
                "INSERT INTO evidence (dedupe_key,subject_type,subject_id,relation_type,"
                "evidence_kind,source_type,evidence_text) VALUES (?,?,?,?,?,?,?)",
                (make_dedupe_key(base), 'formula', 209, 'merged_from',
                 'source_record', 'database_row', 't'))
            assert False, "裸 INSERT 重复应抛 IntegrityError"
        except sqlite3.IntegrityError:
            pass

        # 3. INSERT OR IGNORE 重复 → 不增
        insert_evidence(conn, base)
        n2 = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
        assert n2 == n1, f"INSERT OR IGNORE 后不应增，{n2}"

        # 4. UPSERT 更新 confidence/review_status → 行数不变、值更新
        conn.execute(
            "INSERT INTO evidence (dedupe_key,subject_type,subject_id,relation_type,"
            "evidence_kind,source_type,evidence_text,confidence,review_status) "
            "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO UPDATE SET "
            "confidence=excluded.confidence, review_status=excluded.review_status",
            (make_dedupe_key(base), 'formula', 209, 'merged_from', 'source_record',
             'database_row', 't', 0.5, 'reviewed'))
        n3 = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
        assert n3 == n1, f"UPSERT 不应增行，{n3}"
        row = conn.execute("SELECT confidence,review_status FROM evidence WHERE subject_id=209").fetchone()
        assert row[0] == 0.5 and row[1] == 'reviewed', f"UPSERT 未更新 {row}"

        # 5. NULL vs '' 类型差异 → 不同 dedupe_key，都可插入
        r_null = dict(base); r_null['subject_id'] = 210; r_null['source_record_id'] = None
        r_empty = dict(base); r_empty['subject_id'] = 211; r_empty['source_record_id'] = ''
        insert_evidence(conn, r_null)
        insert_evidence(conn, r_empty)
        assert make_dedupe_key(r_null) != make_dedupe_key(r_empty), "NULL 与 '' 的 dedupe_key 不应相同"

        # 6. 裸 INSERT 非法 JSON metadata → IntegrityError(CHECK json_valid)
        try:
            conn.execute(
                "INSERT INTO evidence (dedupe_key,subject_type,subject_id,relation_type,"
                "evidence_kind,source_type,evidence_text,metadata_json) VALUES (?,?,?,?,?,?,?,?)",
                ('k_bad', 'formula', 212, 'merged_from', 'source_record', 'database_row', 't', '{bad'))
            assert False, "非法 JSON 应被 CHECK 拒"
        except sqlite3.IntegrityError:
            pass

        # 7. 裸 INSERT object_type 非空 + object_id NULL → IntegrityError(配对 CHECK)
        try:
            conn.execute(
                "INSERT INTO evidence (dedupe_key,subject_type,subject_id,relation_type,"
                "object_type,object_id,evidence_kind,source_type,evidence_text) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ('k_obj', 'formula', 213, 'entity_relation', 'syndrome', None,
                 'explicit', 'database_row', 't'))
            assert False, "object 配对违反应被 CHECK 拒"
        except sqlite3.IntegrityError:
            pass

        conn.close()
        print("✅ self-test 全部通过：")
        print("   DDL 建表 / UNIQUE 挡重复 / INSERT OR IGNORE 幂等 / UPSERT 不增行 /")
        print("   NULL≠'' 类型差异 / metadata json_valid CHECK / object 配对 CHECK")
        return 0
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ============================================================
# 子命令：create-evidence
# ============================================================
def cmd_create_evidence(args):
    conn = get_conn(DB_PATH)
    conn.executescript(EVIDENCE_DDL)
    conn.commit()
    n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='evidence'").fetchone()[0]
    idx = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ev_%'").fetchone()[0]
    conn.close()
    print(f"✅ evidence 表已建（存在={n}），索引 {idx} 个")
    return 0


# ============================================================
# 子命令：migrate --name X
# ============================================================
MEDICAL_FIELDS = {'composition', 'dosage', 'indication', 'six_channel', 'syndrome',
                  'differentiation', 'contraindication', 'alias', 'commentary'}
MERGE_FIELDS = ['source_book', 'chapter', 'alias', 'composition', 'dosage', 'indication',
                'six_channel', 'syndrome', 'differentiation', 'contraindication',
                'commentary', 'lesson_ref']


def _field_conflict_evidence(canon_id, field, value, src_row, canon_val):
    is_medical = field in MEDICAL_FIELDS
    return dict(
        subject_type='formula', subject_id=canon_id, relation_type='field_value',
        object_type=None, object_id=None, evidence_kind='source_record',
        source_type='database_row', source_record_type='formula',
        source_record_id=str(src_row['id']), source_id=None,
        source_path=src_row.get('raw_path'), field_name=field,
        evidence_text=value, confidence=None, extraction_method='migration',
        review_status='pending',
        metadata_json=json.dumps({
            'canonical_value': canon_val,
            'original_source_repo': src_row.get('source_repo'),
            'is_medical_field': is_medical,
            'reason': '合并去重保留的非canonical字段值；' + ('医学字段需人工裁定' if is_medical else '该字段不参与推理')},
            ensure_ascii=False))


def _compute_field_merges(rows_d, canon):
    """通用字段合并（确定性规则）：
    - canonical 非空 + 其他不同非空 → 保留 canonical，其他值写 evidence
    - canonical 空 + 其他一致非空 → canonical 补该值
    - canonical 空 + 其他冲突 → canonical 留空，所有非空值写 evidence
    返回 (updates_dict, evidences_list)。"""
    canon_id = canon['id']
    updates, evidences = {}, []
    for f in MERGE_FIELDS:
        c_val = (canon.get(f) or '').strip() or None
        others = {}
        for r in rows_d:
            if r['id'] == canon_id:
                continue
            v = (r.get(f) or '').strip() or None
            if v:
                others.setdefault(v, []).append(r)
        if c_val:
            for v, rs in others.items():
                if v != c_val:
                    for r in rs:
                        evidences.append(_field_conflict_evidence(canon_id, f, v, r, c_val))
        else:
            if not others:
                continue
            if len(others) == 1:
                updates[f] = next(iter(others.keys()))
            else:
                for v, rs in others.items():
                    for r in rs:
                        evidences.append(_field_conflict_evidence(canon_id, f, v, r, None))
    return updates, evidences


def _write_merge_evidence(conn, rows_d, canon):
    """写字段合并/冲突 evidence + 旧 id 映射 evidence；返回 canonical 字段补值 dict。
    chapter 等字段按确定性规则：一致→补 canonical；冲突→canonical 留空 + 全写 evidence。
    （桂枝汤已人工确认 chapter=上篇并迁移完毕，通用规则不影响已迁移数据。）"""
    canon_id = canon['id']
    name = canon['name']
    updates, field_evs = _compute_field_merges(rows_d, canon)
    for ev in field_evs:
        insert_evidence(conn, ev)
    for r in rows_d:
        if r['id'] == canon_id:
            continue
        insert_evidence(conn, dict(
            subject_type='formula', subject_id=canon_id, relation_type='merged_from',
            object_type=None, object_id=None, evidence_kind='source_record',
            source_type='database_row', source_record_type='formula',
            source_record_id=str(r['id']), source_id=None,
            source_path=r.get('raw_path'), field_name=None,
            evidence_text=f'原formula_id={r["id"]}已合并入canonical {canon_id}',
            confidence=None, extraction_method='migration', review_status='pending',
            metadata_json=json.dumps({
                'original_name': name, 'duplicate_of': canon_id,
                'original_source_repo': r.get('source_repo'),
                'original_raw_path': r.get('raw_path'),
                'original_chapter': (r.get('chapter') or '').strip() or None},
                ensure_ascii=False)))
    return updates


def _plan_group(conn, name):
    """计算单组迁移计划（只读）。返回 plan 或 None。"""
    rows_d = [dict(r) for r in conn.execute(
        "SELECT * FROM formulas WHERE name=? ORDER BY id", (name,)).fetchall()]
    if len(rows_d) < 2:
        return None
    ids = [r['id'] for r in rows_d]
    canon = pick_canonical(rows_d)
    canon_id = canon['id']
    non_canon = [i for i in ids if i != canon_id]
    refs = referencing_tables(conn)
    updates, field_evs = _compute_field_merges(rows_d, canon)
    before = {
        'formulas_rows': len(rows_d),
        'distinct_herbs': sorted(r[0] for r in conn.execute(
            f"SELECT DISTINCT herb_id FROM formula_herbs WHERE formula_id IN ({_in_ph(len(ids))})", ids).fetchall()),
        'distinct_cases': sorted(r[0] for r in conn.execute(
            f"SELECT DISTINCT case_id FROM case_formulas WHERE formula_id IN ({_in_ph(len(ids))})", ids).fetchall()),
    }
    # 动态检查旧 id 引用
    old_refs = {}
    for ref in refs:
        for nid in non_canon:
            cnt = conn.execute(
                f'SELECT count(*) FROM "{ref["table"]}" WHERE "{ref["column"]}"=?', (nid,)).fetchone()[0]
            if cnt:
                old_refs.setdefault(ref['table'], {})[str(nid)] = cnt
    return {'name': name, 'rows_d': rows_d, 'ids': ids, 'canon': canon, 'canon_id': canon_id,
            'non_canon': non_canon, 'refs': refs, 'updates': updates,
            'field_conflict_evidence': len(field_evs), 'before': before, 'old_refs': old_refs}


def _apply_group(conn, p):
    """执行单组迁移（事务内）。dry-run 与正式同代码路径。"""
    updates = _write_merge_evidence(conn, p['rows_d'], p['canon'])
    for ref in p['refs']:
        cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{ref["table"]}")')]
        other = [c for c in cols if c != ref['column']]
        col_list = ','.join(f'"{c}"' for c in other)
        for nid in p['non_canon']:
            conn.execute(
                f'INSERT OR IGNORE INTO "{ref["table"]}" ("{ref["column"]}",{col_list}) '
                f'SELECT ?,{col_list} FROM "{ref["table"]}" WHERE "{ref["column"]}"=?',
                (p['canon_id'], nid))
    for ref in p['refs']:
        conn.execute(
            f'DELETE FROM "{ref["table"]}" WHERE "{ref["column"]}" IN ({_in_ph(len(p["non_canon"]))})',
            p['non_canon'])
    conn.execute(
        f'DELETE FROM formulas WHERE id IN ({_in_ph(len(p["non_canon"]))})', p['non_canon'])
    if updates:
        set_clause = ','.join(f'"{k}"=?' for k in updates)
        conn.execute(f'UPDATE formulas SET {set_clause} WHERE id=?',
                     list(updates.values()) + [p['canon_id']])


def cmd_migrate(args):
    """批量迁移（多组一个事务，整批 ROLLBACK）。
    dry-run 与正式同代码路径：都执行 _apply_group，仅最后 ROLLBACK vs COMMIT 不同。"""
    names = args.name
    dry = args.dry_run
    conn = get_conn(DB_PATH)
    plans = []
    for name in names:
        p = _plan_group(conn, name)
        if p is None:
            print(json.dumps({'name': name, 'skip': '无重复'}, ensure_ascii=False))
        else:
            plans.append(p)
    if not plans:
        conn.close(); return 0

    # 一个事务执行所有组（dry-run 与正式同路径）
    try:
        conn.execute("BEGIN")
        for p in plans:
            _apply_group(conn, p)
        if dry:
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        print(f"❌ {'dry-run' if dry else '迁移'}失败，整批已 ROLLBACK：{e}")
        raise

    if dry:
        out = {'mode': 'dry-run(已ROLLBACK,未写库)', 'groups': [{
            'name': p['name'], 'canonical_id': p['canon_id'], 'duplicate_ids': p['ids'],
            'non_canon_to_delete': p['non_canon'], 'before': p['before'],
            'old_refs_detected': p['old_refs'], 'canonical_field_updates': p['updates'],
            'field_conflict_evidence_to_write': p['field_conflict_evidence'],
        } for p in plans]}
        print(json.dumps(out, ensure_ascii=False, indent=2, default=list))
        conn.close(); return 0

    # 正式：全组对账
    ev_before_total = 5  # 桂枝汤已有5条；这里用差值
    results, all_ok = [], True
    for p in plans:
        after = {
            'formulas_rows': conn.execute("SELECT count(*) FROM formulas WHERE name=?", (p['name'],)).fetchone()[0],
            'distinct_herbs': sorted(r[0] for r in conn.execute(
                "SELECT DISTINCT herb_id FROM formula_herbs WHERE formula_id=?", (p['canon_id'],)).fetchall()),
            'distinct_cases': sorted(r[0] for r in conn.execute(
                "SELECT DISTINCT case_id FROM case_formulas WHERE formula_id=?", (p['canon_id'],)).fetchall()),
            'old_id_refs': sum(
                conn.execute(f'SELECT count(*) FROM "{ref["table"]}" WHERE "{ref["column"]}" IN ({_in_ph(len(p["non_canon"]))})',
                             p['non_canon']).fetchone()[0] for ref in p['refs']),
        }
        ok = (after['formulas_rows'] == 1
              and after['distinct_herbs'] == p['before']['distinct_herbs']
              and after['distinct_cases'] == p['before']['distinct_cases']
              and after['old_id_refs'] == 0)
        all_ok = all_ok and ok
        results.append({'name': p['name'], 'canonical_id': p['canon_id'],
                        'before': p['before'], 'after': after, 'reconcile_ok': ok})
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    ev_total = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
    conn.close()
    print(json.dumps({
        'mode': 'commit', 'all_reconcile_ok': all_ok and not fk and integ == 'ok',
        'evidence_total': ev_total, 'foreign_key_check': [list(x) for x in fk],
        'integrity_check': integ, 'groups': results,
    }, ensure_ascii=False, indent=2, default=list))
    return 0 if all_ok and not fk and integ == 'ok' else 1


def cmd_idempotent(args):
    """幂等测试：对当前 canonical 的现有 evidence 重新 INSERT OR IGNORE，验证行数不变。
    （不依赖"组有重复"——迁移后已无重复，直接重插现有 evidence 测 UNIQUE+IGNORE 幂等。）"""
    conn = get_conn(DB_PATH)
    name = args.name
    row = conn.execute("SELECT id FROM formulas WHERE name=? ORDER BY id LIMIT 1", (name,)).fetchone()
    if not row:
        print(json.dumps({'name': name, 'error': 'not found'}, ensure_ascii=False)); return 1
    cid = row[0]
    ev_rows = [dict(r) for r in conn.execute(
        "SELECT * FROM evidence WHERE subject_type='formula' AND subject_id=?", (cid,)).fetchall()]
    before = len(ev_rows)
    for r in ev_rows:
        r.pop('id', None); r.pop('created_at', None); r.pop('dedupe_key', None)
        insert_evidence(conn, r)   # INSERT OR IGNORE，dedupe_key 相同 → 忽略
    conn.commit()
    after = conn.execute(
        "SELECT count(*) FROM evidence WHERE subject_type='formula' AND subject_id=?", (cid,)).fetchone()[0]
    conn.close()
    ok = before == after
    print(json.dumps({'name': name, 'canonical_id': cid,
                      'evidence_before_rerun': before, 'evidence_after_rerun': after,
                      'idempotent': ok}, ensure_ascii=False))
    return 0 if ok else 1


def cmd_audit_evidence(args):
    """多态引用审计。
    - subject_id / object_id：必须存在（指向当前实体），缺失=真孤儿。
    - source_record_id：语义为"来源记录"，可能是已合并/删除的历史 id（merged_from 等场景），
      不强制当前存在；不存在记 historical_source（正常），不计入 orphan。"""
    conn = get_conn(DB_PATH)
    issues = []
    historical = []
    for row in conn.execute(
        "SELECT id,subject_type,subject_id,object_type,object_id,"
        "source_record_type,source_record_id,source_type FROM evidence"):
        eid, st, sid, ot, oid, srt, srid, soty = row
        # subject 必须存在
        t = TYPE_TO_TABLE.get(st)
        if t and not conn.execute(f'SELECT 1 FROM "{t}" WHERE id=?', (sid,)).fetchone():
            issues.append(['orphan_subject', eid, st, sid])
        # object（非空时）必须存在
        if ot is not None and oid is not None:
            t = TYPE_TO_TABLE.get(ot)
            if t and not conn.execute(f'SELECT 1 FROM "{t}" WHERE id=?', (oid,)).fetchone():
                issues.append(['orphan_object', eid, ot, oid])
        # source_record_id：来源记录，可能是历史已删，不计 orphan
        if srt and soty == 'database_row' and srid:
            t = TYPE_TO_TABLE.get(srt)
            if t and not conn.execute(f'SELECT 1 FROM "{t}" WHERE id=?', (srid,)).fetchone():
                historical.append([eid, srt, srid])
    conn.close()
    print(json.dumps({
        'orphan_count': len(issues), 'issues': issues[:20],
        'historical_source_count': len(historical),
        'note': 'historical_source=来源记录已合并/删除(如merged_from),属正常,非孤儿',
    }, ensure_ascii=False, default=list))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('self-test')
    sub.add_parser('create-evidence')
    p_m = sub.add_parser('migrate')
    p_m.add_argument('--name', action='append', required=True, help='可重复：--name A --name B')
    p_m.add_argument('--dry-run', action='store_true', help='同代码路径但最后 ROLLBACK，不写库')
    p_i = sub.add_parser('idempotent'); p_i.add_argument('--name', required=True)
    sub.add_parser('audit-evidence')
    args = ap.parse_args()
    return {'self-test': cmd_self_test, 'create-evidence': cmd_create_evidence,
            'migrate': cmd_migrate, 'idempotent': cmd_idempotent,
            'audit-evidence': cmd_audit_evidence}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
