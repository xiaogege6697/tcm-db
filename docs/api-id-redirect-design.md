# 旧 formula ID → canonical ID API 重定向方案（设计，未实施）

> **状态：仅设计，未改 API。** 审核通过后才动 server.py（属改 API 行为）。

## 背景
formulas 完全合并去重删除旧 id 后，任何**外部对旧 id 的引用**会失效：
- 浏览器书签 / 分享链接 `/api/detail/formulas/8`
- 导出的 JSON/CSV 里残留的旧 id
- 第三方按 id 调用的请求

旧 id 8/9/15/28 已不存在 → 现状会返回 404。需重定向到 canonical（209）。

## 映射来源（已有，无需新建）
迁移时已写入 evidence 表：
```
subject_type='formula', subject_id=<canonical>, relation_type='merged_from',
source_record_type='formula', source_record_id=<旧id>(TEXT)
```
即 `evidence` 天然是 `{旧id → canonical}` 映射表。

## 方案对比

### 方案 1：复用 evidence 表（推荐，零新表）
API 在 id 未命中时查 evidence：
```sql
SELECT subject_id FROM evidence
WHERE subject_type='formula' AND relation_type='merged_from'
  AND source_record_type='formula' AND source_record_id=?
LIMIT 1;
```
命中 → 返回 canonical 数据（附加 `_redirected_from=旧id` 标记），或 301/302 重定向。
- ✅ 零新表，复用迁移产物；映射与去重同源，不会脱节。
- ⚠️ 每次 miss 多一次查询 → 用启动内存缓存消除（见方案 3 叠加）。

### 方案 2：独立 formula_id_map 表
```sql
CREATE TABLE formula_id_map (old_id INTEGER PRIMARY KEY, canonical_id INTEGER, merged_at TEXT);
```
迁移时填充，API miss 查此表。
- ✅ 查询语义清晰、可索引。
- ❌ 与 evidence merged_from **重复存储**，两处需同步。

### 方案 3：启动内存缓存
启动时把 evidence merged_from 加载为 `{old_id: canonical}` 字典，API O(1) 查。
- ✅ 零运行时开销（映射仅 ~36 条）。
- ⚠️ 新增映射需重启或刷新接口。

## 推荐：方案 1 + 方案 3 缓存
- API 层：id miss → 查内存缓存（启动从 evidence 加载）→ 命中则返回 canonical。
- **不改 API 契约**：`/api/detail/formulas/8` 仍返回 200 + 数据，附 `_redirected_from: 209`（透明重定向，优于 301，避免客户端断链）。
- 覆盖端点：`/api/detail/<table>/<id>`（主体）；`/api/browse`、`/api/export` 不需（按表/筛选，非单 id）。

## 伪代码（server.py 改动草案，待审核）
```python
# 启动时加载
REDIRECT_MAP = {}  # {old_id: canonical_id}
for r in conn.execute(
    "SELECT source_record_id, subject_id FROM evidence "
    "WHERE subject_type='formula' AND relation_type='merged_from' "
    "AND source_record_type='formula'"):
    if r[0]: REDIRECT_MAP[int(r[0])] = r[1]

# api_detail 内
row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
if row is None and table == 'formulas' and id in REDIRECT_MAP:
    canon = REDIRECT_MAP[id]
    row = conn.execute("SELECT * FROM formulas WHERE id=?", (canon,)).fetchone()
    d = dict_row(row); d['_redirected_from'] = id   # 透明标记
    return d
```

## 待你裁定
1. 重定向语义：**200 + `_redirected_from` 标记（透明，推荐）** vs 301/302 HTTP 重定向？
2. 是否覆盖 `/api/export`（CSV/JSON 残留旧 id）：默认不动（导出反映当前 canonical），还是把旧 id 也映射？
3. 范围：仅 formulas 去重，还是泛化到未来 herb/syndrome 去重的 id 重定向？
4. 是否接受方案 1+3（复用 evidence + 内存缓存）？

## 实施时机
第二批绿色组去重完成后、或观察到外部引用旧 id 时实施。属"改 API 行为"，需你确认。
