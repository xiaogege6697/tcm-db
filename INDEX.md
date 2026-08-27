# tcm-db 倪海厦中医知识数据库 — INDEX

<!-- tags: 倪海厦/中医, 倪海厦/方剂, 倪海厦/医案, 来源/语料, 入库/2026-08-26 -->

- **来源**：github.com/xiaogege6697/tcm-db（主人仓库，git clone 正本，更新走 git pull）
- **入库**：2026-08-26，46M（SQLite 主文件 33.6M）
- **形态**：结构化 SQLite（tcm_knowledge.db，29表）+ Python 脚本，**非 MD 语料库**

## 内容规模（实测核对与 README 一致）
- 中药 472 / 方剂 234 / 症状 727 / 证型 194 / 穴位 47
- 医案 1737 / 经典原文 113（内经73+伤寒14+金匮26）/ 课程笔记 121 / 治法 119
- 讲座 81 / 天纪 185（易经紫微堪舆命理）/ 书籍PDF专题 22 / 妙方 17 / 课程 15
- 总计 3867 条

## 使用方式
- 查询：`sqlite3 tcm_knowledge.db "select ..."`；示例见 query_examples.py
- 上游数据来自 7 个开源 nihaixia 仓库（来源清单在 README/data_sources.json）
- schema：schema_v2.sql（v2）
- 图片库（2026-08-26 补）：assets/screenshots/ 2987张原书截图，11模块目录（金匮656/伤寒649/天纪527/针灸501/内经272/本草127/医案88/仲景心法/扶阳/八纲/易筋经），与库内 *-screenshot-evidence.md 文字描述一一对应，源：JuneYaooo/nihaixia

## 标签表（本库受控词表）
倪海厦/中药 · 倪海厦/方剂 · 倪海厦/医案 · 倪海厦/经典 · 倪海厦/针灸 · 倪海厦/天纪

## 注意
- 医疗内容仅供学习研究，不构成诊疗建议
- .git 保留（主人仓库，便于 pull 更新）
