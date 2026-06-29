# formula 去重操作手册 (runbook)

> 用于 formulas 完全合并去重的**备份、迁移、对账、回滚**。
> 核心红线：tcm_knowledge.db 是 WAL 模式，**禁止直接 cp 运行中的主文件**（会漏 `-wal` 未 checkpoint 数据）。

## 0. 红线
- WAL 库备份必须停服后用 `sqlite3.Connection.backup()` 或 `sqlite3 .backup`。
- 删除/迁移前必须有「通过完整性校验」的备份。
- **中医语义字段（composition/dosage/indication/six_channel 等）冲突不得静默覆盖**：保留 canonical 值，其他版本写入 `evidence` 表并标 `source_record`（不得标成中医推理证据）。
- 关系迁移前必须证明：旧 id 的有效内容已进入 canonical 或 evidence。
- 外键是连接级开关：server.py / ETL / 迁移脚本 / 测试连接都要 `PRAGMA foreign_keys=ON`。

---

## 1. 备份（每次迁移前必做）

### 1.1 前置：停止所有写入
```bash
pkill -f "server.py" || true
# 确认无残留写进程
pgrep -fl "server.py|enrich_|populate_|import_new" || echo "✅ 无写进程"
```

### 1.2 执行备份
```bash
cd ~/tcm-project/tcm-db
python3 scripts/backup_db.py
```
输出含：备份路径、SHA-256、表数比对、`integrity_check`、行数一致性。
**全部 ✅ 才算备份有效**，否则停止迁移。

### 1.3 产物
`backups/tcm_knowledge-backup-YYYYMMDD-HHMMSS.db`（带时间戳，不覆盖旧备份）。

---

## 2. 恢复（回滚）
```bash
pkill -f "server.py" || true
cd ~/tcm-project/tcm-db
# 用通过校验的备份覆盖（覆盖前确认该备份 integrity=ok）
cp backups/tcm_knowledge-backup-XXXXXXXX-XXXXXX.db tcm_knowledge.db
# 清理可能残留的 WAL/SHM（恢复后会按需重建）
rm -f tcm_knowledge.db-wal tcm_knowledge.db-shm
nohup python3 server.py 8080 > server.log 2>&1 &
pgrep -f server.py && echo "✅ 已重启"
```

---

## 3. 桂枝汤去重对账 SQL（迁移前后必跑）

> canonical_id = 209（nihaixia 版，带 six_channel）；待删冗余 id = 8, 9, 15, 28。

### 3.1 迁移前快照（before）
```sql
SELECT 'before_formulas_ids',   group_concat(id)            FROM formulas WHERE name='桂枝汤';
SELECT 'before_fh_total',       count(*)                    FROM formula_herbs    WHERE formula_id IN (8,9,15,28,209);
SELECT 'before_fs_total',       count(*)                    FROM formula_syndromes WHERE formula_id IN (8,9,15,28,209);
SELECT 'before_cf_total',       count(*)                    FROM case_formulas    WHERE formula_id IN (8,9,15,28,209);
-- 业务键去重后集合（迁移后 canonical=209 的集合必须等于这些）
SELECT 'before_distinct_herbs',  count(DISTINCT herb_id)    FROM formula_herbs    WHERE formula_id IN (8,9,15,28,209);
SELECT 'before_distinct_cases',  count(DISTINCT case_id)    FROM case_formulas    WHERE formula_id IN (8,9,15,28,209);
```

### 3.2 迁移后验证（after，必须全部满足）
```sql
-- (1) 桂枝汤只剩 canonical 一行
SELECT 'after_formulas_ids', group_concat(id) FROM formulas WHERE name='桂枝汤';   -- 期望: 209
-- (2) 旧 id 不再被任何关系表引用
SELECT 'after_orphan_fh', count(*) FROM formula_herbs    WHERE formula_id IN (8,9,15,28);  -- 期望: 0
SELECT 'after_orphan_fs', count(*) FROM formula_syndromes WHERE formula_id IN (8,9,15,28); -- 期望: 0
SELECT 'after_orphan_cf', count(*) FROM case_formulas    WHERE formula_id IN (8,9,15,28);  -- 期望: 0
-- (3) 业务键集合等价（canonical 的 distinct 集合 == before 的 distinct 集合）
SELECT 'after_distinct_herbs',  count(DISTINCT herb_id) FROM formula_herbs WHERE formula_id=209;  -- == before_distinct_herbs
SELECT 'after_distinct_cases',  count(DISTINCT case_id) FROM case_formulas WHERE formula_id=209;  -- == before_distinct_cases
-- (4) 全库完整性
PRAGMA foreign_key_check;   -- 期望: 空
PRAGMA integrity_check;     -- 期望: ok
```

### 3.3 API 回归
```bash
python3 tests/test_api.py                              # 全绿
curl -s "http://127.0.0.1:8080/api/detail/formulas/209" | head   # 桂枝汤详情含药/证型/医案
curl -s "http://127.0.0.1:8080/api/search?q=桂枝汤" | head        # 搜索仍命中
```

---

## 4. 重启服务
```bash
cd ~/tcm-project/tcm-db
nohup python3 server.py 8080 > server.log 2>&1 &
pgrep -f server.py && echo "✅ server.py 已启动 (新代码已生效)"
```

---

## 5. 迁移脚本事务边界（每方剂一组）
- 动态读取所有引用 `formulas.id` 的表（`PRAGMA foreign_key_list`，不硬编码）。
- 每个重复 id：`INSERT OR IGNORE` 关系到 canonical → 核对业务键 → 删旧关系 → 删冗余 formula 行。
- 全程一个事务；**任一步失败则整组 `ROLLBACK`**，该方剂保持原样。
- 字段冲突（canonical 空→补；冲突→写 evidence 标 source_record）。
