# Changelog

## v0.2.0 · 2026-06-29 — 可靠数据底盘

> 机械性去重全部完成、安全加固、迁移工具链就位。数据库为权威产物。
> DB SHA-256: `a9ff634e621ed47869c4ab2628e145b7da48afe922205bcf6f7983415a72966c`

### 实测基线（SQL 实测，非抄录）
- formulas: **234**（清洗前 301，去重后）
- 重名方剂组（duplicates）: **0**（清洗前 28 组）
- evidence: **121**（field_value 30 / merged_from 57 / normalized_from 34）
- ingestion_quarantine: **14**
- redirect 映射（merged_from）: **57** 旧ID → canonical
- integrity_check: ok / foreign_key_check: 空 / audit hard=0
- 全表计数：herbs 472 / symptoms 727 / syndromes 194 / clinical_cases 1737 / classics 113 / course_notes 121 / treatment_methods 119 / lectures 81 / tianji 185 / books 22 / folk_formulas 17 / courses 15 / acupoints 47；关系表 formula_herbs 196 / formula_syndromes 19 / case_formulas 472 / case_herbs 2342 / syndrome_symptoms 440 / course_course_notes 68

### 安全加固
- `server.py`：SQL 表名/列名白名单防注入、`/screenshots/` 路径穿越防护、`PRAGMA foreign_keys=ON`、异常不泄露内部细节、绑定 `127.0.0.1`（非 0.0.0.0）
- `/api/detail/formulas/<旧id>` 透明重定向到 canonical（200 + `_redirected_from`/`_canonical_id`）；未知ID JSON 404；非法ID 400

### formula 名称清洗与隔离
- Phase0.5：48 个 blockquote 脏名 → 34 改名（`normalized_from` evidence 记原名）+ 14 隔离到 `ingestion_quarantine`
- 守恒：清洗前 301 == 287 formulas + 14 quarantine

### 全部重名方剂合并（27 组）
桂枝汤(1) + 五组(5) + 5 green(5) + 16 green(16) + 2 yellow(2) = 27 组全部去重，重名组 28→0。
- 字段合并确定性规则：canonical 非空+其他冲突→保留 canonical 写 field_value evidence；canonical 空+一致→补；canonical 空+冲突→留空+全写 evidence
- `evidence` 表：dedupe_key 幂等（规范 JSON SHA-256）、多态无 FK、CHECK 枚举

### evidence 与旧ID重定向
- `merged_from` evidence 作为旧id→canonical 映射源（与去重同源不脱节）
- 启动内存缓存 `_load_formula_redirect_map`：单射校验（冲突排除告警）+ 循环保护 + ID 严格解析
- 删 formula 前强制门禁：旧id 不再作 subject/object + 关系归零 + `audit_evidence_refs` 通过

### 数据审计 / 备份 / 迁移工具（scripts/）
- `audit_db.py`：质量闸门（blockquote/空/控制字符 hard exit 非0；长名/多方 warning）
- `backup_db.py`：`Connection.backup()` 在线一致快照（WAL 库禁 cp 主文件）
- `migrate_formula_dedup.py migrate`：通用去重（evidence subject/object 迁移 + 删除门禁 + 多组单事务，dry-run 同代码路径）
- `gen_merge_plan.py` / `gen_merge_risk_report.py`：去重计划与风险评级

### 测试（tests/，全过）
- `test_api.py` 25 项（SQL 注入白名单 + 路径穿越 + 旧ID重定向 + HTTP 层状态码）
- `test_migrate_dedup.py` 10 项（subject/object 迁移 / source_record_id 不变 / dedupe 碰撞 / dry-run 零写入 / 幂等 / 故障 ROLLBACK / 多组单事务）
- `test_schema_parity.py`：脚本 DDL 枚举 ⊇ 正式库（防漂移）

### ETL check 入口
- `scripts/etl.py --check`：报告 clinical_cases 来源键状态（只读）
- `case-ingest`：**BLOCKED**（见下）
- `formulas-ingest`：NOT IMPLEMENTED（历史导入器缺失）

### ⚠️ 已知限制（不阻塞 v0.2，列入后续 P1）
- **clinical_cases 导入安全阻断**：无可靠稳定来源身份键（`raw_path` 同文件多案、`patient_id` 实为标题、组合键仍冲突、无 UNIQUE）。`case-ingest` 保持 BLOCKED——**宁可明确不能导入，也不提供会污染数据库的入口**。长期方案 A（补 `source_locator` 稳定锚点）已裁定，列入后续专项，本版不实施。不采用内容指纹冒充来源幂等；不恢复裸 INSERT。见 `docs/clinical-cases-idempotency-analysis.md`
- **formulas 历史导入器缺失**：脏名/去重根因脚本未留存，数据库为"权威产物"非"可从源重建"。`populate.py build()` 为空壳，`--rebuild` 不可用
- screenshots 为本机绝对路径软链接（已跟踪，本地资源）
- ingestion_quarantine 14 行待人工整理（不阻塞）

### 升级 / 部署
```bash
python3 -u server.py 8080   # 绑定 127.0.0.1，旧ID自动重定向
python3 scripts/etl.py --check
python3 scripts/audit_db.py
```
