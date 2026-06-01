# 倪海厦中医知识数据库 - 项目上下文

## 一、项目概述

基于倪海厦老师全套人纪/天纪课程体系，从 GitHub 开源仓库抓取数据，构建的本地结构化中医知识数据库，并配有 Web 查询界面。

## 二、目录结构

```
~/tcm-project/
├── tcm-db/                          # 主项目（已推 GitHub: xiaogege6697/tcm-db）
│   ├── tcm_knowledge.db             # SQLite 数据库（3,867条记录，24.4MB）
│   ├── schema_v2.sql                # 数据库 Schema（14个表 + 5个关系表）
│   ├── server.py                    # Web 查询界面（零依赖，Python标准库HTTPServer）
│   ├── populate.py                  # 数据构建脚本骨架
│   ├── query_examples.py            # 查询示例代码
│   ├── data_sources.json            # 7个数据来源记录
│   ├── README.md                    # 项目文档
│   ├── CONTEXT.md                   # 本文件
│   └── screenshots -> nihaixia/assets/screenshots  # 符号链接，2986张WebP截图(78MB)
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

## 三、数据库 Schema（14个表）

### 核心实体表
| 表名 | 字段说明 | 记录数 |
|------|---------|--------|
| `herbs` | name, category(上经/中经/下经/倪师补充/小编补充/医案补充), nature(寒热温凉平), flavor(酸苦甘辛咸), toxicity, meridian_tropism, origin, indication, bencao_raw(本经原文), commentary(全文讲解) | 472 |
| `formulas` | name, source_book(伤寒论/金匮要略/汉唐方剂/临床记录), six_channel(太阳/阳明/少阳/太阴/少阴/厥阴), syndrome, indication, composition, dosage, contraindication, differentiation, is_high_risk | 305 |
| `symptoms` | name, category(全身/四肢/头面/胸腹/寒热/二便/脉象/舌象/睡眠等), description, first_gateway(分水岭), target_module, required_questions, differential(JSON) | 727 |
| `syndromes` | name, six_channel, eight_principles, location, core_symptoms, key_differentiation, representative_formulas, contraindication, description（也存病机） | 194 |
| `acupoints` | name, meridian, indication, technique(用法备注) | 47 |
| `clinical_cases` | case_date, patient_id, gender, age, chief_complaint, inquiry, pulse_diagnosis, tongue_diagnosis, eye_diagnosis, diagnosis, acupuncture_rx, herbal_rx, notes, disease_tags(JSON) | 1449 |
| `classics` | book_name(黄帝内经/伤寒论/金匮要略), chapter_name, content(全文), word_count | 113 |
| `course_notes` | module_name, note_type(六经辨证/方证/症状索引/课程蒸馏/截图证据/经络笔记/学习笔记/理论), title, content(全文) | 121 |
| `treatment_methods` | name, description, related_pathomechanism, related_herbs, related_acupoints | 119 |
| `lectures` | title, speaker, lecture_type(对话/论坛/心法/闭门课/演讲), content | 81 |
| `tianji` | title, category(易经/紫微斗数/堪舆/命理/天机道), content | 185 |
| `books` | title, author, category, content, format(md/pdf) | 22 |
| `folk_formulas` | name, disease, composition, commentary | 17 |
| `courses` | name, order_num, total_hours, lesson_count | 15 |

### 关系表（空，待建联）
| 表名 | 说明 |
|------|------|
| `formula_herbs` | 方剂↔药物（含君臣佐使） |
| `formula_syndromes` | 方剂↔证型 |
| `syndrome_symptoms` | 证型↔症状 |
| `case_formulas` | 医案↔方剂 |
| `case_herbs` | 医案↔药物 |

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
| `/api/search?q=关键词` | GET | 全库搜索（搜中药/方剂/症状/穴位/医案/病机/治法/经典/讲座） |
| `/api/browse?table=表名&page=1&filter_col=value` | GET | 分页浏览+筛选 |
| `/api/detail/表名/id` | GET | 单条详情（长文本字段会渲染为HTML） |
| `/api/filter/表名/列名` | GET | 获取筛选选项 |
| `/screenshots/xxx.webp` | GET | 截图静态文件服务 |

### 已实现功能
- ✅ 全库搜索（跨9个表）
- ✅ 分类浏览 + 筛选（六经/性味/来源/经络等）
- ✅ 详情面板（右侧滑出）
- ✅ 分页
- ✅ 截图静态文件服务
- ✅ render_markdown 函数（支持截图路径渲染为<img>标签）

### 截图渲染机制
课程笔记中的截图引用格式为：`截图路径：assets/screenshots/shanghanlun/0001.webp`
render_markdown 函数将其转换为：`<img src="/screenshots/shanghanlun/0001.webp" ...>`
共 2986 张 WebP 截图，78MB，通过符号链接接入。

### 待完善
- 🔲 详情面板中的 Markdown 渲染需要在浏览器端验证（JS 的 showDetail 函数使用 content_html 字段）
- 🔲 搜索结果点击后应跳转到对应表的详情
- 🔲 移动端适配优化
- 🔲 关系表数据为空，需要建立方剂↔药物等关联

## 五、数据来源详情

| 仓库 | Stars | 贡献 |
|------|-------|------|
| 9527qingfeng/hantang-nihaixia-follower | ⭐280 | 中药349+医案708+经典113篇+天纪181+讲座42+妙方17+汉唐方剂102 |
| JuneYaooo/nihaixia | ⭐90 | 课程笔记46篇（六经/方证/症状/八纲/截图证据等） |
| nivance/nihaixia-kb | ⭐3 | 医案679+症状708+穴位47+药物52+病机188+治法119+方剂39+理论37+针灸7+讲座39 |
| jangviktor-web/nihaixia | ⭐32 | 医案62（癌/心血管/代谢/自免/神经）+课程模块9 |
| elliott10/ebook-nihaixia | ⭐22 | 专题PDF14个（糖尿病/肝癌/乳癌/疫苗/经方/紫微等） |
| wdsheng999/hantang_medicine | ⭐2 | 针灸经络笔记17篇 |
| privateheart/renji | ⭐8 | 针灸大成笔记5篇 |

## 六、下一步开发方向

1. **关系表填充** — 从方剂composition字段提取药物，建立formula_herbs关联
2. **接入LLM** — RAG模式，搜索结果喂给大模型做辨证推理
3. **Web界面增强** — 搜索结果可点击跳转、关系图展示、学习路径
4. **数据导出** — 支持导出JSON/CSV格式
5. **医案结构化增强** — 提取问诊五要素（睡眠/胃口/大小便/口渴/手足温度）
6. **症状→证型→方剂** 推理链路

## 七、关键注意事项

1. **药名古名**：神农本草经用古名，如"茈胡"=柴胡，搜索时需同时搜古名和今名
2. **FTS5不支持中文**：SQLite FTS5 默认分词器不支持中文，搜索用 LIKE 替代
3. **PDF导入**：已用 PyMuPDF (fitz) 导入14个独特专题PDF到 books 表
4. **截图是符号链接**：screenshots/ -> nihaixia/assets/screenshots/，部署时需注意路径
5. **数据库已推GitHub**：tcm_knowledge.db (24MB) 已在仓库中
6. **所有脚本零外部依赖**：仅用 Python 标准库
