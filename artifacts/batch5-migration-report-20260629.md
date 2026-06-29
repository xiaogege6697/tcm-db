# 五组方剂去重迁移报告 · 2026-06-29

> 单事务迁移：停服 → backup → migrate_batch5.py → 对账 → 重启。可由备份回滚。
> 接续：桂枝汤试点(2026-06-28) + Phase0.5 清洗后的第二批去重。

## 摘要

五组重名方剂合并去重，13 个旧 id → 5 个 canonical（全迁量 0 关系引用）：

| 方剂 | 旧 id（删除） | canonical（保留） |
|---|---|---|
| 麻黄汤 | 24, 27, 31, 51 | 214 |
| 小柴胡汤 | 42, 43, 44 | 230 |
| 抵当汤 | 57, 59, 84 | 250 |
| 旋覆代赭石汤 | 66, 67 | 65 |
| 乌梅丸 | 1 | 265 |

## 执行（单事务，确定性顺序）

1. 旧 subject evidence → canonical（重算 dedupe_key，INSERT OR IGNORE 去重 + 删旧）
2. 写 merged_from + 字段冲突 evidence
3. 普通关系引用改指 canonical（本轮 0 引用，no-op）
4. 补 canonical 空字段（小柴胡汤 chapter=太阳中篇 / 乌梅丸 chapter=厥阴病篇）
5. 最后删旧 formula

任一冲突/孤儿/对账失败 → 整批 ROLLBACK。dry-run 同代码路径先验证。
脚本 `scripts/migrate_batch5.py`（复用 migrate_formula_dedup 工具，**增强**：迁移旧 id 作为 subject 的 normalized_from evidence，否则删旧 formula 后 subject_id 悬空触发 audit「Evidence 多态引用」hard fail）。

## 数据变化

| 指标 | 迁移前 | 迁移后 |
|---|---|---|
| formulas | 287 | **274** |
| 重名组 | 28 | **23** |
| evidence | 39 | **59** |
| quarantine | 14 | 14 |

evidence 分类：field_value 1→8 / merged_from 4→17 / normalized_from 34→34（迁移改 subject 不增减）。

**evidence 59 vs 预计 52 的差异**：多 7 条 field_value（麻黄汤 4 + 抵当汤 3，canonical 与旧 id 字段值冲突，按合并规则保留写 evidence，与桂枝汤试点的 chapter field_value 同类，非去重差异）。

## normalized_from 无损迁移（7 条）

旧 id subject → canonical subject，source_record_id / source_path 原样保留：

| 旧 id | → canonical | 原始 source（仓库内相对路径） |
|---|---|---|
| 1 | 265 | 人纪-4-伤寒论/10.辨厥阴病脉证并治法.md |
| 24 | 214 | 人纪-4-伤寒论/3.辨太阳病脉证并治法上篇.md |
| 31 | 214 | 人纪-4-伤寒论/4.辨太阳病脉证并治法中篇.md |
| 51 | 214 | 人纪-4-伤寒论/4.辨太阳病脉证并治法中篇.md |
| 57 | 250 | 人纪-4-伤寒论/5.辨太阳病脉证并治法下篇.md |
| 59 | 250 | 人纪-4-伤寒论/5.辨太阳病脉证并治法下篇.md |
| 84 | 250 | 人纪-4-伤寒论/6.辨阳明病脉证并治法.md |

## 对账验证（全部通过）

- 13 旧 id 关系引用（formula_herbs/syndromes/case_formulas 等所有 FK→formulas 表）：**0**
- 13 旧 id 仍存 formulas：**0**
- 13 旧 id 作为 subject 的 evidence：**0**（已迁移）
- foreign_key_check：**空**
- integrity_check：**ok**
- audit_db.py：**hard=0**，Evidence 多态引用 PASS
- 13 条 merged_from 映射：(1→265)(24/27/31/51→214)(42/43/44→230)(57/59/84→250)(66/67→65)

## HTTP 验证（重启后）

`python3 -u server.py 8080`（127.0.0.1），FORMULA_REDIRECT_MAP 启动加载 **17 条**（桂枝 4 + 本轮 13）。
13 旧 id HTTP 请求全部 200 重定向到 canonical：
`/api/detail/formulas/<旧id>` → 200 + `_redirected_from=<旧id>` + `_canonical_id=<canonical>` + `id=<canonical>`。
25 项测试 OK（21 函数层 + 4 HTTP 层）。

## 备份与回滚

- 迁移前备份：`backups/tcm_knowledge-backup-20260629-120714.db`（integrity ok，formulas 287，evidence 39）
- 回滚：停服 → 用备份覆盖 `tcm_knowledge.db`（Connection.backup 或 cp）→ 重启

## 脱敏说明

本报告不含本机绝对路径；source 路径均为仓库内相对路径。

## 后续（未执行，待决策）

剩余去重：21 green + 2 yellow（白虎汤迁 12 / 大柴胡汤迁 11，单独处理）。本轮按指令止步于此。
