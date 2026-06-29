# clinical_cases 幂等可行性分析（只读证据）· 2026-06-29

> v0.2 收口：评估 clinical_cases 导入幂等。**结论：当前数据无可靠稳定来源身份键，按指令停止实施幂等导入，提交证据与推荐方案，不自行猜测。**

## 一、写入路径（只读确认）

- **唯一 INSERT 点**：`import_new_cases.py:325` `INSERT INTO clinical_cases (...)`（裸 INSERT，无 OR IGNORE / 无 UNIQUE 依赖）
- 补字段路径：`enrich_clinical_cases.py:365` / `enrich_hantang_cases.py:241` 均为 `UPDATE`（按 id 补充字段，不新增行）
- 结论：新增行只来自 `import_new_cases.py`，幂等问题集中在该路径。

## 二、schema 来源字段

```
clinical_cases(id PK AUTOINCREMENT, case_date, patient_id, gender, age,
  chief_complaint, inquiry, ..., raw_path, source_repo)
-- 索引：idx_cases_date(case_date) / idx_cases_diag(diagnosis)  —— 均普通索引，无 UNIQUE
```

来源字段仅 `source_repo` + `raw_path`（无 source_path / source_locator / 文件内锚点）。

## 三、候选稳定键评估（总 1737 行）

| 候选键 | 非空 | 重复组 | 判定 |
|---|---|---|---|
| `source_repo` | 1737/1737 | — | 仅 2-3 个仓库，非身份键 |
| `raw_path` | 1449/1737（**288 空**） | 4 | **不可用**：同文件多案 |
| `patient_id` | 1737/1737 | **199** | **不可用**：实为标题/分类名 |
| `(source_repo, raw_path)` | — | 4 | 同 raw_path 问题 |
| `(source_repo, raw_path, patient_id)` | — | **2** | 三元组仍冲突 |

### 关键冲突证据（同来源键 + 内容不同）
- `jangviktor / cases/01_cancer.md`：**13 行 / 13 个 distinct 主诉**（一个 .md 是多案合集）
- `jangviktor / cases/02_cardiovascular.md`：7 行 / 7 distinct
- `jangviktor / cases/03_metabolic.md`：6 行 / 5 distinct

### patient_id 语义证据（非身份键）
- hantang：patient_id = 案标题（如 "080902精子太稀-鼻窦-失眠-高胆固醇"），一文件一案时近似唯一
- jangviktor：patient_id = 分类占位（"核心要点提炼"重复 19 次、"060" 重复 18 次），同标题多案
- patient_id 字段名误导：实际是"主诉/标题"，不是稳定患者身份 ID

## 四、结论：无可靠稳定来源身份键

- raw_path 是**文件级**，但 jangviktor 来源是"一文件多案合集"→ 同 raw_path 对应多个不同 case
- patient_id 是**标题级**，重复严重，非身份
- 三元组仍有 2 组冲突
- 无 UNIQUE 约束、无文件内锚点/序号

**因此无法构造"同来源 = 同 case"的等价键**。任何基于现有字段的 INSERT OR IGNORE / UNIQUE 都会是**假幂等**（要么误并同文件多案，要么漏判同案更新）。

## 五、推荐方案（供决策，未自行实施）

### 方案 A（推荐·根本）：源数据补稳定身份键
- jangviktor 合集文件：导入时为每个 case 生成文件内序号/锚点（如 `raw_path#case_idx`），写入新列 `source_locator`
- hantang 一文件一案：raw_path 本身即身份（补 288 空值后可用）
- 代价：需新列 + 改导入器 + 回填现有 1737 行；但获得真稳定键
- 之后幂等：`UNIQUE(source_repo, source_locator)` 真约束

### 方案 B（workaround·局限大）：内容指纹
- 键 = `(source_repo, raw_path, sha256(canonical(chief_complaint+diagnosis+inquiry+herbal_rx+...)))`
- 同 repo+raw_path+同内容 → skip；不同内容 → 视为不同 case 各自 insert
- **局限（必须记录）**：
  1. 内容微调（修正一个错字）= 新指纹 = 视为新案 → 重复插入，**无法识别"同案更新"**
  2. 无法满足"同来源内容变化报告 conflict 不覆盖"——因无身份键判断"同 case"，只能"不同内容=不同案"
  3. 不删不合并现有行，但重跑可能对历史微调产生重复
- 适用：源数据冻结、仅防"完全相同重复导入"

### 方案 C（现状）：保持裸 INSERT + 人工去重
- 不幂等；重跑会重复；依赖人工
- 仅作过渡

## 六、本轮处置（按指令停止）

- ❌ **未实施** clinical_cases 幂等修复（无可靠键，避免假幂等）
- ❌ **未实现** etl.py 的 case-ingest 写入（同上）
- ✅ 提供 `scripts/etl.py --check`：报告来源键状态（NULL 率/重复组/同文件多案冲突），供决策
- ✅ 未删除/合并任何现有 clinical_cases（1737 行不变）
- 待你裁定 A/B/C 后再实施幂等导入

## 七、规则遵守
- 只用本地 db + 来源记录，不凭模型常识
- 未自行猜测键；未强行假幂等
- 现有疑似重复医案（758/759 等）未清理
