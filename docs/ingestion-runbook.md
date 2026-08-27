# OCR 转写 JSONL 入库 Runbook

_2026-08-27 · 配套设计文档 `transcript-pipeline.md`，执行器 `scripts/load_transcript_jsonl.py`_

## 入库步骤

```bash
cd ~/.openclaw/shared/knowledge/tcm-db

# 1. 备份（铁律，跳过即停）
cp tcm_knowledge.db tcm_knowledge.db.bak-$(date +%m%d-%H%M)

# 2. 测试库验证（铁律：主库导入前必须全绿）
cp tcm_knowledge.db /tmp/tcm-test.db
python3 scripts/load_transcript_jsonl.py artifacts/jingui.jsonl --db /tmp/tcm-test.db   # 首跑
python3 scripts/load_transcript_jsonl.py artifacts/jingui.jsonl --db /tmp/tcm-test.db   # 二跑：全字段零增量

# 3. 验证 SQL 三连（见下），全绿后主库
python3 scripts/load_transcript_jsonl.py artifacts/jingui.jsonl --db tcm_knowledge.db

# 4. 主库复核：同款 SQL 三连 + 增量计数
```

## 验证 SQL 三连

```sql
-- ① 增量守恒：read = classics_inserted + quarantined + classics_dup（首跑 dup 应=0）
SELECT COUNT(*) FROM classics WHERE book_name='金匮要略';        -- 存量26 → 358（+332）
SELECT COUNT(*) FROM ingestion_quarantine WHERE reason_code LIKE 'ocr_%';  -- +258

-- ② 幂等：二跑输出 classics_inserted=0, quarantined=0, evidence_inserted=0（仅 *_dup 非零）

-- ③ 溯源抽检：classics JOIN evidence 能查到 image_ids
SELECT c.id, substr(c.content,1,30), group_concat(e.source_record_id)
FROM classics c JOIN evidence e
  ON e.subject_type='classic' AND e.subject_id=c.id
WHERE c.content_hash IS NOT NULL GROUP BY c.id LIMIT 3;
```

## 已知事实（金匮首跑，2026-08-27）

- 590 条 = 332 classics + 258 隔离（ocr_low_confidence/ocr_truncated）；formulas 候选 222 行（source_repo='ocr-candidate'，未与现有方剂合并）；evidence(image) 333+222=555 行
- 存量 26 条金匮 classics 未检出 hash 重复（存量清洗规则与新管线不同，重合未被识别——不冲突也不覆盖，后续可人工比对）
- schema 自动小改：classics 加 `content_hash` 列；quarantine reason_code 枚举扩 `ocr_low_confidence`/`ocr_truncated`（重建表保数据，14 条存量无损）
- 脚本只增不删，全事务，`--dry-run` 可试跑回滚

## 后续册子接入

伤寒论等 9 册转换完成后：换 jsonl 路径重复上述步骤即可，book 字段自动分流入 classics/formulas。隔离条目审核后改 `status` 字段（pending_review → rejected/restored）。
