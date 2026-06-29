# Yellow 方剂最终迁移报告（白虎汤 / 大柴胡汤）· 2026-06-29

> 两独立事务执行（任一失败只回滚当前方剂）。**机械性去重全部完成（含 yellow），重名组 2→0。**
> 裁定依据见 `docs/yellow-formula-decision-report.md`（commit f08d9eb）。

## 摘要

| 方剂 | 旧id（删） | canonical | 事务 |
|---|---|---|---|
| 白虎汤 | 2, 16, 76, 77, 78 | 243 | 事务1 |
| 大柴胡汤 | 46, 60, 68 | 41 | 事务2 |

共删 8 旧id。每方：停服→独立备份→dry-run→单事务 migrate→对账。事务1 后保持停服，事务2 后统一重启。

## 数据变化

| 指标 | 前 | 后 |
|---|---|---|
| formulas | 242 | **234** |
| 重名组 | 2 | **0** |
| evidence | 106 | **121** |
| redirect map | 49 | **57** |
| quarantine | 14 | 14 |

evidence 分类：merged_from 49→57（+8，白虎5+大柴胡3）/ field_value 23→30（+7，白虎5 chapter+大柴胡2 chapter）/ normalized_from 34（迁移无损）。

## 白虎汤事务1（canon 243）

- **chapter 处理**（按指令）：canonical 243 chapter 保持 **NULL**（不人为选篇章）；厥阴病篇/太阳上篇/太阳下篇全部写 field_value evidence（5 条，保留来源篇章）
- formula_herbs 迁移：id 16/77/78 各 4 herb → 合并到 243，distinct herbs 前后一致 `[147,171,364,441]`（石膏/知母/粳米/炙甘草）
- 8 医案原挂 243（canonical），无迁移
- updates={}（无空值互补）

## 大柴胡汤事务2（canon 41）

- chapter：canon 41（太阳中篇）保留；id 60/68（太阳下篇）写 field_value evidence（2 条）
- **9 条 case_formulas（id 68）→ 完整迁移到 41**：distinct cases 前后一致 `[744,758,759,883,884,1124,1125,1235,1630]`
- 疑似重复医案 **758/759、1124/1125 保持原样**（本轮不去重，按指令）
- formula_herbs：id 46/68 厚朴 → 41（去重一致）

## 对账（全部通过）

- 重名组：**0**（green=0/yellow=0/red=0，最终 risk-report 确认）
- 8 旧id 仍存 formulas / 关系 / subject·object：0（subject/object evidence 已迁移，source_record_id 保留历史旧id）
- merged_from 57 完整 / normalized_from 34 无损 / field_value 30
- foreign_key_check: 空 / integrity_check: ok
- audit_db.py: **hard=0，duplicates=0，Evidence 多态引用 PASS**

## HTTP 验证

server（`python3 -u`, 127.0.0.1:8080），redirect map **57 条**。**全部57旧id HTTP 200 重定向**；新增8旧id确认：
- 白虎 2/16/76/77/78 → 243（白虎汤）
- 大柴胡 46/60/68 → 41（大柴胡汤）
- api25 + migrate10 + parity1 测试全过

## 备份与回滚

- 白虎汤前备份 + 大柴胡汤前备份（`backups/tcm_knowledge-backup-20260629-*.db`，integrity ok）
- 回滚：停服 → 对应备份覆盖 → 重启

## 里程碑：机械性去重全部完成

桂枝汤(1) + 五组(5) + 5green(5) + 16green(16) + yellow(2) = **全部 27 组重名方剂去重完成**。
重名组 28→**0**。formulas 301（清洗前）→ **234**。

## 脱敏说明

本报告不含本机绝对路径；source 路径均为仓库内相对路径。

## 后续（未执行，本轮止步）

- clinical_cases 幂等 + 最小 ETL 入口
- 打 v0.2 版本
- 之后转 v0.3 推理 MVP
