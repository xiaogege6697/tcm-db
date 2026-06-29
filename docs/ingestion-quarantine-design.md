# ingestion_quarantine 隔离表设计（待审核，未实施）

> **状态：仅设计，未建表。** 审核通过后才 CREATE。
> 定位：ETL 编译器前端的**隔离区**——把"无法确定为合法领域实体"的候选暂存，不进 formulas/evidence，可逆恢复，待人工裁定。
> **不写入 evidence**：evidence 表达"实体/关系的证据"，而隔离区内容**没有合法 subject**，硬塞会污染证据语义和多态审计。

---

## 1. 完整 DDL

```sql
CREATE TABLE IF NOT EXISTS ingestion_quarantine (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table      TEXT    NOT NULL CHECK (source_table IN (
                          'formulas','herbs','syndromes','symptoms','acupoints',
                          'clinical_cases','folk_formulas','classics','course_notes',
                          'books','lectures','tianji','treatment_methods')),
    source_record_id  INTEGER NOT NULL,          -- 原表记录 id（移出前）
    reason_code       TEXT    NOT NULL CHECK (reason_code IN (
                          'descriptive_non_entity',   -- 描述性文本，非实体
                          'multiple_entities',        -- 多实体混在一条
                          'invalid_markdown_parse',   -- markdown 解析异常
                          'ambiguous_name')),         -- 单一名但无法确认是合法实体
    status           TEXT    NOT NULL DEFAULT 'pending_review' CHECK (status IN (
                          'pending_review','rejected','restored','split')),
    raw_record_json  TEXT    NOT NULL CHECK (json_valid(raw_record_json)),  -- 原整行 JSON，可逆
    source_repo      TEXT,
    source_path      TEXT,                         -- raw_path / locator
    original_name    TEXT,                         -- 原脏名（如 "> 抵当汤"）
    cleaned_name     TEXT,                         -- 清洗后候选名（如 "抵当汤"）
    run_id           TEXT    NOT NULL,             -- 清洗批次标识（如 "phase0.5-20260628"）
    dedupe_key       TEXT    NOT NULL UNIQUE,      -- 幂等：(source_table, source_record_id) SHA-256
    quarantined_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    review_note      TEXT,
    metadata_json    TEXT    CHECK (metadata_json IS NULL OR json_valid(metadata_json)),
    CHECK (length(raw_record_json) > 2)            -- 不是空 JSON
);
CREATE INDEX IF NOT EXISTS idx_quar_source ON ingestion_quarantine(source_table, source_record_id);
CREATE INDEX IF NOT EXISTS idx_quar_reason ON ingestion_quarantine(reason_code, status);
CREATE INDEX IF NOT EXISTS idx_quar_run    ON ingestion_quarantine(run_id);
```

## 2. 字段说明
| 字段 | 用途 |
|---|---|
| `source_table` + `source_record_id` | 溯源：从哪张表的哪条记录移来 |
| `reason_code` | 四类：描述性垃圾 / 多方混名 / markdown 解析异常 / 歧义名 |
| `status` | 审核流转：待审 → 已拒绝 / 已恢复 / 已拆分 |
| `raw_record_json` | **原 formulas 整行 JSON**，保证可逆恢复（status=restored 时回填 formulas） |
| `original_name` / `cleaned_name` | 脏名 + 清洗候选，便于审核 |
| `run_id` | 批次隔离，便于按次回滚/审计 |
| `dedupe_key` | `(source_table, source_record_id)` 的规范 JSON SHA-256，重跑幂等 |

## 3. dedupe_key 生成（与 evidence 同规范）
```python
def make_quarantine_key(source_table, source_record_id):
    canon = json.dumps([source_table, source_record_id], ensure_ascii=False, separators=(',',':'))
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()
```
同一原记录只隔离一次；重跑 `INSERT OR IGNORE`。

## 4. 与 evidence 的边界
| | evidence | ingestion_quarantine |
|---|---|---|
| 内容 | 合法实体/关系的证据 | 无法确定为合法实体的候选 |
| subject | 必须指向真实实体 | **无合法 subject** |
| 多态审计 | subject/object 必须存在 | 不参与（无 subject） |
| 恢复 | 不需要 | status=restored → 回填原表 |

## 5. 守恒律（Phase 0.5 执行时强制校验）
```
formulas_after + quarantine_added = formulas_before
```
- A 类（改名）：formulas 总数不变（只 UPDATE name）。
- B/C/ambiguous（移出）：formulas −N，quarantine +N。
- 任一不满足 → 整批 ROLLBACK。

## 6. 安全门禁（移出前逐行）
对每条 B/C/ambiguous 行，查所有引用 `formulas.id` 的关系表（formula_herbs/formula_syndromes/case_formulas 等）：
- **有引用 → BLOCK，停止该行移出，报告**（不得直接删，会留孤儿）。
- 无引用 → 允许移出（raw_record_json 备份后 DELETE from formulas）。
- A 类改名：id 不变，关系自然保留，无需迁移。

## 7. 恢复路径（status=restored）
```sql
-- 审核后决定恢复某条
UPDATE ingestion_quarantine SET status='restored', review_note='人工确认是真方剂' WHERE id=?;
-- 应用层从 raw_record_json 重建 formulas 行（新 id 或保留原 id 若未冲突）
```

## 8. 待你审核
1. 字段集 + CHECK 枚举是否够用？
2. `source_table` 枚举是否覆盖未来需要的表？
3. `dedupe_key = (source_table, source_record_id)` 是否接受（同一原记录只隔离一次）？
4. 守恒律 + 安全门禁是否照此实施？
5. `raw_record_json` 可逆恢复机制是否接受？

审核通过后：建表 → Phase 0.5（停服+备份+单一事务+逐行门禁+守恒律校验+对账）→ 重做 merge-plan/risk-report → 重新选组去重。
