# evidence 表 Schema 设计 v2（待审核，未执行）

> **状态：仅设计，未写库。** 审核通过后才 `CREATE TABLE`。
> v2 采纳审核意见：拆分 `source_type` 双重语义、加 `dedupe_key` DB 级幂等、多态 CHECK 强化、`confidence` 可空表"不适用"、`merged_from` 取代魔法字段。

---

## 变更摘要（v1 → v2）

| 项 | v1 | v2 |
|---|---|---|
| source_type | 同时表"证据性质+载体" | **拆分**：`evidence_kind`(性质) + `source_type`(载体) |
| 旧记录定位 | source_record_id INTEGER | `source_record_type` + `source_record_id TEXT`（兼容 DB id/文件定位符/复合 id） |
| 防重 | 仅应用层 | **`dedupe_key TEXT NOT NULL UNIQUE`**（SHA-256，DB 级幂等） |
| confidence | NOT NULL DEFAULT 0.0 | 可空，**NULL = 不适用**（非"可信度为零"） |
| 旧行映射 | field_name='_merge_origin'（魔法字段） | `relation_type='merged_from'`，field_name=NULL |
| 多态完整性 | 应用层 | 强化 CHECK + `audit_db.py` 审计 + 删前检查 |
| 实体枚举 | 摘要 | **完整枚举（实际表名）** |

---

## 1. 完整 DDL

```sql
CREATE TABLE IF NOT EXISTS evidence (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 主体（证据描述"谁"）
    subject_type        TEXT    NOT NULL CHECK (subject_type IN ENTITY_ENUM),
    subject_id          INTEGER NOT NULL,

    -- 关系/字段（证据描述"什么"）
    relation_type       TEXT    NOT NULL CHECK (relation_type IN
                            ('source_record','field_value','entity_relation','textual','merged_from')),
    object_type         TEXT    CHECK (object_type IS NULL OR object_type IN ENTITY_ENUM),
    object_id           INTEGER,

    -- 证据性质 + 资料载体（拆分，正交）
    evidence_kind       TEXT    NOT NULL CHECK (evidence_kind IN
                            ('source_record','explicit','extracted','inferred','model_suggested')),
    source_type         TEXT    NOT NULL CHECK (source_type IN
                            ('database_row','markdown','pdf','image','github','manual')),

    -- 旧记录定位（仅 evidence_kind='source_record' 且来源是 DB 行时填）
    source_record_type  TEXT    CHECK (source_record_type IS NULL OR source_record_type IN ENTITY_ENUM),
    source_record_id    TEXT,                            -- TEXT：兼容 DB id / 文件定位符 / 未来复合 id
    source_id           INTEGER,                         -- 来源实体 id（如 classics.id），多态
    source_path         TEXT,                            -- 来源文件路径

    -- 内容
    field_name          TEXT,
    evidence_text       TEXT    NOT NULL,
    confidence          REAL    CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    extraction_method   TEXT    NOT NULL DEFAULT 'manual' CHECK (extraction_method IN
                            ('manual','regex','llm_assisted','migration','etl')),
    review_status       TEXT    NOT NULL DEFAULT 'pending' CHECK (review_status IN
                            ('pending','reviewed','rejected')),

    -- 幂等 + 元数据
    dedupe_key          TEXT    NOT NULL UNIQUE,         -- DB 级幂等：规范化关键字段的 SHA-256
    metadata_json       TEXT    CHECK (metadata_json IS NULL OR json_valid(metadata_json)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),

    -- 复合一致性约束
    CHECK ((object_type IS NULL AND object_id IS NULL)
        OR (object_type IS NOT NULL AND object_id IS NOT NULL))
);

-- 索引（dedupe_key 的 UNIQUE 自带索引，不另建）
CREATE INDEX IF NOT EXISTS idx_ev_subject      ON evidence(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_ev_object       ON evidence(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_ev_kind         ON evidence(evidence_kind);
CREATE INDEX IF NOT EXISTS idx_ev_relation     ON evidence(subject_type, relation_type);
CREATE INDEX IF NOT EXISTS idx_ev_src_record   ON evidence(source_record_type, source_record_id);
```

> 注：SQLite 不支持 CHECK 内部宏展开，`ENTITY_ENUM` 在实际建表时需**展开为完整字面量元组**（见 §2）。

---

## 2. 完整枚举（ENTITY_ENUM 展开值，使用实际表名）

`subject_type` / `object_type` / `source_record_type` 取值（16 个实体类型，对应 16 张实体表）：

```
'formula','herb','symptom','syndrome','acupoint','meridian',
'clinical_case','folk_formula','course','classic','course_note',
'book','lecture','tianji','treatment_method','diagnostic_note'
```

类型→表名映射（`audit_db.py` 用）：
```
formula→formulas, herb→herbs, symptom→symptoms, syndrome→syndromes,
acupoint→acupoints, meridian→meridians, clinical_case→clinical_cases,
folk_formula→folk_formulas, course→courses, classic→classics,
course_note→course_notes, book→books, lecture→lectures, tianji→tianji,
treatment_method→treatment_methods, diagnostic_note→diagnostic_notes
```

---

## 3. 所有 CHECK 约束（汇总）

| 约束 | 表达式 |
|---|---|
| subject_type 枚举 | `subject_type IN (...16值...)`（NOT NULL） |
| subject_id 必填 | `subject_id INTEGER NOT NULL` |
| object 配对一致 | `(object 同时空) OR (object 同时非空)` |
| object_type 枚举 | `object_type IS NULL OR object_type IN (...16值...)` |
| relation_type 枚举 | `IN ('source_record','field_value','entity_relation','textual','merged_from')` |
| evidence_kind 枚举 | `IN ('source_record','explicit','extracted','inferred','model_suggested')` |
| source_type 枚举 | `IN ('database_row','markdown','pdf','image','github','manual')` |
| source_record_type 枚举 | `source_record_type IS NULL OR source_record_type IN (...16值...)` |
| confidence 范围 | `confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0` |
| extraction_method 枚举 | `IN ('manual','regex','llm_assisted','migration','etl')` |
| review_status 枚举 | `IN ('pending','reviewed','rejected')` |
| metadata_json 合法 | `metadata_json IS NULL OR json_valid(metadata_json)` |
| dedupe_key 唯一 | `dedupe_key TEXT NOT NULL UNIQUE` |

---

## 4. dedupe_key 生成规范

### 参与计算的字段（12 个结构性字段，定义"同一证据"身份）
`subject_type, subject_id, relation_type, object_type, object_id, evidence_kind, source_type, source_record_type, source_record_id, field_name, source_path, source_id`

### 不参与的字段（非身份定义）
`evidence_text`（长文本，可能有细微差异）、`confidence`（性质标记）、`metadata_json`（附属）、`review_status`（会变）、`extraction_method`（可能变）、`created_at`、`id`

### 规范化规则（规范 JSON 数组，保留类型差异）
- **不用 `'|'` join**：字段值本身可能含 `|`，会产生歧义。
- **NULL 与空串不合并**（语义可能不同）：`None` → JSON `null`，`''` → JSON `""`。
- 整数保持数字、字符串保持字符串；字段顺序固定（`DEDUPE_FIELDS`）。

### 算法
```python
import json, hashlib
DEDUPE_FIELDS = ['subject_type','subject_id','relation_type','object_type','object_id',
                 'evidence_kind','source_type','source_record_type','source_record_id',
                 'field_name','source_path','source_id']   # 仅身份字段

def make_dedupe_key(rec):
    values = [rec.get(f) for f in DEDUPE_FIELDS]   # 保留 None/''/int/str 类型差异
    canon = json.dumps(values, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()
```

> **dedupe_key 不含**：`confidence`、`review_status`、`metadata_json`（可变审核信息）、`created_at`/`updated_at`。这些变化时用 `INSERT ... ON CONFLICT(dedupe_key) DO UPDATE SET ...` 更新原记录，**不产生新 evidence**。

### 幂等执行
- **dry-run 与正式执行共用同一函数**（`scripts/migrate_formula_dedup.py` 导入 `make_dedupe_key`）。
- 写入用 `INSERT OR IGNORE INTO evidence ...`（dedupe_key 冲突则忽略）。
- **重跑测试**：连续执行迁移两次，第二次 evidence 行数不增（见 §7）。

---

## 5. 5 条桂枝汤实际 INSERT 参数（canonical=209）

### (A) chapter 中篇来源记录（1 条）—— canonical 取"上篇"，中篇保留
| 字段 | 值 |
|---|---|
| subject_type | `formula` |
| subject_id | `209` |
| relation_type | `field_value` |
| object_type / object_id | NULL / NULL |
| evidence_kind | `source_record` |
| source_type | `database_row` |
| source_record_type | `formula` |
| source_record_id | `'28'` |
| source_id | NULL |
| source_path | `hantang-nihaixia-follower/倪海厦/人纪-4-伤寒论/4.辨太阳病脉证并治法中篇.md` |
| field_name | `chapter` |
| evidence_text | `4.辨太阳病脉证并治法中篇` |
| confidence | **NULL**（不适用，非"可信度零"） |
| extraction_method | `migration` |
| review_status | `pending` |
| metadata_json | `{"canonical_value":"3.辨太阳病脉证并治法上篇","original_source_repo":"hantang","reason":"合并去重保留的非canonical chapter;chapter不参与医学推理"}` |

### (B-E) 旧行来源映射（4 条，relation_type=`merged_from`，field_name=NULL）
以旧 id=8 为例（9/15 同 raw_path，28 的 source_path/chapter 为中篇）：

| 字段 | 值（旧 id=8） |
|---|---|
| subject_type | `formula` |
| subject_id | `209`（canonical） |
| relation_type | `merged_from` |
| object_type / object_id | NULL / NULL |
| evidence_kind | `source_record` |
| source_type | `database_row` |
| source_record_type | `formula` |
| source_record_id | `'8'` |
| source_path | `hantang-nihaixia-follower/倪海厦/人纪-4-伤寒论/3.辨太阳病脉证并治法上篇.md` |
| field_name | NULL |
| evidence_text | `原formula_id=8已合并入canonical 209` |
| confidence | NULL |
| extraction_method | `migration` |
| metadata_json | `{"original_name":"桂枝汤","duplicate_of":209,"original_source_repo":"hantang","original_raw_path":".../3.上篇.md","original_chapter":"3.辨太阳病脉证并治法上篇"}` |

> 旧 id=9 / 15：与 id=8 同 raw_path（真重复），metadata 标 `{"note":"与id8同文件,真重复"}`，source_path 同 id8。
> 旧 id=28：source_path 为中篇，metadata 的 `original_chapter="4.中篇"`。

---

## 6. 索引及对应查询场景

| 索引 | 场景 |
|---|---|
| `idx_ev_subject (subject_type, subject_id)` | 查"某实体（如桂枝汤 209）的所有证据" |
| `idx_ev_object (object_type, object_id)` | 反查"某客体被哪些证据引用"（如某证型被哪些方-证证据指向） |
| `idx_ev_kind (evidence_kind)` | 筛选"所有 source_record"或"所有 explicit 医学原文" |
| `idx_ev_relation (subject_type, relation_type)` | 查"方剂的 entity_relation 证据"（方-证推理）或"merged_from 来源" |
| `idx_ev_src_record (source_record_type, source_record_id)` | 旧 id 反查：`WHERE source_record_type='formula' AND source_record_id='8'` |
| `dedupe_key UNIQUE`（隐式） | DB 级幂等防重 |

---

## 7. 重跑幂等测试

```sql
-- 伪代码：迁移函数对桂枝汤组生成 5 条 evidence 并 INSERT OR IGNORE
-- 第一次执行
INSERT OR IGNORE INTO evidence (..., dedupe_key, ...) VALUES (..., '<k1>', ...);  -- ×5 → 插入 5
-- 第二次执行（同样 5 条，dedupe_key 相同）
INSERT OR IGNORE INTO evidence (..., dedupe_key, ...) VALUES (..., '<k1>', ...);  -- ×5 → 全 IGNORE
-- 断言
SELECT count(*) FROM evidence WHERE subject_type='formula' AND subject_id=209;  -- 期望: 5（不变）
```

`scripts/audit_db.py` 的幂等检查：
```python
def check_evidence_idempotent(conn, run_migration_fn):
    before = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
    run_migration_fn(conn)   # 第一次
    mid = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
    run_migration_fn(conn)   # 第二次（应无新增）
    after = conn.execute("SELECT count(*) FROM evidence").fetchone()[0]
    assert mid == after, f"幂等失败: 第一次{mid} 第二次{after}"
    return mid - before      # 第一次实际新增数
```

---

## 8. 多态引用审计（scripts/audit_db.py）

```python
TYPE_TO_TABLE = {
    'formula':'formulas','herb':'herbs','symptom':'symptoms','syndrome':'syndromes',
    'acupoint':'acupoints','meridian':'meridians','clinical_case':'clinical_cases',
    'folk_formula':'folk_formulas','course':'courses','classic':'classics',
    'course_note':'course_notes','book':'books','lecture':'lectures','tianji':'tianji',
    'treatment_method':'treatment_methods','diagnostic_note':'diagnostic_notes',
}

def audit_evidence_refs(conn):
    """校验 evidence 的多态引用真实存在；返回 issues 列表。"""
    issues = []
    rows = conn.execute(
        "SELECT id, subject_type, subject_id, object_type, object_id, "
        "source_record_type, source_record_id, source_type FROM evidence").fetchall()
    for eid, st, sid, ot, oid, srt, srid, soty in rows:
        # subject 必须存在
        t = TYPE_TO_TABLE.get(st)
        if t and not conn.execute(f'SELECT 1 FROM "{t}" WHERE id=?', (sid,)).fetchone():
            issues.append(('orphan_subject', eid, st, sid))
        # object（非空时）必须存在
        if ot is not None and oid is not None:
            t = TYPE_TO_TABLE.get(ot)
            if t and not conn.execute(f'SELECT 1 FROM "{t}" WHERE id=?', (oid,)).fetchone():
                issues.append(('orphan_object', eid, ot, oid))
        # source_record（仅 database_row 载体时校验，文件定位符不校验）
        if srt and soty == 'database_row' and srid:
            t = TYPE_TO_TABLE.get(srt)
            if t and not conn.execute(f'SELECT 1 FROM "{t}" WHERE id=?', (srid,)).fetchone():
                issues.append(('orphan_source_record', eid, srt, srid))
    return issues

def check_evidence_before_delete(conn, subject_type, subject_id):
    """删除 canonical 实体前必须调用：仍有证据引用则阻止。"""
    n = conn.execute(
        "SELECT count(*) FROM evidence WHERE subject_type=? AND subject_id=?",
        (subject_type, subject_id)).fetchone()[0]
    return n == 0   # True=可删
```

---

## 9. evidence_kind 与 source_type 语义说明（正交两维）

### evidence_kind（证据**性质** —— 这条记录是什么性质的证据）
| 值 | 含义 | 典型 confidence |
|---|---|---|
| `source_record` | 来源记录（迁移保留的旧数据/多来源差异） | NULL（不适用） |
| `explicit` | 显式医学原文证据（如"桂枝汤主之"原文） | 0.7–1.0 |
| `extracted` | 从文本结构化抽取（如正则抽方-证） | 0.4–0.8 |
| `inferred` | 推断得出（需人工/模型复核） | 0.2–0.6 |
| `model_suggested` | 模型建议、**未验证**（默认 review_status=pending） | 0.0–0.5 |

### source_type（资料**载体** —— 这条证据的物理形态）
| 值 | 含义 |
|---|---|
| `database_row` | 数据库行（如被合并的旧 formula 行） |
| `markdown` | Markdown 文件（如源仓库 .md） |
| `pdf` | PDF 文档 |
| `image` | 图片（如课程截图） |
| `github` | GitHub 源（仓库/issue/commit） |
| `manual` | 人工录入（无外部来源） |

**正交示例**：
- 迁移保留的旧 formula 行 → `evidence_kind=source_record` + `source_type=database_row`
- 《伤寒论》md 原文证据 → `evidence_kind=explicit` + `source_type=markdown`
- 模型从 PDF 抽取的关联 → `evidence_kind=model_suggested` + `source_type=pdf`

---

## 10. 待你审核
1. 字段集（含新增 evidence_kind/source_type 拆分、source_record_id 改 TEXT、dedupe_key）是否认可？
2. ENTITY_ENUM 16 个实体类型是否完整？是否要加/减？
3. dedupe_key 参与 12 字段、规范化规则、SHA-256 算法是否认可？
4. 5 条桂枝汤 INSERT（confidence=NULL、merged_from、旧 id 保留 source_path/chapter）是否符合预期？
5. 多态审计（audit_evidence_refs + 删前 check_evidence_before_delete）是否充分？

审核通过后：新备份 → `CREATE TABLE evidence` + 索引 → 桂枝汤事务迁移（dry-run 与正式同一套代码、事务内先写 evidence→迁关系→删冗余、整组 ROLLBACK、对账含 evidence 幂等检查）。
