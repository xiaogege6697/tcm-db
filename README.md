# 🏥 倪海厦中医知识数据库 (TCM Knowledge Base)

> 目前开源社区**最全的倪海厦课程结构化数据库**：11 册课程板书 2,987 张逐张 OCR 转录 + 3,867 条结构化知识记录 + 倪师辨证思维 skill（AI 问诊逻辑）+ 可审计的 SQLite 数据底座。

## 🧠 灵魂搭档：nihaixia-perspective 思维分身

本库不只是「原文弹药库」，还配套一个 **AI 辨证思维分身**（`skills/nihaixia-perspective/`）：从本库 3,867 条记录蒸馏出的倪师思维方式——三层架构（易为体 → 医理转译 → 临床为用）、病势演进轴、阳不入阴、水循环气化、十二时辰流注等辨证推理框架，可直接作为 Claude/LLM 的 system prompt 使用。

**原文数据库 + 问诊逻辑 = 相辅相成**：分身管脑子（怎么辨证思考），数据库管弹药（药性/方剂/医案原文），每条思维都带原文锚点可回库溯源。接入方法见该目录下 `SKILL.md`。

## ✨ 为什么值得一看

- **逐张 OCR 的板书全文库**：人纪/天纪 11 册课程的 2,987 张原书板书截图，每张都完成 OCR 转录，`assets/transcripts/` 下按册整理为 Markdown，**转录与原书截图页码一一对应**，可原文定位、可校对。
- **结构化 + 可审计**：中药/方剂/症状/证型/医案全部入库 SQLite，带 schema、去重证据链（evidence 表）和旧 ID 重定向，不是一堆散落的文本。
- **为 AI 检索而生**：附 RAG/LLM 检索提示词模板（见下文），直接喂给任意大模型即可构建倪海厦中医问答库。
- **来源全部可溯**：7 个开源仓库来源记录在 `data_sources.json`，每条数据可回查。

## 📊 数据规模

| 表 | 记录数 | 说明 |
|---|---|---|
| 中药 `herbs` | 472 | 神农本草经上中下三经 + 倪师/小编补充 + 临床用药 |
| 方剂 `formulas` | 234 | 伤寒论 + 金匮要略 + 汉唐方剂（27 组重名已合并去重） |
| 症状 `symptoms` | 727 | 按全身/四肢/头面/胸腹/寒热/二便/脉象/舌象/睡眠分类 |
| 证型/病机 `syndromes` | 194 | 六经辨证 + 疾病机制 |
| 穴位 `acupoints` | 47 | 经络归属 + 功效 + 用法 |
| 医案 `clinical_cases` | 1,737 | 倪师 2005-2008 年诊疗记录 + 结构化医案 |
| 经典原文 `classics` | 113 | 黄帝内经 73 篇 + 伤寒论 14 篇 + 金匮要略 26 篇 |
| 课程笔记 `course_notes` | 121 | 六经/方证/症状/八纲/针灸/截图证据等 |
| 治法 `treatment_methods` | 119 | 疏肝/补肾/补血等治疗方法 |
| 讲座 `lectures` | 81 | 梁冬对话 + 扶阳论坛 + 仲景心法 + 闭门课 + 斯坦福 |
| 天纪 `tianji` | 185 | 易经 + 紫微斗数 + 堪舆 + 命理 |
| 书籍 `books` | 22 | 专题 PDF（糖尿病/肝癌/乳癌/疫苗/经方等） |
| 妙方 `folk_formulas` | 17 | 社区经验方 |
| 课程 `courses` | 15 | 学习路径总览 |

**总计：3,867 条记录 | 24.4 MB SQLite | 11 册板书转录（assets/transcripts/）+ 2,987 张原书截图（assets/ 下按册归档）**

## 📚 板书转录库（本库独有）

`assets/transcripts/` 收录 11 册课程转录（Markdown，按页分节）：

`伤寒论`(649页) · `金匮要略`(656页) · `天机`(527页) · `针灸` · `本草` · `黄帝内经` · `八纲` · `扶阳` · `易筋经` · `仲景心法` · `临床案例`

OCR 采用「本地 HunyuanOCR 打头阵 + 云端视觉模型兜底」双轨方案：规整板书本地近乎满分，图示页与极端行草由云端补齐。转录管线说明见 `docs/transcript-pipeline.md`。

> ⚠️ 板书截图体积较大，本仓库提供全部转录文本；截图库可按 `data_sources.json` 中的源仓库获取，或按需 issue 联系。

## 🚀 快速开始

```bash
git clone https://github.com/xiaogege6697/tcm-db.git
cd tcm-db
sqlite3 tcm_knowledge.db "SELECT name FROM sqlite_master WHERE type='table';"
```

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
```

更多示例见 `query_examples.py`；本地查询服务 `python server.py`（只读 API，绑定 127.0.0.1）。

## 🤖 LLM 检索提示词模板（RAG 建议）

把本库作为知识源接入任意大模型时，推荐以下提示词骨架：

**1. 经方检索助手（用 formulas/syndromes 表）**

```text
你是倪海厦经方检索助手。基于以下数据库表结构回答：
formulas(name, syndrome, differentiation, herbs, six_channel, is_high_risk)
用户提问："{症状描述}"
要求：① 先辨证归六经 ② 给出候选方剂及辨证要点 ③ 标注 is_high_risk 项需医师确认
回答末尾附上所查记录的来源表与字段，便于核对。
```

**2. 医案对照检索（用 clinical_cases 表）**

```text
你是医案检索助手。在 clinical_cases(诊断, 病症标签, 处方, 疗效) 中检索与「{疾病/症状}」相似的医案，
输出：患者概况 → 诊断 → 处方 → 疗效转归，并总结倪师治疗该类疾病的共性思路（用药习惯、加减法）。
```

**3. 板书原文定位（用 assets/transcripts/）**

```text
在伤寒论转录(shanghanlun.md, 649页)中查找与「{关键词，如：结胸、藏结}」相关的条文讲解，
返回：原文摘录 + 页码，页码格式 "p0434" 可直接对应原书截图核对。
```

**4. 中药性味查询（用 herbs 表）**

```text
查询 herbs 表中「{药名}」的性味、归经、功效与倪师讲解要点(commentary)，
若有神农本草经原文请区分标注「本经原文」与「倪师注解」。
```

**5. 学习路径规划（用 courses/course_notes 表）**

```text
我是{背景，如：零基础爱好者/有西医基础}，请基于 courses 表的课程体系和 course_notes 的笔记，
给我规划一条倪海厦课程学习路径，标注每门课的先修关系与重点章节。
```

**安全提示词（建议追加在系统提示尾部）**：

```text
本知识库仅供学习研究。所有方剂剂量与用药建议必须提示"请咨询专业中医师"，
is_high_risk=1 的方剂（如含附子/乌头类）禁止给出具体剂量。
```

## 🗂️ 数据来源

| 来源 | Stars | 链接 | 贡献 |
|---|---|---|---|
| hantang-nihaixia-follower | ⭐280 | [GitHub](https://github.com/9527qingfeng/hantang-nihaixia-follower) | 中药/医案/经典/天纪/讲座 |
| JuneYaooo/nihaixia | ⭐90 | [GitHub](https://github.com/JuneYaooo/nihaixia) | 结构化课程笔记 + 板书截图源 |
| nihaixia-kb | ⭐3 | [GitHub](https://github.com/nivance/nihaixia-kb) | 医案/症状/穴位/病机/治法 |
| jangviktor-nihaixia | ⭐32 | [GitHub](https://github.com/jangviktor-web/nihaixia) | 分类医案/课程模块 |
| ebook-nihaixia | ⭐22 | [GitHub](https://github.com/elliott10/ebook-nihaixia) | 专题 PDF |
| hantang-notes | ⭐2 | [GitHub](https://github.com/wdsheng999/hantang_medicine) | 针灸经络笔记 |
| renji-notes | ⭐8 | [GitHub](https://github.com/privateheart/renji) | 针灸大成笔记 |

## 🏗️ 数据库架构

- **核心实体**：`herbs` / `formulas` / `symptoms` / `syndromes` / `acupoints` / `clinical_cases` / `classics`
- **扩展实体**：`course_notes` / `treatment_methods` / `lectures` / `tianji` / `books` / `folk_formulas` / `courses`
- **关系表**：`formula_herbs`（方剂↔药物）/ `formula_syndromes`（方剂↔证型）/ `syndrome_symptoms`（证型↔症状）
- **审计设施**：`evidence`（字段级来源证据）/ `ingestion_quarantine`（脏数据隔离）/ 旧 ID 重定向缓存

Schema 详见 `schema_v2.sql`；数据管线见 `populate.py` 与 `docs/transcript-pipeline.md`。

## 📁 目录速览

```
tcm-db/
├── tcm_knowledge.db      # SQLite 数据库（权威产物）
├── schema_v2.sql         # Schema
├── assets/transcripts/   # 11 册板书 OCR 转录（Markdown，按页分节）
├── skills/nihaixia-perspective/  # 倪师辨证思维分身（AI system prompt，蒸馏自本库）
├── 谱系/                  # 知识谱系参考卡（紫极等对照体系，带 books.id 溯源）
├── populate.py           # 数据填充脚本（需下载源仓库）
├── query_examples.py     # 查询示例代码
├── server.py             # 本地只读查询 API
├── docs/                 # 核心契约 + 转录管线文档
├── data_sources.json     # 数据来源记录
└── CHANGELOG.md          # 变更日志（含 DB SHA-256 校验）
```

## ⚠️ 免责声明

本数据库仅供中医学习和研究使用，不构成任何医疗建议。所有内容来源于公开的倪海厦老师课程资料和开源社区整理。如有健康问题，请咨询专业中医师。

## 🧭 维护核心

本项目的出发点是**可查询、可审计、可继续维护**的中医资料数据底座，而不是自动诊断或处方系统。详细边界见 [`docs/project-core-contract.md`](docs/project-core-contract.md)。

## 📄 License

数据与代码遵循各源仓库许可；本仓库整理成果以 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh) 提供（非商业、署名、相同方式共享）。
