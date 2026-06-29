# Yellow 方剂裁定报告（白虎汤 / 大柴胡汤）· 2026-06-29

> **只读分析，未修改数据库。** 机械性去重（27 组 green）已完成，仅剩这两个 yellow 待人裁定。
> **证据来源**：仅本地数据库 + 来源记录（source_repo/source_path），不凭模型中医常识裁定。原文证据缺失处标 `unknown`。

---

## 一、白虎汤 `ids=[2, 16, 76, 77, 78, 243]` · `canonical候选=243`

### 1. 各 id 非空字段与来源
| id | source_repo | chapter | composition | 非空字段数 | 说明 |
|---|---|---|---|---|---|
| 2 | hantang | 10.辨厥阴病脉证并治法 | —（空） | 6 | **空行**：无组成、无药 |
| 16 | hantang | 3.辨太阳病脉证并治法上篇 | 石膏,知母,炙甘草,粳米 | 7 | 完整 |
| 76 | hantang | 5.辨太阳病脉证并治法下篇 | —（空） | 6 | **空行** |
| 77 | hantang | 5.辨太阳病脉证并治法下篇 | 石膏,知母,炙甘草,粳米 | 7 | 完整 |
| 78 | hantang | 5.辨太阳病脉证并治法下篇 | 石膏,知母,炙甘草,粳米 | 7 | 完整 |
| 243 | nihaixia | —（None） | 石膏,知母,炙甘草,粳米 | 10 | **最全（canonical 候选）** |

**canonical 理由**：id 243 非空字段最多（10），nihaixia 版（pick_canonical 规则：字段完整度最高 + nihaixia 优先）。

### 2. formula_herbs 完整集合（剂量/炮制差异）
- id 16 / 77 / 78 / 243：均为 `石膏, 知母, 粳米, 炙甘草`（4 味，**完全一致**，dosage_in_formula 全 None，无剂量；note 全空，无炮制差异）
- id 2 / 76：**无 herbs**（空行）
- 结论：**无剂量/炮制差异**（所有剂量字段为空，是数据缺失而非差异）

### 3. formula_syndromes
- 仅 id 243 挂载证型（1 条）；id 2/16/76/77/78 均无。具体证型名见 db（`SELECT * FROM formula_syndromes WHERE formula_id=243`）。

### 4. case_formulas 及医案摘要/来源（id 243，共 8 条）
| case_id | source_repo | raw_path |
|---|---|---|
| 4 | hantang | 倪师医案整理/1500个医案记录/080822牙套金属过敏.md |
| 750,776,814,849,1180,1378,1380 | nihaixia-kb | wiki/医案/摘要/*.md（7 条） |

id 2/16/76/77/78 无医案。医案主诉各异（牙套过敏等），均 nihaixia/hantang 来源记录，挂白虎汤。

### 5. 挂载的 evidence
- id 2：1 条；id 76：1 条；其余 id 无 evidence。具体 relation_type/source_record_id 见 db（`SELECT * FROM evidence WHERE subject_type='formula' AND subject_id IN (2,76)`）。

### 6. 普通关系迁移前后业务键集合
- 迁移前 distinct herbs（全组）：`{石膏, 知母, 粳米, 炙甘草}`（来自 id 16/77/78/243）
- 迁移后（合并到 243）：`{石膏, 知母, 粳米, 炙甘草}`（INSERT OR IGNORE 去重，**集合不变**）
- 旧 id 16/77/78 各 4 条 formula_herbs → 合并到 243 后去重为 4 条；id 2/76 无 herbs。

### 7. 字段冲突原值与来源（共 5 条，**全部是 chapter**，非医学字段）
| 冲突字段 | 其他 id | 其他值（来源 hantang） | canon 243 值 | is_medical |
|---|---|---|---|---|
| chapter | 2 | 10.辨厥阴病脉证并治法 | None | False |
| chapter | 16 | 3.辨太阳病脉证并治法上篇 | None | False |
| chapter | 76 | 5.辨太阳病脉证并治法下篇 | None | False |
| chapter | 77 | 5.辨太阳病脉证并治法下篇 | None | False |
| chapter | 78 | 5.辨太阳病脉证并治法下篇 | None | False |

### 8. 空值互补 vs 真实语义差异
- **空值互补**：无（updates={}，canon 243 无空字段需补；旧 id 的 chapter 非空但与 canon 的 None 冲突，非"互补"）。
- **真实语义差异**：仅 chapter（篇章定位）。composition/herbs 全组一致 → **无方剂语义差异**。
- id 2/76 是**空行**（无组成无药）——判定为章节引用占位（厥阴病篇/太阳下篇提及白虎汤但未重列组成），非独立方剂实体。此判定依据：组成/herbs 字段全空 + 同名 + 来源同 hantang。`unknown`：空行的原始导入逻辑未留存（P1 工程债），无法 100% 排除"独立变体"可能，但组成一致性强支持"占位"。

### 9. 合并后预计新增
- merged_from：+5（旧 id 2/16/76/77/78 → 243）
- field_value：+5（5 条 chapter 冲突，保留来源篇章写 evidence）
- normalized_from：id 2/76 的 evidence 迁移到 243（subject 改指，净 0）

### 10. 删除旧 ID 后 API 重定向计划
- `/api/detail/formulas/2|16|76|77|78` → 200 + `_redirected_from` + `_canonical_id=243`
- 当前 redirect map 49 条，合并后 → 54 条（启动加载 evidence merged_from）

---

## 二、大柴胡汤 `ids=[41, 46, 60, 68]` · `canonical候选=41`

### 1. 各 id 非空字段与来源
| id | source_repo | chapter | composition | 非空字段数 | 说明 |
|---|---|---|---|---|---|
| 41 | hantang | 4.辨太阳病脉证并治法中篇 | 柴胡、黄芩、枳实、白芍、炙甘草、大黄、厚朴、生姜 | 7 | **canonical 候选** |
| 46 | hantang | 4.辨太阳病脉证并治法中篇 | 柴胡、黄芩、枳实、白芍、炙甘草、大黄、厚朴、生姜 | 7 | 完整，与 41 同章 |
| 60 | hantang | 5.辨太阳病脉证并治法下篇 | —（空） | 6 | **空行** |
| 68 | hantang | 5.辨太阳病脉证并治法下篇 | 柴胡、黄芩、枳实、白芍、炙甘草、大黄、厚朴、生姜 | 7 | 完整，挂 9 医案 |

**canonical 理由**：id 41 字段完整 + 最低 id（46 与 41 同章同组成，取最小 id）。

### 2. formula_herbs 完整集合
- id 41 / 46 / 68：均为 `厚朴`（1 味，dosage/note 全空）
- id 60：无 herbs（空行）
- 注：composition 列出 8 味，但 formula_herbs 表只挂了厚朴 1 味——**composition 文本与 formula_herbs 关系表不对齐**（`unknown`：ETL 仅将部分药入关系表，或厚朴为标记性用药）。这是数据录入问题，非方剂差异。

### 3. formula_syndromes
- 全组无证型挂载。

### 4. case_formulas 及医案（id 68，共 9 条，全 nihaixia-kb）
| case_id | 性别/年龄 | 主诉摘要 | 来源 |
|---|---|---|---|
| 744 | 女/56 | 右脚跟痛（肾虚） | nihaixia-kb |
| 758 | 女/55+ | 右侧肝区剧痛穿背 | nihaixia-kb |
| 759 | 女/55+ | 右侧肝区剧痛穿背（与758同案拆分?） | nihaixia-kb |
| 883 | 女/46 | 慢性腹膜炎16年 | nihaixia-kb |
| 884 | 女/中年 | 右下腹胀痛欲爆 | nihaixia-kb |
| 1124 | ? | 奎宁中毒/头昏/视力模糊 | nihaixia-kb |
| 1125 | 女/80+ | 奎宁中毒（与1124同案?） | nihaixia-kb |
| 1235 | 男/40 | B肝带原/工作压力 | nihaixia-kb |
| 1630 | 女/四五十 | 慢性盲肠炎包膜 | nihaixia-kb |

id 41/46/60 无医案。**9 医案全挂 id 68**，组成与 canon 41 一致。

### 5. 挂载的 evidence
- id 60：1 条；其余无。见 db。

### 6. 普通关系迁移前后业务键集合
- 迁移前 distinct herbs：`{厚朴}`（id 41/46/68）；迁移后合并到 41：`{厚朴}`（不变）
- **9 条 case_formulas（id 68）→ 合并到 41**：distinct cases 迁移前后一致（9 个 case 改挂 41）

### 7. 字段冲突（共 2 条，全是 chapter）
| 冲突字段 | 其他 id | 其他值 | canon 41 值 | is_medical |
|---|---|---|---|---|
| chapter | 60 | 5.辨太阳病脉证并治法下篇 | 4.辨太阳病脉证并治法中篇 | False |
| chapter | 68 | 5.辨太阳病脉证并治法下篇 | 4.辨太阳病脉证并治法中篇 | False |

### 8. 空值互补 vs 语义差异
- **空值互补**：无（updates={}）。
- **真实语义差异**：仅 chapter（中篇 vs 下篇）。composition 一致 → 无方剂语义差异。
- id 60 空行（无组成无药）= 章节引用占位（太阳下篇提及大柴胡汤未重列组成）。`unknown`：同白虎汤空行，导入器缺失无法 100% 排除。

### 9. 合并后预计新增
- merged_from：+3（旧 id 46/60/68 → 41）
- field_value：+2（2 条 chapter 冲突）
- normalized_from：id 60 evidence 迁移（净 0）

### 10. API 重定向计划
- `/api/detail/formulas/46|60|68` → 200 + `_canonical_id=41`
- redirect map 49 → 52

---

## 三、必须回答的 5 个问题

### Q1. 是否存在同名异方或组成变体？
**否。** 白虎汤全组 composition 一致（石膏,知母,炙甘草,粳米）；大柴胡汤全组 composition 一致（柴胡,黄芩,枳实,白芍,炙甘草,大黄,厚朴,生姜）。无组成变体。空行（白虎 id 2/76、大柴胡 id 60）组成/herbs 全空，是章节引用占位，非异方（依据：组成一致 + 同名 + 同源；`unknown`：导入器缺失，无法绝对排除但证据强支持占位）。

### Q2. 关系合并是否会制造原资料中不存在的"联合方"？
**否。** 白虎汤 herbs 集合 `{石膏,知母,粳米,炙甘草}` 各 id 完全相同，INSERT OR IGNORE 合并去重后集合不变；大柴胡汤 herbs `{厚朴}` 同理。合并不产生新组合。

### Q3. 9 个大柴胡汤医案是否确实都指向同一方剂实体？
**是（依据数据，非中医判断）。** 9 医案全挂 id 68，id 68 的 composition 与 canon 41（及其他 id）完全一致，全 nihaixia-kb 来源。这些是倪师对不同患者使用同一大柴胡汤的医案记录（同方异症），指向同一方剂实体。主诉多样（脚跟痛/肝区痛/腹膜炎/奎宁中毒/B肝/盲肠炎）是"同方治不同症"的应用记录，不构成异方证据。`unknown`：758/759、1124/1125 疑为同案拆分，需人工确认是否去重，但不影响"同一方剂"判定。

### Q4. 白虎汤 3 处非医学冲突具体是什么？
实际 5 条 chapter 冲突记录，**去重为 3 个不同 chapter 值**（即用户所指"3 处"）：
1. **厥阴病篇**（id 2）vs canon 243 的 None
2. **太阳病上篇**（id 16）vs None
3. **太阳病下篇**（id 76/77/78，3 行重复）vs None

均为 `chapter` 字段（篇章定位，`is_medical=False`），非医学内容冲突。反映同一白虎汤在《伤寒论》不同篇章被记录（厥阴病篇提白虎汤、太阳上/下篇有白虎汤条文）。

### Q5. 推荐 merge / keep_variants / quarantine？依据？
**推荐：均 `merge`**（白虎汤→243，大柴胡汤→41）。

依据：
- ✅ 组成（composition）全组一致——无变体
- ✅ herbs 关系集合一致——合并不制造联合方
- ✅ 字段冲突**全部是非医学 chapter**（篇章定位），无医学字段冲突
- ✅ 医案/证型挂在 canonical 或可安全迁移的 id（白虎 8 案在 243=canon；大柴胡 9 案在 68，组成同 canon 41）
- ✅ 空值互补无（updates={}），无静默覆盖风险

**为何之前判 yellow 而非 green**：risk-report 按字段冲突数评级，白虎汤 5 条 / 大柴胡汤 2 条 chapter 冲突超过 green 阈值。但**逐项复核后，冲突全是非医学 chapter**（同一方剂在原文不同篇章的定位），符合 merge 标准。yellow 是"需人确认 chapter 冲突可接受"，人确认后可 merge。

**merge 后处理**：chapter 冲突按既有规则写 field_value evidence（保留来源篇章 + canon 留 None 或人工选定），不丢来源可溯性。

---

## 四、规则遵守声明
- ✅ 仅使用本地数据库 + 来源记录（source_repo/source_path/raw_path）
- ✅ 不凭模型中医常识裁定（Q3 医案判定基于 composition 一致 + 同源，非"这些症状该用某方"）
- ✅ 缺原文证据处标 `unknown`（空行导入器缺失、composition vs formula_herbs 不对齐、疑同案拆分）
- 主线程已逐项复核来源与关系集合（材料落盘 `/tmp/yellow_materials.json` + `/tmp/yellow_conflicts.json`）

## 五、后续（未执行，本轮止步）
- 报告仅供裁定，**未迁移 yellow、未动数据库**
- 待你确认 merge 后，可用 `python3 scripts/migrate_formula_dedup.py migrate --name 白虎汤 --name 大柴胡汤` 执行（脚本已验证）
