#!/usr/bin/env python3
"""⚠️ 历史一次性脚本（2026-06-29 五组去重已执行完成，commit 255f4d6）。

未来方剂去重一律用 `scripts/migrate_formula_dedup.py migrate --name ...`——通用脚本已回填
evidence subject/object 迁移 + 删除前强制门禁（见 _migrate_formula_evidence / _assert_safe_to_delete /
_apply_group），覆盖了本脚本当初手工增强的场景。本脚本仅为当时一次性迁移逻辑留档，
**不得作为主入口**。

---

原五组去重单事务迁移（麻黄汤/小柴胡汤/抵当汤/旋覆代赭石汤/乌梅丸）。

按用户步骤5顺序（单事务，任一失败整批 ROLLBACK）：
  5.1 旧subject evidence → canonical（重算 dedupe_key，INSERT OR IGNORE 去重 + 删旧）
  5.2 写 merged_from + 字段冲突 evidence（复用 _write_merge_evidence）
  5.3 普通关系引用改指 canonical（INSERT OR IGNORE + DELETE 旧）
  5.4 补 canonical 空字段
  5.5 最后删旧 formula

相对 migrate_formula_dedup.cmd_migrate 的增强：迁移旧 id 作为 subject 的 normalized_from
evidence（否则删旧 formula 后 subject_id 悬空，触发 audit「Evidence 多态引用」hard fail）。
复用 migrate_formula_dedup 的工具函数，不动原脚本。

用法：
  python3 scripts/migrate_batch5.py            # dry-run（ROLLBACK，不写库）
  python3 scripts/migrate_batch5.py --apply    # 正式（COMMIT）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import migrate_formula_dedup as M

# (方名, 预期 canonical_id) —— canonical 必须在组内且不在删除列表
GROUPS = [('麻黄汤', 214), ('小柴胡汤', 230), ('抵当汤', 250),
          ('旋覆代赭石汤', 65), ('乌梅丸', 265)]
APPLY = '--apply' in sys.argv


def migrate_subject_evidence(conn, old_id, canon_id):
    """旧 id 作为 subject 的 evidence → subject_id 改 canonical，重算 dedupe_key。
    先删旧再 INSERT OR IGNORE 新（去重）；返回 (保留数, 去重数, 明细)。"""
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM evidence WHERE subject_type='formula' AND subject_id=?",
        (old_id,)).fetchall()]
    kept = dedup = 0
    detail = []
    for ev in rows:
        old_dedupe = ev['dedupe_key']
        new_ev = {k: v for k, v in ev.items() if k not in ('id', 'dedupe_key', 'created_at')}
        new_ev['subject_id'] = canon_id
        new_dedupe = M.make_dedupe_key(new_ev)
        new_ev['dedupe_key'] = new_dedupe
        conn.execute("DELETE FROM evidence WHERE dedupe_key=?", (old_dedupe,))   # 先删旧
        existed = conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE dedupe_key=?", (new_dedupe,)).fetchone()[0] > 0
        M.insert_evidence(conn, new_ev)                                          # INSERT OR IGNORE
        if existed:
            dedup += 1
        else:
            kept += 1
        detail.append({
            'relation_type': ev['relation_type'],
            'source_record_id': ev.get('source_record_id'),
            'source_path': ev.get('source_path'),
            'deduped_against_canonical': existed,
        })
    return kept, dedup, detail


def evidence_formula_set(conn):
    """subject_type='formula' 的 evidence 三元组指纹 (subject_id, relation_type, source_record_id)"""
    return sorted(
        (r[0], r[1], r[2]) for r in conn.execute(
            "SELECT subject_id, relation_type, source_record_id "
            "FROM evidence WHERE subject_type='formula' ORDER BY 1,2,3"))


def main():
    conn = M.get_conn(M.DB_PATH)
    # 规划 + canonical 校验（事务前，只读）
    plans = []
    for name, expected in GROUPS:
        p = M._plan_group(conn, name)
        if p is None:
            print(json.dumps({'error': f'{name} 无重复组'}, ensure_ascii=False)); conn.close(); return 1
        if p['canon_id'] != expected:
            print(json.dumps({'error': f"{name} canonical={p['canon_id']} != 预期 {expected}"},
                             ensure_ascii=False)); conn.close(); return 1
        plans.append(p)
    old_to_canon = {nid: p['canon_id'] for p in plans for nid in p['non_canon']}

    ev_before = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    before_set = evidence_formula_set(conn)

    try:
        conn.execute("BEGIN")
        # 5.1 迁移旧 subject evidence
        subj_log = []
        for old_id, canon_id in sorted(old_to_canon.items()):
            k, d, detail = migrate_subject_evidence(conn, old_id, canon_id)
            subj_log.append({'old_id': old_id, 'canon_id': canon_id,
                             'kept': k, 'deduped': d, 'evidence': detail})
        # 5.2 merged_from + 字段冲突；5.3 普通关系；5.4 补 canonical
        group_log = []
        for p in plans:
            updates = M._write_merge_evidence(conn, p['rows_d'], p['canon'])
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
                    f'DELETE FROM "{ref["table"]}" WHERE "{ref["column"]}" '
                    f'IN ({M._in_ph(len(p["non_canon"]))})', p['non_canon'])
            if updates:
                set_clause = ','.join(f'"{k}"=?' for k in updates)
                conn.execute(f'UPDATE formulas SET {set_clause} WHERE id=?',
                             list(updates.values()) + [p['canon_id']])
            group_log.append({'name': p['name'], 'canon_id': p['canon_id'],
                              'non_canon': p['non_canon'], 'field_updates': updates,
                              'old_refs_detected': p['old_refs']})
        # 5.5 最后删旧 formula
        all_old = sorted(old_to_canon.keys())
        conn.execute(f'DELETE FROM formulas WHERE id IN ({M._in_ph(len(all_old))})', all_old)

        # 事务内对账快照
        ev_after = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        formulas_after = conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0]
        after_set = evidence_formula_set(conn)
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        old_refs_after = {}
        for p in plans:
            for ref in p['refs']:
                n = conn.execute(
                    f'SELECT COUNT(*) FROM "{ref["table"]}" WHERE "{ref["column"]}" '
                    f'IN ({M._in_ph(len(p["non_canon"]))})', p['non_canon']).fetchone()[0]
                if n:
                    old_refs_after[f"{p['name']}@{ref['table']}"] = n

        snapshot = {
            'mode': 'commit' if APPLY else 'dry-run(已ROLLBACK,未写库)',
            'evidence_before': ev_before, 'evidence_after': ev_after,
            'formulas_before': formulas_after + len(all_old), 'formulas_after': formulas_after,
            'subject_evidence_migration': subj_log,
            'groups': group_log,
            'old_refs_after_delete': old_refs_after,
            'foreign_key_check': [list(x) for x in fk],
            'integrity_check': integ,
        }
        if APPLY:
            conn.execute("COMMIT")
        else:
            conn.execute("ROLLBACK")
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=list))
        # evidence 集合差异（诊断用）
        print("\n--- evidence(formula subject) 迁移前后集合差异 ---")
        sb, sa = set(before_set), set(after_set)
        print("新增:", sorted(sa - sb))
        print("消失:", sorted(sb - sa))
        conn.close()
        return 0
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        print(f"❌ 失败，整批已 ROLLBACK：{e}", file=sys.stderr)
        raise


if __name__ == '__main__':
    sys.exit(main())
