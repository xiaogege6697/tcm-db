# 板书 OCR 语料管线（质检报告 + 中间格式设计 + 入库路径）

_2026-08-27 研学产出 · 状态：设计定稿，未动 tcm_knowledge.db（纯增量设计）_

## 一、语料现状

`assets/transcripts/` 共 10 个有效文件（tianji/zhongjing-xinfa 仅 1 行占位，忽略）：

| 文件 | 行数 | 格式代际 | 内容性质 |
|---|---|---|---|
| jingui.md | 698 | 混合（早期简表 + 后期详细描述） | 金匮条文+方剂板书 |
| shanghanlun.md | 678 | 早期简表 | 伤寒条文，混入大量口语字幕 |
| bencao.md | 127 | 后期详细描述 | 本草药名/五味板书，字迹最潦草 |
| acupuncture.md | 488 | 早期简表 | 已另行处理（据任务说明） |
| clinical-cases.md | 92 | 早期简表 | 穴位/字幕帧为主，信息密度低 |
| fuyang.md | 45 | 早期简表 | 医案（含完整处方，价值高） |
| huangdi.md | 26 | 早期简表 | 内经板书关键词堆 |
| yijinjing.md | 36 | 后期详细描述 | 易筋经动作要领（白话，质量好） |
| bagang.md | 41 | 字幕帧 | 口语字幕，无板书 |

## 二、质检报告（每文件抽样 3-5 段）

分级：**A=可直接入库**（结构化抽取即可）／**B=需人工抽校**（关键字段错漏可控）／**C=需重转或放弃**。

| 文件 | 分级 | 主要问题 |
|---|---|---|
| jingui | **B+** | 两代格式混排；重复镜头多（同页 3-6 帧）；竖排已由转写者按语义重组，错字率低（约 1-2%），但 0007/0032 等页"行序错乱"自标注多；122 条疑截断（画面裁切"最左列"） |
| shanghanlun | **B-** | 板书正文与授课口语字幕混在同一单元格里（"名为中风太阳病呢我们有中风有伤寒"），条文完整度远低于金匮；0011-0021 存大量栅格错乱自标注 |
| bencao | **C+** | 草书+低分辨率，转写者自己标了大量 〔?〕；可辨识骨架（药名序列、五味归类）尚有值，建议按"板书碎片"降级入库而非条文 |
| acupuncture | （已完成，不在本次范围） | — |
| clinical-cases | **C** | 多为单句字幕/无文字帧，无医案结构；个别行（0011-0012）是潦草手写日期+药名，几乎不可读 |
| fuyang | **B** | 医案结构清晰（案例编号/日期/症状/处方/复诊），错字集中在 OCR 混淆（政→症、窺→屎类），处方药物列表基本准确；血癌案例 2、Lupus 案完整 |
| huangdi | **C+** | 关键词堆+错字率高（"晚(曙)早起"），无连读文本；建议只做主题标签层，不做条文层 |
| yijinjing | **A-** | 白话动作要领，转录完整清晰，几乎无需校对（少量标题错字：易筋径/国籙筆径） |
| bagang | **C** | 纯口语字幕断片，单帧无语义；除非按课程时间轴拼接，否则无用 |

**通用问题**（所有文件）：
1. 重复镜头：同一板书页被截 3-6 帧，内容相同但错字不同 → 靠内容 hash 去重，保留多帧 image_ids 备查
2. 水印变体："UP主硬照鬼才/砸照/晒/顽固/彼照见才" 等多种误识 → 脚本已用宽匹配剥离
3. 竖排→横排：转写者已做语义重组（这是这批语料最大的质量红利），脚本不需再做列序还原

## 三、中间格式（JSONL v1）

每条文一行，字段：

```json
{
  "id": "金匮要略-b72a867b",          // book + content_hash 前8位
  "book": "金匮要略",
  "chapter": "痰飲欬嗽病脈證并治第十二",
  "chapter_source": "explicit|inherited",  // 显式命中篇章名 / 从上一条继承
  "text": "……条文+方剂连读全文……",
  "formula_names": ["小半夏湯"],
  "caption": "",                        // 底部字幕（授课口语，与正文分离）
  "image_ids": ["0293", "0294"],
  "source_file": "assets/transcripts/jingui.md",
  "content_hash": "…",                  // 去标点后 sha1[:16]，跨帧去重键
  "flags": {
    "has_doubt_mark": true,             // 原转写含"字形存疑/？"
    "has_truncation": true,             // 原转写含"截断/裁切/未完"
    "from_verbose_format": true         // 来自后期详细格式（连读块可信度更高）
  }
}
```

转换脚本：`scripts/transcripts_to_jsonl.py`

```bash
python3 scripts/transcripts_to_jsonl.py assets/transcripts/jingui.md \
    --book "金匮要略" --out artifacts/jingui.jsonl
```

**金匮样板结果**：590 条（669 有效帧 − 41 条"同NNNN"引用帧 − 5 显式跳过 − 53 碎句 − 5 hash 重复）；含方名 282 条、疑截断 121、疑存疑 163。人读抽检 3 条（薏苡附子散条/甘草泻心汤条/消渴厥阴条）均通顺可读。

## 四、对齐 tcm_knowledge.db 与入库路径

### 现有承接点
- `classics` 表（book_name/chapter_name/chapter_num/content/annotation/raw_path）——**条文层天然去处**：jingui.jsonl 每条 → classics 一行，book_name='金匮要略'，content=text，annotation 可放 caption（授课口语），raw_path=source_file+image_ids
- `formulas` 表（name/source_book/chapter/composition/dosage）——jsonl 的 formula_names + text 内"X方：药 剂量"结构可二次抽取为候选 formula 行
- `ingestion_quarantine` 表——已有隔离机制，flags.has_doubt_mark/has_truncation 的条目建议走 quarantine（reason_code 现有枚举偏 name 类，需扩 1 个 code 如 `low_confidence_ocr`，属于 schema 小改，暂未做）
- `evidence` 表——source_type 已支持 'image'，subject_type 支持 'classic'：入库后逐条登记 source_record_id=image_ids，溯源到原始截图

### 喂进 populate 流程
1. **不建议改 populate.py 主流程**（它面向 GitHub md 仓库）。新增 `scripts/load_transcript_jsonl.py`：读 jsonl → 按 book 写 classics/formulas 候选 → 每行写 evidence(image)
2. 去重防线：jsonl 的 content_hash 与 classics 现有 26 条金匮记录比对（现库 26 条 vs 样板 590 条，重叠预计集中在名篇），冲突时保现库、新条目进 quarantine
3. 缺的字段：classics 需要 chapter_num（现靠正则从 chapter 尾部"第十二"提取，可补）；formulas 需要 composition 结构化（需对 text 跑方剂解析，如"藥名+數字+兩/枚/升"模式）——这是下一步工作，不在本次范围

### 分级落地顺序建议
1. jingui（B+）→ classics 直入，quarantine 疑存疑条
2. fuyang（B）→ clinical_cases 表，处方解析后关联 case_herbs
3. yijinjing（A-）→ course_notes（module_name='针灸'，note_type='功法'）
4. shanghanlun（B-）→ 先人工抽校字幕混杂段，再走同管线
5. bencao/huangdi → 降级为主题标签层，暂缓
6. clinical-cases/bagang → 搁置

## 五、遗留
- [ ] load_transcript_jsonl.py（入库执行器，本文档只做设计）
- [ ] quarantine reason_code 扩 `low_confidence_ocr`（需 schema 小改）
- [ ] shanghanlun 字幕/正文分离规则（金匮靠 caption 字段已解，伤寒早期格式需反推）
- [ ] chapter 显式命中率仅 12/590，多数靠 inherited——按篇章页边界人工校一遍章节切分
