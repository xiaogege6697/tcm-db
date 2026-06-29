#!/usr/bin/env python3
"""生成 formula 去重迁移计划（只读，不改库）。

输出 artifacts/formula-merge-plan.json，每个重名方剂组含：
- duplicate_ids / canonical_id / canonical_source / canonical_reason
- 每行非空字段、每行在各关系表的关联数
- 字段冲突列表（区分医学语义字段）
- 计划迁移关系数、删除后预期

canonical 选择规则：
  1. 优先带 six_channel 的 nihaixia 版本
  2. 其次带 six_channel 的任意版本
  3. 其次字段完整度最高
  4. 并列时按来源可靠性 + 最低 id
"""
import sqlite3
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "tcm_knowledge.db"
OUT = HERE.parent / "artifacts" / "formula-merge-plan.json"

# 医学语义字段：冲突时保留 canonical 值，其他版本写 evidence(source_record)
MEDICAL_FIELDS = {
    "composition", "dosage", "indication", "six_channel", "syndrome",
    "differentiation", "contraindication", "alias", "commentary",
}
# 元数据字段：不计入完整度，不视为信息丢失
META_FIELDS = {"id", "raw_path", "source_repo"}
# 来源可靠性排序（规则3/4 用）
SOURCE_RANK = {"nihaixia": 0, "hantang": 1}


def get_conn():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def referencing_tables(conn):
    """动态发现所有引用 formulas.id 的 {table, column}（不硬编码）"""
    refs = []
    for (t,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        for fk in conn.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
            # fk: (id, seq, table, from, to, on_update, on_delete, match)
            if fk[2] == "formulas":
                refs.append({"table": t, "column": fk[3]})
    return refs


def fullness(row_dict):
    """字段完整度：非空字段数（排除元数据与 name）"""
    return sum(
        1 for k, v in row_dict.items()
        if k not in META_FIELDS and k != "name" and v not in (None, "")
    )


def pick_canonical(rows):
    r = [dict(x) for x in rows]
    # 规则 1：带 six_channel 的 nihaixia 版
    c = [x for x in r if (x.get("six_channel") or "").strip() and x.get("source_repo") == "nihaixia"]
    if c:
        return min(c, key=lambda x: x["id"]), "rule1:带six_channel的nihaixia版"
    # 规则 1b：带 six_channel 的任意版本
    c = [x for x in r if (x.get("six_channel") or "").strip()]
    if c:
        return min(c, key=lambda x: x["id"]), "rule1b:带six_channel(优先nihaixia未命中)"
    # 规则 2/3/4：完整度最高；并列按来源可靠性 + 最低 id
    fb = max(fullness(x) for x in r)
    tie = [x for x in r if fullness(x) == fb]
    tie.sort(key=lambda x: (SOURCE_RANK.get(x.get("source_repo"), 9), x["id"]))
    return tie[0], f"rule2-4:字段完整度最高({fb}个非空)并列取来源可靠性+最低id"


def build_plan(conn):
    refs = referencing_tables(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(formulas)").fetchall()]
    dup_names = [r[0] for r in conn.execute(
        "SELECT name FROM formulas GROUP BY name HAVING count(*) >= 2 "
        "ORDER BY count(*) DESC, name"
    ).fetchall()]
    plan = []
    for name in dup_names:
        rows = conn.execute("SELECT * FROM formulas WHERE name=? ORDER BY id", (name,)).fetchall()
        rows_d = [dict(x) for x in rows]
        ids = [r["id"] for r in rows_d]
        canon, reason = pick_canonical(rows)
        canon_id = canon["id"]

        per_row = []
        for r in rows_d:
            nonempty = {k: v for k, v in r.items()
                        if k not in META_FIELDS and v not in (None, "")}
            rel = {}
            for ref in refs:
                cnt = conn.execute(
                    f'SELECT count(*) FROM "{ref["table"]}" WHERE "{ref["column"]}"=?',
                    (r["id"],)).fetchone()[0]
                if cnt:
                    rel[ref["table"]] = cnt
            per_row.append({
                "id": r["id"],
                "source_repo": r.get("source_repo"),
                "raw_path": r.get("raw_path"),
                "nonempty_fields": nonempty,
                "relations": rel,
            })

        # 字段冲突：多版本非空且取值不同
        conflicts = []
        for col in cols:
            if col in META_FIELDS or col == "id" or col == "name":
                continue
            vals = {}
            for r in rows_d:
                v = r.get(col)
                if v not in (None, ""):
                    vals.setdefault(v, []).append(r["id"])
            if len(vals) > 1:
                conflicts.append({
                    "field": col,
                    "is_medical": col in MEDICAL_FIELDS,
                    "variants": [{"value": k, "from_ids": v} for k, v in vals.items()],
                    "canonical_value": canon.get(col),
                    "note": ("医学语义字段:保留canonical值,其他版本写evidence(source_record)"
                             if col in MEDICAL_FIELDS else "非医学字段:冲突待人工裁定"),
                })

        # 计划迁移关系数（非 canonical 行的全部关系）
        non_canon = [i for i in ids if i != canon_id]
        migrate_by_table = {}
        migrate_total = 0
        for ref in refs:
            tcnt = 0
            for i in non_canon:
                tcnt += conn.execute(
                    f'SELECT count(*) FROM "{ref["table"]}" WHERE "{ref["column"]}"=?',
                    (i,)).fetchone()[0]
            if tcnt:
                migrate_by_table[ref["table"]] = tcnt
                migrate_total += tcnt

        plan.append({
            "name": name,
            "duplicate_ids": ids,
            "canonical_id": canon_id,
            "canonical_source": canon.get("source_repo"),
            "canonical_reason": reason,
            "rows": per_row,
            "field_conflicts": conflicts,
            "plan_migrate_relations": migrate_total,
            "plan_migrate_by_table": migrate_by_table,
            "expected_after": {"formulas_remaining": 1, "rows_to_delete": len(ids) - 1},
        })
    return plan


def main():
    conn = get_conn()
    plan = build_plan(conn)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    total_del = sum(p["expected_after"]["rows_to_delete"] for p in plan)
    total_mig = sum(p["plan_migrate_relations"] for p in plan)
    med_conf = sum(1 for p in plan for c in p["field_conflicts"] if c["is_medical"])
    nonmed_conf = sum(1 for p in plan for c in p["field_conflicts"] if not c["is_medical"])

    print(f"重名组数         : {len(plan)}")
    print(f"涉及方剂行       : {sum(len(p['duplicate_ids']) for p in plan)}")
    print(f"计划删除冗余行   : {total_del}")
    print(f"计划迁移关系总数 : {total_mig}")
    print(f"医学语义字段冲突 : {med_conf} 处(需写 evidence,标 source_record)")
    print(f"非医学字段冲突   : {nonmed_conf} 处(待人工裁定)")
    print(f"输出             : {OUT}\n")
    print(f"{'方剂':14s} {'ids':30s} {'canon':8s} {'冲突':6s} {'迁移':6s} 理由")
    for p in plan:
        ids_s = str(p["duplicate_ids"])
        if len(ids_s) > 28:
            ids_s = ids_s[:25] + "..."
        print(f"{p['name']:14s} {ids_s:30s} {str(p['canonical_id']):8s} "
              f"{len(p['field_conflicts']):6d} {p['plan_migrate_relations']:6d} {p['canonical_reason']}")
    conn.close()


if __name__ == "__main__":
    main()
