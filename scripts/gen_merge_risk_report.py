#!/usr/bin/env python3
"""对剩余重名方剂组生成去重风险评估报告（green/yellow/red）。只读，不改库。

评估维度：
- normalized formula_herbs 集合（herb_id 集合是否一致）
- 剂量与炮制差异（formula_herbs 的 role/dosage_in_formula/note）
- 原始来源差异（source_repo / raw_path）
- 非空字段冲突（医学 / 非医学）
- 关系数量 + 旧 id 在 case_formulas（医案）的引用
- 分类 green / yellow / red
"""
import sqlite3, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "tcm_knowledge.db"
OUT_J = HERE.parent / "artifacts" / "merge-risk-report.json"
OUT_M = HERE.parent / "artifacts" / "merge-risk-report.md"

MEDICAL_FIELDS = {'composition', 'dosage', 'indication', 'six_channel', 'syndrome',
                  'differentiation', 'contraindication', 'alias', 'commentary'}
CONFLICT_FIELDS = ['source_book', 'chapter', 'alias', 'composition', 'dosage', 'indication',
                   'six_channel', 'syndrome', 'differentiation', 'contraindication', 'commentary']


def get_conn():
    c = sqlite3.connect(str(DB)); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c


def referencing_tables(conn):
    refs = []
    for (t,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")'):
            if fk[2] == 'formulas':
                refs.append((t, fk[3]))
    return refs


def pick_canonical(rows_d):
    rank = {'nihaixia': 0, 'hantang': 1}
    def full(r):
        return sum(1 for k, v in r.items()
                   if k not in ('id', 'raw_path', 'source_repo', 'name') and v not in (None, ''))
    c = [x for x in rows_d if (x.get('six_channel') or '').strip() and x.get('source_repo') == 'nihaixia']
    if c: return min(c, key=lambda x: x['id'])
    c = [x for x in rows_d if (x.get('six_channel') or '').strip()]
    if c: return min(c, key=lambda x: x['id'])
    fb = max(full(x) for x in rows_d)
    tie = [x for x in rows_d if full(x) == fb]
    tie.sort(key=lambda x: (rank.get(x.get('source_repo'), 9), x['id']))
    return tie[0]


def field_conflicts(rows_d, canon):
    canon_id = canon['id']
    out = []
    for f in CONFLICT_FIELDS:
        c_val = (canon.get(f) or '').strip() or None
        others = {}
        for r in rows_d:
            if r['id'] == canon_id: continue
            v = (r.get(f) or '').strip() or None
            if v: others.setdefault(v, []).append(r['id'])
        if c_val:
            for v, ids in others.items():
                if v != c_val:
                    out.append({'field': f, 'is_medical': f in MEDICAL_FIELDS,
                                'canonical': c_val, 'conflict_value': v, 'from_ids': ids})
        else:
            if len(others) > 1:
                for v, ids in others.items():
                    out.append({'field': f, 'is_medical': f in MEDICAL_FIELDS,
                                'canonical': None, 'conflict_value': v, 'from_ids': ids})
    return out


def herbs_info(conn, ids):
    info = {}
    for i in ids:
        rows = conn.execute(
            "SELECT herb_id,role,dosage_in_formula,note FROM formula_herbs WHERE formula_id=?",
            (i,)).fetchall()
        info[i] = {
            'herb_ids': sorted(set(r['herb_id'] for r in rows)),
            'detail': sorted((r['herb_id'], (r['role'] or '').strip(),
                              (r['dosage_in_formula'] or '').strip(), (r['note'] or '').strip())
                             for r in rows),
        }
    return info


def classify(g):
    med = [c for c in g['field_conflicts'] if c['is_medical']]
    nonmed = [c for c in g['field_conflicts'] if not c['is_medical']]
    if med or not g['herbs_consistent']:
        return 'red'
    if g['relation_counts']['case_formulas_on_dup'] > 5 or len(nonmed) > 2 or g['migrate_relations'] > 20:
        return 'yellow'
    return 'green'


def main():
    conn = get_conn()
    refs = referencing_tables(conn)
    dup_names = [r[0] for r in conn.execute(
        "SELECT name FROM formulas GROUP BY name HAVING count(*)>=2 "
        "ORDER BY count(*) DESC, name").fetchall()]
    groups = []
    for name in dup_names:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM formulas WHERE name=? ORDER BY id", (name,)).fetchall()]
        ids = [r['id'] for r in rows]
        canon = pick_canonical(rows); canon_id = canon['id']
        non_canon = [i for i in ids if i != canon_id]
        hi = herbs_info(conn, ids)
        # 忽略空集合（无药的行）：只比较非空药集合是否一致（有药vs无药算互补，非冲突）
        non_empty_herbsets = {tuple(v['herb_ids']) for v in hi.values() if v['herb_ids']}
        herbs_consistent = len(non_empty_herbsets) <= 1
        # 剂量/炮制差异：detail 集合是否一致（同样忽略空）
        non_empty_details = {tuple(v['detail']) for v in hi.values() if v['detail']}
        detail_consistent = len(non_empty_details) <= 1
        rel = {}
        for i in ids:
            r = {}
            for t, c in refs:
                n = conn.execute(f'SELECT count(*) FROM "{t}" WHERE "{c}"=?', (i,)).fetchone()[0]
                if n: r[t] = n
            rel[i] = r
        case_on_dup = sum(rel.get(i, {}).get('case_formulas', 0) for i in non_canon)
        migrate = sum(sum(rel.get(i, {}).values()) for i in non_canon)
        fc = field_conflicts(rows, canon)
        g = {
            'name': name, 'duplicate_ids': ids, 'canonical_id': canon_id,
            'canonical_source': canon.get('source_repo'),
            'herbs_consistent': herbs_consistent,
            'dosage_prep_consistent': detail_consistent,
            'herbs_per_id': {str(k): len(v['herb_ids']) for k, v in hi.items()},
            'field_conflicts': fc,
            'relation_counts': {
                'per_id': {str(k): v for k, v in rel.items()},
                'case_formulas_on_dup': case_on_dup,
                'migrate_total': migrate,
            },
            'migrate_relations': migrate,
            'sources': sorted({(r.get('source_repo') or '') + ' | ' + (r.get('raw_path') or '') for r in rows}),
        }
        g['risk'] = classify(g)
        groups.append(g)
    conn.close()

    by = {'green': [], 'yellow': [], 'red': []}
    for g in groups:
        by[g['risk']].append(g['name'])
    OUT_J.parent.mkdir(parents=True, exist_ok=True)
    OUT_J.write_text(json.dumps(
        {'summary': {k: len(v) for k, v in by.items()}, 'groups': groups},
        ensure_ascii=False, indent=2))

    md = ["# 剩余方剂去重风险评估", "",
          "> 桂枝汤已迁移，不在评估内。",
          "green=可直接批量；yellow=需留意（关系多/非医学冲突多）；red=需人工裁定（医学冲突或药集合不一致）。", "",
          f"- 🟢 green: {len(by['green'])} 组 — {', '.join(by['green']) or '无'}",
          f"- 🟡 yellow: {len(by['yellow'])} 组 — {', '.join(by['yellow']) or '无'}",
          f"- 🔴 red: {len(by['red'])} 组 — {', '.join(by['red']) or '无'}", "", "## 明细", ""]
    for g in groups:
        med = sum(1 for c in g['field_conflicts'] if c['is_medical'])
        nonmed = sum(1 for c in g['field_conflicts'] if not c['is_medical'])
        md.append(f"### [{g['risk'].upper()}] {g['name']}  ids={g['duplicate_ids']} → canon={g['canonical_id']}({g['canonical_source']})")
        md.append(f"- 药集合一致: {'✅' if g['herbs_consistent'] else '❌'} | 剂量炮制一致: {'✅' if g['dosage_prep_consistent'] else '⚠️'}")
        md.append(f"- 字段冲突: {len(g['field_conflicts'])} 处 (医学 {med} / 非医学 {nonmed})")
        for c in g['field_conflicts']:
            tag = '医学' if c['is_medical'] else '非医学'
            md.append(f"  - [{tag}] {c['field']}: canon={c['canonical']!r} 冲突={c['conflict_value']!r} from={c['from_ids']}")
        md.append(f"- 关系迁移: {g['migrate_relations']} (旧 id 挂医案 case_formulas: {g['relation_counts']['case_formulas_on_dup']})")
        md.append("")
    OUT_M.write_text('\n'.join(md))

    print(f"🟢 green={len(by['green'])}  🟡 yellow={len(by['yellow'])}  🔴 red={len(by['red'])}")
    print(f"green 组: {by['green']}")
    print(f"输出: {OUT_M}")


if __name__ == '__main__':
    main()
