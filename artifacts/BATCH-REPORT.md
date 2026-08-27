# OCR 转录 → JSONL 批量报告（2026-08-27）

工具：`scripts/transcripts_to_jsonl.py`（金匮验证版，未改动）
未触碰：`assets/transcripts/` 原文、`tcm_knowledge.db`、tianji / zhongjing-xinfa（OCR 进行中）。

## 汇总

| 分册 | 书名 | 条数 | 质量级(质检报告) | 存疑占比 | 疑截断 |
|---|---|---|---|---|---|
| jingui（样板） | 金匮要略 | 590 | B+ | 27.6% | 121 |
| shanghanlun | 伤寒论 | 553 | B- | **53.0%** | 22 |
| acupuncture | 针灸 | 423 | （已完成版） | 33.6% | 79 |
| bencao | 本草 | 119 | C+ | 47.9% | 8 |
| clinical-cases | 临床医案 | 52 | C | **61.5%**（最高） | 0 |
| fuyang | 扶阳 | 23 | B | 4.3% | 0 |
| yijinjing | 易筋经 | 28 | A- | 0.0% | 0 |
| huangdi | 黄帝内经 | 13 | C+ | 38.5% | 0 |
| bagang | 八纲 | 0 | C | — | — |

**本批新增总条数：1211**（含金匮全库 1801）。

## 备注

- **bagang 产出 0 条**：33 帧全为口语字幕断片，28 条因 <25 字被过滤、5 条跳过标签，符合质检报告 C 级"搁置"结论，非脚本故障。
- **clinical-cases 存疑率最高（61.5%）**、shanghanlun 次之（53.0%）：与质检"口语字幕混杂/不可读手写"结论一致，入库建议走 quarantine/降级路径。
- fuyang 23 条但 skip_tag=12（转录失败帧），存疑率仅 4.3%，质量最好。
- shanghanlun 有 116 条短碎句被 min-chars 过滤（多为授课口语），如需保留可调 `--min-chars`。
- 全部 8 册一次性跑通，无失败跳过项。
