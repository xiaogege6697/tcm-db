#!/usr/bin/env python3
"""只读：生成 formulas.name 脏数据（'> ' 前缀）的 48 行分类清单 + 引用检查。
分类（按裁定）：
  A_clean_match      去前缀后单一名 + 与现有净名精确匹配 → 自动改名候选
  descriptive_non_entity  含标点/解释词 → B 隔离
  multiple_entities      多方混名 → C 隔离 pending_split
  ambiguous_name         单一名但不匹配净名 → 隔离待审
每行检查所有引用 formulas.id 的关系表（安全门禁）。
"""
import sqlite3, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "tcm_knowledge.db"
OUT = HERE.parent / "artifacts" / "name-cleanup-plan.json"

FORMULA_SUFFIX = r'(汤|丸|散|丹|膏|饮|煎|酒|丸|栓|露)'


def get_conn():
    c = sqlite3.connect(str(DB)); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c


def referencing_tables(conn):
    refs = []
    for (t,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")'):
            if fk[2] == 'formulas':
                refs.append({'table': t, 'column': fk[3]})
    return refs


def classify(cleaned, net_names):
    if re.search(r'[。，.,；;：:！!？?]', cleaned):
        return 'descriptive_non_entity'
    parts = re.split(r'[、和与及还有]', cleaned)
    formula_parts = [p for p in parts if re.search(FORMULA_SUFFIX, p)]
    if len(formula_parts) >= 2:
        return 'multiple_entities'
    if re.search(r'(是|的|为|即|平常|接近|减少|增加|不一样|还好|煮|收|简称|多|少)', cleaned):
        return 'descriptive_non_entity'
    if cleaned in net_names:
        return 'A_clean_match'
    return 'ambiguous_name'


def main():
    conn = get_conn()
    net_names = set(r[0] for r in conn.execute(
        "SELECT DISTINCT name FROM formulas WHERE name NOT LIKE '> %'"))
    refs = referencing_tables(conn)
    dirty = [dict(r) for r in conn.execute(
        "SELECT * FROM formulas WHERE name LIKE '> %' ORDER BY id")]
    plan = []
    for row in dirty:
        name = row['name']
        cleaned = re.sub(r'^\s*>\s*', '', name).strip()
        reason = classify(cleaned, net_names)
        rel = {}
        for ref in refs:
            cnt = conn.execute(
                f'SELECT count(*) FROM "{ref["table"]}" WHERE "{ref["column"]}"=?',
                (row['id'],)).fetchone()[0]
            if cnt:
                rel[ref['table']] = cnt
        plan.append({
            'id': row['id'], 'name': name, 'cleaned': cleaned, 'reason': reason,
            'source_repo': row.get('source_repo'), 'raw_path': row.get('raw_path'),
            'is_A_safe': reason == 'A_clean_match',
            'has_relations': rel, 'relation_total': sum(rel.values()),
            'block_action': 'BLOCK_B/C_has_relations' if (reason != 'A_clean_match' and sum(rel.values()) > 0) else 'ok',
        })
    conn.close()
    summary = {
        'total_dirty': len(dirty),
        'A_clean_match': sum(1 for p in plan if p['reason'] == 'A_clean_match'),
        'B_descriptive': sum(1 for p in plan if p['reason'] == 'descriptive_non_entity'),
        'C_multiple': sum(1 for p in plan if p['reason'] == 'multiple_entities'),
        'ambiguous': sum(1 for p in plan if p['reason'] == 'ambiguous_name'),
        'B_or_C_with_relations_BLOCKED': sum(1 for p in plan if p['block_action'].startswith('BLOCK')),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'summary': summary, 'plan': plan}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n输出: {OUT}")
    print("\n=== A 类（自动改名候选，去前缀后精确匹配净名）===")
    for p in plan:
        if p['reason'] == 'A_clean_match':
            print(f"  id={p['id']:3d} {p['name']!r} → {p['cleaned']!r}  [{p['source_repo']}]")
    print("\n=== B/C 有引用的安全门禁拦截（BLOCK，不得移出）===")
    for p in plan:
        if p['block_action'].startswith('BLOCK'):
            print(f"  id={p['id']:3d} {p['name']!r} reason={p['reason']} 引用={p['has_relations']}")
    print("\n=== ambiguous（单一名但不匹配净名，待审）===")
    for p in plan:
        if p['reason'] == 'ambiguous_name':
            print(f"  id={p['id']:3d} {p['name']!r} → {p['cleaned']!r}  [{p['source_repo']}]")


if __name__ == '__main__':
    main()
