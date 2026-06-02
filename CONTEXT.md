# 倪海厦中医知识数据库 - 项目上下文

## 一、项目概述

基于倪海厦老师全套人纪/天纪课程体系，从 GitHub 开源仓库抓取数据，构建的本地结构化中医知识数据库，并配有 Web 查询界面。

## 二、目录结构

```
~/tcm-project/
├── tcm-db/                          # 主项目（已推 GitHub: xiaogege6697/tcm-db）
│   ├── tcm_knowledge.db             # SQLite 数据库（5,800+条记录，35MB）
│   ├── schema_v2.sql                # 数据库 Schema（14个表 + 6个关系表）
│   ├── server.py                    # Web 查询界面（零依赖，Python标准库HTTPServer）
│   ├── populate.py                  # 数据构建脚本骨架
│   ├── query_examples.py            # 查询示例代码
│   ├── data_sources.json            # 7个数据来源记录
│   ├── README.md                    # 项目文档
│   ├── CONTEXT.md                   # 本文件
│   ├── screenshots -> nihaixia/assets/screenshots  # 符号链接，2986张WebP截图(78MB)
│   │
│   │── # 数据补全脚本
│   ├── enrich_clinical_cases.py     # 医案数据补全（nihaixia-kb）
│   ├── import_new_cases.py          # 导入新医案记录
│   ├── enrich_hantang_cases.py      # hantang仓库医案补全
│   ├── populate_formula_herbs.py    # 填充formula_herbs关系表
│   ├── populate_relationship_tables.py  # 填充所有关系表
│   ├── extract_pdf_content.py       # 提取PDF内容到books表
│   ├── enrich_courses.py            # 补全courses表
│   └── enrich_treatment_methods.py  # 补全treatment_methods分类
│
├── hantang-nihaixia-follower/       # 源仓库1 ⭐280（人纪教材+医案+天纪）
├── nihaixia/                        # 源仓库2 ⭐90（Agent Skill结构化笔记+截图证据）
├── new-repos/                       # 源仓库3-7
│   ├── nihaixia-kb/                 # ⭐3（4574个md，1981个结构化医案）
│   ├── jangviktor-nihaixia/         # ⭐32（按病种分类医案+课程模块）
│   ├── ebook-nihaixia/              # ⭐22（61个PDF，专题PDF已导入）
│   ├── hantang-notes/               # ⭐2（针灸经络笔记）
│   ├── renji-notes/                 # ⭐8（针灸大成笔记）
│   ├── nihaisha-pdfs/               # 跳过（重复）
│   ├── hantang-mirror/              # 跳过（英文官网）
│   ├── face-reading/                # 跳过（无内容）
│   ├── qintao-notes/                # 跳过（无内容）
│   └── tcm-masters/                 # 跳过（非倪海厦）
└── tcm-backup-20260601/             # 本地备份
```

## 三、数据库 Schema（14个表 + 6个关系表）

### 核心实体表
| 表名 | 字段说明 | 记录数 |
|------|---------|--------|
| `herbs` | name, category, nature, flavor, toxicity, meridian_tropism, origin, indication, bencao_raw, commentary | 472 |
| `formulas` | name, source_book, six_channel, syndrome, indication, composition, dosage, contraindication, differentiation, is_high_risk | 305 |
| `symptoms` | name, category, description, first_gateway, target_module, required_questions, differential(JSON) | 727 |
| `syndromes` | name, six_channel, eight_principles, location, core_symptoms, key_differentiation, representative_formulas, contraindication, description | 194 |
| `acupoints` | name, meridian, indication, technique | 47 |
| `clinical_cases` | case_date, patient_id, gender, age, chief_complaint, inquiry, pulse_diagnosis, tongue_diagnosis, eye_diagnosis, diagnosis, acupuncture_rx, herbal_rx, notes, disease_tags(JSON) | 1,737 |
| `classics` | book_name, chapter_name, content, word_count | 113 |
| `course_notes` | module_name, note_type, title, content, word_count | 121 |
| `treatment_methods` | name, category, description, related_pathomechanism, related_herbs, related_acupoints | 119 |
| `lectures` | title, speaker, lecture_type, content | 81 |
| `tianji` | title, category, content, word_count | 185 |
| `books` | title, author, category, content, format(md/pdf), word_count | 22 |
| `folk_formulas` | name, disease, composition, commentary | 17 |
| `courses` | name, order_num, total_hours, lesson_count, description, key_topics, content | 15 |

### 关系表（已填充）
| 表名 | 说明 | 记录数 |
|------|------|--------|
| `formula_herbs` | 方剂↔药物（含君臣佐使） | 239 |
| `formula_syndromes` | 方剂↔证型 | 19 |
| `syndrome_symptoms` | 证型↔症状 | 440 |
| `case_formulas` | 医案↔方剂 | 472 |
| `case_herbs` | 医案↔药物 | 2,342 |
| `course_course_notes` | 课程↔课程笔记 | 68 |

## 四、Web 服务器 (server.py)

### 启动方式
```bash
cd ~/tcm-project/tcm-db
python3 server.py 8080
# 浏览器打开 http://localhost:8080
```

### 技术栈
- 零依赖，仅用 Python 标准库（http.server, sqlite3, json）
- HTML/CSS/JS 全部内嵌在 server.py 的 HTML_TEMPLATE 变量中
- 暖色调中医风格 UI

### API 端点
| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | HTML 页面 |
| `/api/stats` | GET | 各表统计 |
| `/api/search?q=关键词` | GET | 全库搜索（跨9个表） |
| `/api/browse?table=表名&page=1&filter_col=value` | GET | 分页浏览+筛选 |
| `/api/detail/表名/id` | GET | 单条详情（含关联数据） |
| `/api/filter/表名/列名` | GET | 获取筛选选项 |
| `/api/export/表名?format=json\|csv` | GET | 导出表数据 |
| `/api/export/search?q=关键词&format=json\|csv` | GET | 导出搜索结果 |
| `/screenshots/xxx.webp` | GET | 截图静态文件服务 |

### 已实现功能
- ✅ 全库搜索（跨9个表）
- ✅ 分类浏览 + 筛选（六经/性味/来源/经络等）
- ✅ 详情面板（右侧滑出，含关联数据）
- ✅ 分页
- ✅ 截图静态文件服务
- ✅ render_markdown 函数（支持截图路径渲染为<img>标签）
- ✅ 关系数据显示（药物、方剂、证型、症状、医案、课程资料）
- ✅ 可点击的关联标签
- ✅ 数据导出功能（JSON/CSV）
- ✅ 搜索结果可点击查看详情

### 关联数据显示
- **方剂详情**：显示相关药物（带性味）和证型
- **医案详情**：显示相关方剂和药物
- **药物详情**：显示相关方剂和医案
- **证型详情**：显示相关方剂和症状
- **症状详情**：显示相关证型
- **课程详情**：显示关联的课程资料

## 五、数据补全状态

### 医案数据补全
| 字段 | 初始 | 最终 | 改善 |
|------|------|------|------|
| inquiry | 0 | 732 | +732 |
| pulse_diagnosis | 0 | 834 | +834 |
| tongue_diagnosis | 46 | 690 | +644 |
| eye_diagnosis | 0 | 353 | +353 |
| herbal_rx | 466 | 796 | +330 |
| acupuncture_rx | 96 | 427 | +331 |

### 其他表补全
- ✅ **books 表**：提取 10 本 PDF 内容（2,857,297 字符），补充 3 本书的作者和分类
- ✅ **courses 表**：补充 7 门课程的描述、主题和内容摘要
- ✅ **treatment_methods 表**：补全 119 条治法的分类

## 六、数据来源详情

| 仓库 | Stars | 贡献 |
|------|-------|------|
| 9527qingfeng/hantang-nihaixia-follower | ⭐280 | 中药349+医案708+经典113篇+天纪181+讲座42+妙方17+汉唐方剂102 |
| JuneYaooo/nihaixia | ⭐90 | 课程笔记46篇（六经/方证/症状/八纲/截图证据等） |
| nivance/nihaixia-kb | ⭐3 | 医案679+症状708+穴位47+药物52+病机188+治法119+方剂39+理论37+针灸7+讲座39 |
| jangviktor-web/nihaixia | ⭐32 | 医案62（癌/心血管/代谢/自免/神经）+课程模块9 |
| elliott10/ebook-nihaixia | ⭐22 | 专题PDF14个（糖尿病/肝癌/乳癌/疫苗/经方/紫微等） |
| wdsheng999/hantang_medicine | ⭐2 | 针灸经络笔记17篇 |
| privateheart/renji | ⭐8 | 针灸大成笔记5篇 |

## 七、下一步开发方向

1. **接入LLM** — RAG模式，搜索结果喂给大模型做辨证推理
2. **移动端适配** — 优化移动端显示
3. **性能优化** — 添加缓存机制
4. **关系图展示** — 可视化药物-方剂-证型-症状关系网络
5. **学习路径** — 按六经辨证体系组织学习路径
6. **症状→证型→方剂** 推理链路

## 八、关键注意事项

1. **药名古名**：神农本草经用古名，如"茈胡"=柴胡，搜索时需同时搜古名和今名
2. **FTS5不支持中文**：SQLite FTS5 默认分词器不支持中文，搜索用 LIKE 替代
3. **PDF导入**：已用 PyMuPDF (fitz) 导入21个PDF到 books 表（20个有内容）
4. **截图是符号链接**：screenshots/ -> nihaixia/assets/screenshots/，部署时需注意路径
5. **数据库已推GitHub**：tcm_knowledge.db (35MB) 已在仓库中
6. **所有脚本零外部依赖**：仅用 Python 标准库
7. **URL编码**：中文搜索需要URL编码（如"桂枝" -> "%E6%A1%82%E6%9E%9D"）

## 九、运行记录

### 2026-06-01 主要工作
1. 修复截图显示问题（content_html字段渲染）
2. 医案数据补全（+288条新记录，+842条更新）
3. 填充所有关系表（formula_herbs, formula_syndromes, syndrome_symptoms, case_formulas, case_herbs, course_course_notes）
4. Web界面增强（关联数据显示、数据导出、搜索结果可点击）
5. 补全其他表（books PDF内容、courses描述、treatment_methods分类）
