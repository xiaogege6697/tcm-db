# 剩余方剂去重风险评估

> 桂枝汤已迁移，不在评估内。
green=可直接批量；yellow=需留意（关系多/非医学冲突多）；red=需人工裁定（医学冲突或药集合不一致）。

- 🟢 green: 26 组 — 五苓散, 真武汤, 麻黄汤, 小柴胡汤, 抵当汤, 四逆散, 四逆汤, 旋覆代赭石汤, 桃核承气汤, 猪苓汤, 葛根汤, 乌梅丸, 吴茱萸汤, 干姜黄连黄芩人参汤, 承气汤, 旋覆代赭汤, 柴胡桂枝汤, 桂枝人参汤, 桂枝加芍药汤, 桂枝加葛根汤, 桂枝甘草汤, 桂枝麻黄各半汤, 甘草干姜汤, 调胃承气汤, 附子汤, 麻子仁丸
- 🟡 yellow: 2 组 — 白虎汤, 大柴胡汤
- 🔴 red: 0 组 — 无

## 明细

### [YELLOW] 白虎汤  ids=[2, 16, 76, 77, 78, 243] → canon=243(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 3 处 (医学 0 / 非医学 3)
  - [非医学] chapter: canon=None 冲突='10.辨厥阴病脉证并治法' from=[2]
  - [非医学] chapter: canon=None 冲突='3.辨太阳病脉证并治法上篇' from=[16]
  - [非医学] chapter: canon=None 冲突='5.辨太阳病脉证并治法下篇' from=[76, 77, 78]
- 关系迁移: 12 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 五苓散  ids=[32, 33, 34, 86, 225] → canon=225(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 2 处 (医学 0 / 非医学 2)
  - [非医学] chapter: canon=None 冲突='4.辨太阳病脉证并治法中篇' from=[32, 33, 34]
  - [非医学] chapter: canon=None 冲突='6.辨阳明病脉证并治法' from=[86]
- 关系迁移: 2 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 真武汤  ids=[36, 37, 98, 101, 228] → canon=228(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 2 处 (医学 0 / 非医学 2)
  - [非医学] chapter: canon=None 冲突='4.辨太阳病脉证并治法中篇' from=[36, 37]
  - [非医学] chapter: canon=None 冲突='9.辨少阴病脉证并治法' from=[98, 101]
- 关系迁移: 2 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 麻黄汤  ids=[24, 27, 31, 51, 214] → canon=214(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 2 处 (医学 0 / 非医学 2)
  - [非医学] chapter: canon=None 冲突='3.辨太阳病脉证并治法上篇' from=[24]
  - [非医学] chapter: canon=None 冲突='4.辨太阳病脉证并治法中篇' from=[27, 31, 51]
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [YELLOW] 大柴胡汤  ids=[41, 46, 60, 68] → canon=41(hantang)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 1 处 (医学 0 / 非医学 1)
  - [非医学] chapter: canon='4.辨太阳病脉证并治法中篇' 冲突='5.辨太阳病脉证并治法下篇' from=[60, 68]
- 关系迁移: 11 (旧 id 挂医案 case_formulas: 9)

### [GREEN] 小柴胡汤  ids=[42, 43, 44, 230] → canon=230(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 抵当汤  ids=[57, 59, 84, 250] → canon=250(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 2 处 (医学 0 / 非医学 2)
  - [非医学] chapter: canon=None 冲突='5.辨太阳病脉证并治法下篇' from=[57, 59]
  - [非医学] chapter: canon=None 冲突='6.辨阳明病脉证并治法' from=[84]
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 四逆散  ids=[103, 104, 264] → canon=264(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 四逆汤  ids=[39, 83, 253] → canon=253(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 2 处 (医学 0 / 非医学 2)
  - [非医学] chapter: canon=None 冲突='4.辨太阳病脉证并治法中篇' from=[39]
  - [非医学] chapter: canon=None 冲突='6.辨阳明病脉证并治法' from=[83]
- 关系迁移: 1 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 旋覆代赭石汤  ids=[65, 66, 67] → canon=65(hantang)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 桃核承气汤  ids=[48, 58, 235] → canon=235(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 2 处 (医学 0 / 非医学 2)
  - [非医学] chapter: canon=None 冲突='4.辨太阳病脉证并治法中篇' from=[48]
  - [非医学] chapter: canon=None 冲突='5.辨太阳病脉证并治法下篇' from=[58]
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 猪苓汤  ids=[81, 87, 249] → canon=249(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 葛根汤  ids=[17, 20, 215] → canon=215(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 乌梅丸  ids=[1, 265] → canon=265(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 吴茱萸汤  ids=[56, 99] → canon=99(hantang)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 1 处 (医学 0 / 非医学 1)
  - [非医学] chapter: canon='9.辨少阴病脉证并治法' 冲突='5.辨太阳病脉证并治法下篇' from=[56]
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 干姜黄连黄芩人参汤  ids=[3, 4] → canon=3(hantang)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 承气汤  ids=[29, 69] → canon=29(hantang)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 1 处 (医学 0 / 非医学 1)
  - [非医学] chapter: canon='4.辨太阳病脉证并治法中篇' 冲突='5.辨太阳病脉证并治法下篇' from=[69]
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 旋覆代赭汤  ids=[5, 239] → canon=239(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 柴胡桂枝汤  ids=[62, 231] → canon=231(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 桂枝人参汤  ids=[71, 238] → canon=238(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 桂枝加芍药汤  ids=[92, 251] → canon=251(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 桂枝加葛根汤  ids=[10, 210] → canon=210(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 桂枝甘草汤  ids=[54, 220] → canon=220(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 3 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 桂枝麻黄各半汤  ids=[11, 213] → canon=213(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 甘草干姜汤  ids=[55, 292] → canon=292(nihaixia-kb)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 1 处 (医学 0 / 非医学 1)
  - [非医学] source_book: canon='临床记录' 冲突='伤寒论' from=[55]
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 调胃承气汤  ids=[40, 247] → canon=247(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 1 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 附子汤  ids=[96, 97] → canon=96(hantang)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)

### [GREEN] 麻子仁丸  ids=[89, 248] → canon=248(nihaixia)
- 药集合一致: ✅ | 剂量炮制一致: ✅
- 字段冲突: 0 处 (医学 0 / 非医学 0)
- 关系迁移: 0 (旧 id 挂医案 case_formulas: 0)
