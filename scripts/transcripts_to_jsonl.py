#!/usr/bin/env python3
"""
transcripts_to_jsonl.py — 板书 OCR 转录 md → 分条 JSONL 中间格式
用法:
    python3 scripts/transcripts_to_jsonl.py assets/transcripts/jingui.md \
        --book "金匮要略" --out artifacts/jingui.jsonl
设计见 docs/transcript-pipeline.md
"""
import re, json, hashlib, argparse, sys
from pathlib import Path

# ---------- 行级过滤 ----------
SKIP_PATTERNS = [
    re.compile(r'^\[转录失败'),
    re.compile(r'^\[低价值'),
    re.compile(r'^\[无文字'),
    re.compile(r'^\[图表页'),       # 图表页整体转不动的，跳过（标记在报告中）
]
DUP_REF = re.compile(r'^同(\d{4})')  # "同0012：……"

# ---------- 章节识别 ----------
CH_PATTERNS = [
    re.compile(r'([一二三四五六七八九十百]+、[\u4e00-\u9fff]{2,14}脈證[并並]治)'),
    re.compile(r'([\u4e00-\u9fff]{2,12}病脈證[并並]治第[一二三四五六七八九十]+)'),
    re.compile(r'(續傷寒霍亂篇)'),
    re.compile(r'(辨[\u4e00-\u9fff]{1,8}病脈證[并並]治[上中下]?篇?)'),
]

# ---------- 方名识别 ----------
FORMULA_RE = re.compile(
    r'([\u4e00-\u9fff]{1,10}(?:去[\u4e00-\u9fff]+加[\u4e00-\u9fff]+)?)'
    r'(湯|丸|散|方)(?:主之|亦主之|方見上|方)'
)
# 条文编号： "四、" "十五、" 等
CLAUSE_RE = re.compile(r'^([一二三四五六七八九十]+)、')

# ---------- 通用清洗 ----------
WATERMARK = re.compile(r'UP主[\u4e00-\u9fff]{2,8}|JP主[\u4e00-\u9fff]{2,8}')
HEADER = re.compile(r'^#{1,3}\s*(图中文字转录|转录内容|转录|图中文字|图内文字转录|图中文字转录如下)\s*')
CAPTION_RE = re.compile(r'(?:底部字幕|字幕[（(]?[^）)]*[）)]?|字幕：)\s*[:：]?\s*(.{2,60})')

def clean_text(s: str) -> str:
    s = WATERMARK.sub('', s)
    s = HEADER.sub('', s.strip())
    s = s.replace('｜', '|')
    return s.strip()

def norm_for_hash(s: str) -> str:
    """去掉标点/空白后取 hash，用于跨帧去重"""
    return re.sub(r'[\s，。、；：「」『』（）()\[\]〔〕*#>|]|（字形存疑.*?）|〔\?〕', '', s)

def extract_reading(cell: str) -> str:
    """后期详细格式：优先『连读』块，其次拼 quote 行（> 开头的正文），再退原始单元格"""
    m = re.search(r'(?:连读全文|按语义连读|连读成文|语义连读|连读)\s*[：:]*\s*(.+?)(?:\*\*|$)', cell, re.S)
    if m:
        return m.group(1).strip()
    quotes = re.findall(r'^>\s*(.+)$', cell, re.M)
    if not quotes and '>' in cell:
        # 表格行内联引用：竖排断句以 “ > ” 分隔，直接拼接
        parts = [p.strip() for p in re.split(r'\s*>\s*', cell) if p.strip()]
        noise = re.compile(r'水印|字幕|说明|注[：:]|连读|黑板|示意图|未写完|裁切|截断|画面|——|^\*\*|版式|旁注|板书')
        quotes = [p for p in parts if len(p) >= 4 and not noise.search(p[:10])]
    if quotes:
        body = [q.strip() for q in quotes if len(q.strip()) >= 2]
        if body:
            return ''.join(body)
    return cell.strip()

def split_rows(md: str):
    """解析 md 表格行 → (图号, 单元格文本)"""
    for line in md.splitlines():
        line = line.strip()
        m = re.match(r'^\|\s*(\d{3,4})\s*\|\s*(.+?)\s*\|?\s*$', line)
        if m:
            yield m.group(1), m.group(2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--book', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-chars', type=int, default=25, help='短于此的碎条不输出（多为字幕残句）')
    args = ap.parse_args()

    md = Path(args.input).read_text(encoding='utf-8')
    entries = {}          # hash -> entry
    skipped = {'dup_ref': 0, 'skip_tag': 0, 'short': 0, 'dup_hash': 0}
    chapter_cache = None

    for img_id, cell in split_rows(md):
        cell = clean_text(cell)
        # 1) 显式跳过
        if any(p.search(cell) for p in SKIP_PATTERNS):
            skipped['skip_tag'] += 1
            continue
        # 2) "同NNNN" 引用帧
        if DUP_REF.match(cell):
            skipped['dup_ref'] += 1
            continue
        # 3) 提取正文（后期格式取连读块）
        text = clean_text(extract_reading(cell))
        # 4) 章节归属（显式命中才更新缓存，否则继承，flag 区分）
        chapter = chapter_cache
        chapter_src = 'inherited'
        for pat in CH_PATTERNS:
            m = pat.search(text[:60])
            if m:
                chapter = m.group(1)
                chapter_cache = chapter
                chapter_src = 'explicit'
                text = text.replace(chapter, '', 1).strip()
                break
        # 5) 字幕（若有，剥离出独立字段）
        caption = ''
        cm = CAPTION_RE.search(text)
        if cm:
            caption = cm.group(1).strip()
        # 6) 方名
        formulas = []
        for m in FORMULA_RE.finditer(text):
            name = m.group(1) + m.group(2)
            if name not in formulas:
                formulas.append(name)
        # 7) 长度门槛 + 跨帧去重
        if len(norm_for_hash(text)) < args.min_chars:
            skipped['short'] += 1
            continue
        h = hashlib.sha1(norm_for_hash(text).encode()).hexdigest()[:16]
        if h in entries:
            entries[h]['image_ids'].append(img_id)
            skipped['dup_hash'] += 1
            continue
        entries[h] = {
            'id': f"{args.book}-{h[:8]}",
            'book': args.book,
            'chapter': chapter,
            'chapter_source': chapter_src,
            'text': text,
            'formula_names': formulas,
            'caption': caption,
            'image_ids': [img_id],
            'source_file': str(args.input),
            'content_hash': h,
            'flags': {
                'has_doubt_mark': ('存疑' in cell) or ('？' in cell and '？]' not in cell),
                'has_truncation': ('未完' in cell) or ('裁切' in cell) or ('截断' in cell),
                'from_verbose_format': ('连读' in cell),
            },
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(entries.values(), key=lambda e: e['image_ids'][0])
    with out.open('w', encoding='utf-8') as f:
        for e in rows:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    print(f"✅ {len(rows)} entries → {out}")
    print(f"   skipped: {skipped}")
    f_cnt = sum(1 for e in rows if e['formula_names'])
    t_cnt = sum(1 for e in rows if e['flags']['has_truncation'])
    print(f"   含方名 {f_cnt} 条 / 疑截断 {t_cnt} 条 / 疑存疑 {sum(1 for e in rows if e['flags']['has_doubt_mark'])} 条")

if __name__ == '__main__':
    main()
