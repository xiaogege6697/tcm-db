# 16 green 机械去重收口报告 · 2026-06-29

> 通用脚本 `migrate_formula_dedup.py migrate` 两批单事务，**机械性去重全部完成**。
> 接续：桂枝汤 + 五组 + 5green(关系链验证) 之后，剩余16 green 按批收口。

## 摘要

16 green 分两批各 8 组，20 旧id → 16 canonical。重名组 18→**2**（只剩白虎汤 + 大柴胡汤两 yellow）。

## 批1（8组，删10旧id）

| 方剂 | 旧id（删） | canonical |
|---|---|---|
| 四逆散 | 103, 104 | 264 |
| 桃核承气汤 | 48, 58 | 235 |
| 吴茱萸汤 | 56 | 99 |
| 干姜黄连黄芩人参汤 | 4 | 3 |
| 承气汤 | 69 | 29 |
| 旋覆代赭汤 | 5 | 239 |
| 柴胡桂枝汤 | 62 | 231 |
| 桂枝人参汤 | 71 | 238 |

## 批2（8组，删10旧id）

| 方剂 | 旧id（删） | canonical |
|---|---|---|
| 猪苓汤 | 81, 87 | 249 |
| 葛根汤 | 17, 20 | 215 |
| 桂枝加芍药汤 | 92 | 251 |
| 桂枝加葛根汤 | 10 | 210 |
| 桂枝麻黄各半汤 | 11 | 213 |
| 甘草干姜汤 | 55 | 292 |
| 附子汤 | 97 | 96 |
| 麻子仁丸 | 89 | 248 |

## 执行（通用脚本两批单事务）

每批：备份 → dry-run → migrate 单事务 → 对账。批1 后保持停服继续批2；两批后统一 `python3 -u` 重启。

## 数据变化

| 指标 | 前（5green后） | 后 |
|---|---|---|
| formulas | 262 | **242** |
| 重名组 | 18 | **2**（白虎汤+大柴胡汤）|
| evidence | 81 | **106** |
| quarantine | 14 | 14 |

evidence 分类：merged_from 29→49（+20）/ field_value 18→23（+5，批1四+批2一）/ normalized_from 34（迁移改 subject 无损）。

## 对账（全部通过）

- 20旧id 仍存 formulas: 0
- 20旧id 作 subject/object: 0
- 20旧id 关系引用（动态扫描所有 FK→formulas 表）: 0
- merged_from: 49 完整 / normalized_from: 34 无损 / field_value: 23
- foreign_key_check: 空 / integrity_check: ok
- audit_db.py: **hard=0，Evidence 多态引用 PASS，duplicates=2**

## HTTP 验证

server PID 42996（`python3 -u`, 127.0.0.1:8080），redirect map **49 条**。**全部49旧id HTTP 200 重定向到 canonical**。
api25 + migrate10 + parity1 测试全过。

## 备份与回滚

- 批1前备份 + 批2前备份（`backups/tcm_knowledge-backup-20260629-*.db`，integrity ok）
- 回滚：停服 → 批1备份覆盖（回到5green后）或 批2备份覆盖（回到批1后）→ 重启

## 机械性去重收口完成

桂枝汤(1) + 五组(5) + 5green(5) + 本批(16) = 全部 green 完成。
只剩 **2 yellow**（白虎汤迁12 / 大柴胡汤迁11）待人裁定（关系迁移量大，字段合并需人判断）。
通用脚本 `migrate_formula_dedup.py migrate` 经多批验证，可承担后续 yellow 裁定后的迁移。

## 脱敏说明

本报告不含本机绝对路径。

## 后续（未执行，本轮止步）

- 2 yellow 裁定（白虎汤/大柴胡汤）
- clinical_cases 幂等 + 最小 ETL 入口
- 打 v0.2 版本
