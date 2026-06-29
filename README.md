# 🏥 倪海厦中医知识数据库 (TCM Knowledge Base)

基于倪海厦老师全套人纪/天纪课程体系构建的结构化中医知识数据库。

## 📊 数据规模

| 表 | 记录数 | 说明 |
|---|---|---|
| 中药 `herbs` | 472 | 神农本草经上中下三经 + 倪师/小编补充 + 临床用药 |
| 方剂 `formulas` | 234 | 伤寒论 + 金匮要略 + 汉唐方剂（27组重名已合并去重） |
| 症状 `symptoms` | 727 | 按全身/四肢/头面/胸腹/寒热/二便/脉象/舌象/睡眠分类 |
| 证型/病机 `syndromes` | 194 | 六经辨证 + 疾病机制 |
| 穴位 `acupoints` | 47 | 经络归属 + 功效 + 用法 |
| 医案 `clinical_cases` | 1,737 | 倪师2005-2008年诊疗记录 + 结构化医案 |
| 经典原文 `classics` | 113 | 黄帝内经73篇 + 伤寒论14篇 + 金匮要略26篇 |
| 课程笔记 `course_notes` | 121 | 六经/方证/症状/八纲/针灸/截图证据等 |
| 治法 `treatment_methods` | 119 | 疏肝/补肾/补血等治疗方法 |
| 讲座 `lectures` | 81 | 梁冬对话 + 扶阳论坛 + 仲景心法 + 闭门课 + 斯坦福 |
| 天纪 `tianji` | 185 | 易经 + 紫微斗数 + 堪舆 + 命理 |
| 书籍 `books` | 22 | 专题PDF(糖尿病/肝癌/乳癌/疫苗/经方等) |
| 妙方 `folk_formulas` | 17 | 社区经验方 |
| 课程 `courses` | 15 | 学习路径总览 |

**总计: 3,867 条记录 | 24.4 MB SQLite**

## 📁 文件说明

```
tcm-db/
├── tcm_knowledge.db    # SQLite 数据库（主文件）
├── schema_v2.sql       # 数据库 Schema
├── populate.py         # 数据填充脚本（需下载源仓库）
├── query_examples.py   # 查询示例代码
├── data_sources.json   # 数据来源记录
└── README.md
```

## 🗂️ 数据来源

| 来源 | Stars | 链接 | 贡献 |
|---|---|---|---|
| hantang-nihaixia-follower | ⭐280 | [GitHub](https://github.com/9527qingfeng/hantang-nihaixia-follower) | 中药/医案/经典/天纪/讲座 |
| JuneYaooo/nihaixia | ⭐90 | [GitHub](https://github.com/JuneYaooo/nihaixia) | 结构化课程笔记 |
| nihaixia-kb | ⭐3 | [GitHub](https://github.com/nivance/nihaixia-kb) | 医案/症状/穴位/病机/治法 |
| jangviktor-nihaixia | ⭐32 | [GitHub](https://github.com/jangviktor-web/nihaixia) | 分类医案/课程模块 |
| ebook-nihaixia | ⭐22 | [GitHub](https://github.com/elliott10/ebook-nihaixia) | 专题PDF |
| hantang-notes | ⭐2 | [GitHub](https://github.com/wdsheng999/hantang_medicine) | 针灸经络笔记 |
| renji-notes | ⭐8 | [GitHub](https://github.com/privateheart/renji) | 针灸大成笔记 |

## 🔍 快速查询示例

```python
import sqlite3

conn = sqlite3.connect('tcm_knowledge.db')
conn.row_factory = sqlite3.Row

# 搜索中药
rows = conn.execute("""
    SELECT name, category, nature, indication 
    FROM herbs WHERE name LIKE '%柴胡%' OR commentary LIKE '%柴胡%'
""").fetchall()

# 按六经查方剂
rows = conn.execute("""
    SELECT name, syndrome, differentiation, is_high_risk
    FROM formulas WHERE six_channel = '太阳'
""").fetchall()

# 搜索医案
rows = conn.execute("""
    SELECT patient_id, diagnosis, herbal_rx
    FROM clinical_cases WHERE disease_tags LIKE '%癌%'
""").fetchall()

# 搜索症状
rows = conn.execute("""
    SELECT name, category, description
    FROM symptoms WHERE name LIKE '%失眠%'
""").fetchall()

# 搜索穴位
rows = conn.execute("""
    SELECT name, meridian, indication
    FROM acupoints WHERE name LIKE '%足三里%'
""").fetchall()
```

## 🏗️ 数据库架构

### 核心实体
- `herbs` - 中药（神农本草经360味 + 补充）
- `formulas` - 方剂（伤寒论/金匮/汉唐/临床）
- `symptoms` - 症状（727种分类）
- `syndromes` - 证型/病机（194种）
- `acupoints` - 穴位（47个）
- `clinical_cases` - 医案（1449个）
- `classics` - 经典原文（113篇）

### 扩展实体
- `course_notes` - 课程笔记/蒸馏
- `treatment_methods` - 治法
- `lectures` - 讲座/对话
- `tianji` - 天纪（易经/命理）
- `books` - 书籍/专题
- `folk_formulas` - 妙方

### 关系表
- `formula_herbs` - 方剂↔药物
- `formula_syndromes` - 方剂↔证型
- `syndrome_symptoms` - 证型↔症状

## ⚠️ 免责声明

本数据库仅供中医学习和研究使用，不构成任何医疗建议。所有内容来源于公开的倪海厦老师课程资料和开源社区整理。如有健康问题，请咨询专业中医师。

## 📄 许可证

数据来源遵循各原始仓库的许可协议：
- hantang-nihaixia-follower: MulanPSL-2.0（木兰宽松许可证）
- 其他仓库: 请参考各自 LICENSE 文件

## 🔧 数据库构建状态（v0.2）

**`tcm_knowledge.db` 是权威产物**，随 git 提交，不可从源仓库完整重建：
- `populate.py build()` 是空壳（P1 工程债），**`--rebuild` 不可用**
- 历史 `formulas` 导入器缺失（脏名/去重的根因脚本未留存）
- 经多轮清洗（Phase0.5 名称清洗）+ 去重（27 组重名方剂合并）+ 安全加固，数据库为当前权威状态

### 可运行的 ETL 步骤

```bash
# 检查 clinical_cases 来源键状态（只读，不写入）
python3 scripts/etl.py --check
python3 scripts/etl.py --step check --dry-run

# 列出可用/受限步骤
python3 scripts/etl.py
```

- `check`：✅ 可用（报告来源键 NULL率/重复组/同文件多案冲突）
- `case-ingest`：⛔ BLOCKED — clinical_cases 无可靠稳定来源身份键（`raw_path` 同文件多案、`patient_id` 实为标题）。见 `docs/clinical-cases-idempotency-analysis.md`（方案 A/B/C 待决策）。未实施幂等导入，避免假幂等
- `formulas-ingest`：⛔ NOT IMPLEMENTED — 历史导入器缺失

### 重新部署服务

```bash
python3 -u server.py 8080   # 绑定 127.0.0.1，旧ID自动重定向到canonical
```
