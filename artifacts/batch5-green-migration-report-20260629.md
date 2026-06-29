# 5 green 关系迁移组报告 · 2026-06-29

> 验证通用迁移脚本 `migrate_formula_dedup.py migrate`（已回填 evidence subject/object 迁移 + 删除门禁）的完整关系迁移链。
> 接续：桂枝汤(方药迁移) + 五组(批量+evidence迁移) 之后第三批，专测普通关系迁移。

## 摘要

5 个 green 组（关系迁移量非0），12 旧id → 5 canonical：

| 方剂 | 旧id（删除） | canonical | 关系迁移(formula_herbs) |
|---|---|---|---|
| 桂枝甘草汤 | 54 | 220 | 3 |
| 五苓散 | 32, 33, 34, 86 | 225 | 2 |
| 真武汤 | 36, 37, 98, 101 | 228 | 2 |
| 四逆汤 | 39, 83 | 253 | 1 |
| 调胃承气汤 | 40 | 247 | 1 |

## 执行（通用脚本单事务）

```
python3 scripts/migrate_formula_dedup.py migrate \
  --name 桂枝甘草汤 --name 五苓散 --name 真武汤 --name 四逆汤 --name 调胃承气汤
```

停服 → Connection.backup → migrate 单事务 → 对账 → `python3 -u` 重启。dry-run 先验证（同代码路径 ROLLBACK）。

## 数据变化

| 指标 | 前 | 后 |
|---|---|---|
| formulas | 274 | **262** |
| 重名组 | 23 | **18** |
| evidence | 59 | **81** |
| quarantine | 14 | 14 |

evidence 分类：field_value 8→18（+10 字段冲突保留）/ merged_from 17→29（+12）/ normalized_from 34→34（5条迁移改 subject 净 0）。

## normalized_from 迁移（5条，无损）

旧id 32/83/86/98/101 的 normalized_from → subject 改指 canonical，source_record_id/source_path 原样保留。

## 关系迁移链（本轮验证目标）

12 旧id 的 9 条 formula_herbs 关系 → INSERT OR IGNORE 合并到 canonical + DELETE 旧：
- 桂枝甘草汤(220): distinct herbs 3（旧id54 的 3 herb 归并）
- 五苓散/真武汤/四逆汤/调胃承气汤: distinct herbs 1（旧id herb 与 canon 去重）

## 对账（全部通过）

- 12旧id 仍存 formulas: 0
- 12旧id 作 subject/object: 0（已迁移）
- 12旧id 关系引用（动态扫描所有 FK→formulas 表）: 0
- merged_from 总: 29（桂枝4 + 五组13 + 本轮12）
- foreign_key_check: 空 / integrity_check: ok
- audit_db.py: **hard=0，Evidence 多态引用 PASS，duplicates=18**

## HTTP 验证

server PID 41253（`python3 -u`, 127.0.0.1:8080），redirect map **29 条**。12 旧id HTTP 请求全部 200 重定向到 canonical。
测试：api 25项 + migrate_dedup 10项 + schema_parity 1项 全过。

## 备份与回滚

- 迁移前备份：`backups/tcm_knowledge-backup-20260629-*.db`（integrity ok, formulas 274, evidence 59）
- 回滚：停服 → 备份覆盖 `tcm_knowledge.db` → 重启

## 通用脚本验证（关键）

本批**用通用脚本** `migrate_formula_dedup.py migrate`（不再用一次性 migrate_batch5.py），完整验证：
- evidence subject/object 迁移 + dedupe_key 重算（normalized_from 5条）
- 删除前门禁（旧id不作 subject/object + 关系归零 + audit_evidence_refs 通过）
- 关系迁移链（formula_herbs INSERT OR IGNORE 合并 + DELETE）
- 多组单事务 + 事务内对账

全部通过，通用脚本可承担后续剩余 green 按批自动推进。

## 脱敏说明

本报告不含本机绝对路径；source 路径均为仓库内相对路径。

## 后续（未执行，本轮止步）

剩余 16 green + 2 yellow（白虎汤迁12 / 大柴胡汤迁11，单独裁定）。通用脚本就绪，可按批自动推进。
