# 桂枝汤去重 dry-run 报告（试点，未执行）

> **状态：DRY-RUN，未写库。** 待你确认后才按 runbook 执行。
> canonical_id = **209**（nihaixia 版，带 six_channel）

---

## 1. 五行完整字段

| 字段 | id8 | id9 | id15 | id28 | id209 ⭐canonical |
|---|---|---|---|---|---|
| source_book | 伤寒论 | 伤寒论 | 伤寒论 | 伤寒论 | （空） |
| chapter | 3.上篇 | 3.上篇 | 3.上篇 | **4.中篇** | （空） |
| six_channel | 空 | 空 | 空 | 空 | **太阳** |
| syndrome | 空 | 空 | 空 | 空 | **太阳中风,有汗恶风脉缓;解肌调营卫** |
| composition | 桂枝,白芍,炙甘草,生姜,大枣 | 同 | 同 | 同 | 同 |
| dosage | 空 | | | | 空 |
| indication | 空 | | | | 空 |
| differentiation | 空 | | | | **与麻黄汤分水岭是有汗/无汗;酒客吐家胸满需慎** |
| contraindication | 空 | | | | 空 |
| is_high_risk | 0 | 0 | 0 | 0 | 0 |
| source_repo | hantang | hantang | hantang | hantang | nihaixia |
| raw_path | …/3.上篇.md | …/3.上篇.md | …/3.上篇.md | …/4.中篇.md | references/formula-patterns.md |

> 注：**id 8/9/15 三条 raw_path 完全相同**（同一文件被导入 3 次 = 真重复，ETL bug）；id28 是中篇复提；id209 是 nihaixia 结构化版。

## 2. canonical 选择
- canonical_id = **209**，理由 = **rule1（带 six_channel 的 nihaixia 版）**
- 209 是唯一带六经(太阳)+证型+鉴别的版本，信息最完整。

## 3. 关联数量（迁移量）

| id | formula_herbs | formula_syndromes | case_formulas |
|---|---|---|---|
| 8 | 5 | 0 | 0 |
| 9 | 5 | 0 | 0 |
| 15 | 5 | 0 | 0 |
| 28 | 5 | 0 | 0 |
| **209 (canonical)** | 5 | 1 | 13 |

**迁移**：8/9/15/28 的 formula_herbs 共 **20 条** → `INSERT OR IGNORE` 到 209（药味相同，IGNORE）→ 删 20 条。
formula_syndromes / case_formulas：非 canonical 行均为 0，无需迁移。

## 4. 字段合并计划（canonical=209 基础上）

| 字段 | 动作 | 依据 |
|---|---|---|
| composition | 不变 | 5 行完全一致 |
| six_channel / syndrome / differentiation | 保留 209 值 | 其他全空 |
| source_book | **补入「伤寒论」** | canonical 空，其他非空且一致 → 补 |
| chapter | ⚠️ **冲突，待裁定** | 8/9/15=上篇, 28=中篇, 209=空 |
| 其余字段 | 保持空 | 全空 |

## 5. 字段冲突（1 处，非医学）

**chapter 冲突**：值A「3.辨太阳病脉证并治法上篇」← id8/9/15 ；值B「4.辨太阳病脉证并治法中篇」← id28 ；canonical(209) 空。

> ✅ **医学语义字段冲突：0 处**（composition/dosage/indication/six_channel/syndrome/differentiation 均无多版本冲突）→ 合并不丢失任何医学信息。

**chapter 裁定建议**：桂枝汤正条见《伤寒论》第 12 条（"太阳中风，阳浮而阴弱……桂枝汤主之"），位于**上篇**；中篇(28) 为后续条文复提。**建议 canonical chapter 取「上篇」**，中篇出处记入 evidence(source_record)。→ 需你确认。

## 6. 预计写入 evidence（source_record，非推理证据）

删除 8/9/15/28 前，将其来源信息保留到 evidence 表（本次迁移标 `source_record`，**不标推理证据**）：

| 来自原 id | source_repo | source_quote（保留内容） |
|---|---|---|
| 8 | hantang | raw_path=…/3.上篇.md |
| 9 | hantang | raw_path=…/3.上篇.md（与 8 同文件，真重复） |
| 15 | hantang | raw_path=…/3.上篇.md（与 8 同文件，真重复） |
| 28 | hantang | raw_path=…/4.中篇.md（chapter 冲突方，保留中篇出处） |

> ⚠️ evidence 表尚需创建（Schema 迁移，需你确认 DDL）。试点可先暂存为 JSON，evidence 表建立后回填。

## 7. 迁移与删除数量

| 项 | 数量 |
|---|---|
| 迁移关系 formula_herbs | 20（INSERT OR IGNORE 到 209，实际 IGNORE） |
| 删除 formula_herbs | 20（8/9/15/28 的） |
| 删除 formulas | 4 行（8/9/15/28） |
| 桂枝汤最终 | 1 行（209） |

## 8. 迁移前后对账预期（见 runbook 第 3 节 SQL）

| 指标 | before | after（期望） |
|---|---|---|
| formulas 桂枝汤行数 | 5 | **1** |
| 桂枝汤 distinct herbs | 5 | **5（一致）** |
| 桂枝汤 distinct cases | 13 | **13（一致）** |
| 旧 id(8/9/15/28) 关系表引用 | 20 | **0** |
| foreign_key_check | 空 | 空 |
| integrity_check | ok | ok |

## 9. 待你确认
1. canonical = 209 ✓？
2. chapter 冲突：取**上篇（建议）** / 中篇 / 留空？
3. evidence 表：试点先暂存 JSON，还是执行前先建表（我会先展示 DDL 让你过目）？
4. 确认后我按 runbook：停服 → backup → 事务迁移（整组 ROLLBACK 兜底）→ 对账 → 重启。
