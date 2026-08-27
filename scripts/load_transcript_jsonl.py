#!/usr/bin/env python3
"""load_transcript_jsonl.py — OCR 转写 JSONL 增量入库（docs/transcript-pipeline.md 设计的执行器）

用法:
    python3 scripts/load_transcript_jsonl.py artifacts/jingui.jsonl --db tcm_knowledge.db [--dry-run]

行为:
  - classics: 每条非隔离条文一行，content_hash 幂等去重（含存量行清洗比对）
  - formulas: formula_names 非空的条目生成候选行（不与现有方剂合并），不写 name 冲突判定
  - evidence: 每条 classics/formulas 行挂 image 溯源（dedupe_key 幂等）
  - ingestion_quarantine: has_doubt_mark / has_truncation 条目隔离
  - schema 小改（自动，幂等）:
      * classics 加 content_hash 列
      * ingestion_quarantine reason_code 枚举扩 ocr_low_confidence / ocr_truncated（重建表保数据）
铁律: 只增不删，全部走事务，失败回滚。
"""
import argparse, json, re, sqlite3, sys, hashlib, datetime

NEW_REASON_CODES = ("ocr_low_confidence", "ocr_truncated")

def get_reason_codes(conn):
    sql = next(r[0] for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestion_quarantine'"))
    m = re.search(r"reason_code\s+TEXT\s+NOT NULL\s+CHECK\s*\(reason_code IN \((.*?)\)\)", sql, re.S)
    return re.findall(r"'([^']+)'", m.group(1)) if m else []

def ensure_schema(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(classics)")]
    if "content_hash" not in cols:
        conn.execute("ALTER TABLE classics ADD COLUMN content_hash TEXT")
    codes = get_reason_codes(conn)
    if not all(c in codes for c in NEW_REASON_CODES):
        old_sql = next(r[0] for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ingestion_quarantine'"))
        new_sql = old_sql.replace("ingestion_quarantine", "ingestion_quarantine_new", 1)
        # 扩枚举：在最后一个 code 后追加
        last = codes[-1]
        new_sql = new_sql.replace(f"'{last}')", f"'{last}'," + ",".join(f"'{c}'" for c in NEW_REASON_CODES) + ")", 1)
        conn.execute(new_sql)
        conn.execute("""INSERT INTO ingestion_quarantine_new SELECT * FROM ingestion_quarantine""")
        conn.execute("DROP TABLE ingestion_quarantine")
        conn.execute("ALTER TABLE ingestion_quarantine_new RENAME TO ingestion_quarantine")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quar_source ON ingestion_quarantine(source_table, source_record_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quar_run ON ingestion_quarantine(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quar_content ON ingestion_quarantine(content_hash)")

def clean_for_hash(text):
    return re.sub(r"[\s，。、；：？！「」『』（）]", "", text or "")

def existing_classic_hashes(conn):
    """存量 classics 无 content_hash，按清洗文本算补齐后比对"""
    hs = set()
    for cid, content, ch in conn.execute("SELECT id, content, content_hash FROM classics"):
        if ch:
            hs.add(ch)
            continue
        h = hashlib.sha1(clean_for_hash(content).encode()).hexdigest()[:16] if content else ""
        if h:
            hs.add(h)
    return hs

def chapter_num_of(chapter):
    m = re.search(r"第([一二三四五六七八九十百]+)篇?$", chapter or "")
    return m.group(0) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--db", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    conn = sqlite3.connect(a.db)
    conn.isolation_level = None
    run_id = "load-jsonl-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    stats = dict(read=0, classics_inserted=0, classics_dup=0, classics_existing_dup=0,
                 formulas_inserted=0, evidence_inserted=0, quarantined=0, quarantine_dup=0)

    conn.execute("BEGIN")
    try:
        ensure_schema(conn)
        seen_hashes = existing_classic_hashes(conn)
        entries = []
        with open(a.jsonl) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        stats["read"] = len(entries)

        for e in entries:
            flags = e.get("flags", {})
            h = e.get("content_hash") or hashlib.sha1(clean_for_hash(e["text"]).encode()).hexdigest()[:16]

            # 1) quarantine: 存疑或截断
            if flags.get("has_doubt_mark") or flags.get("has_truncation"):
                reason = "ocr_truncated" if flags.get("has_truncation") else "ocr_low_confidence"
                dk = f"transcript|{h}"
                try:
                    conn.execute("""INSERT INTO ingestion_quarantine
                        (source_table, source_record_id, content_hash, raw_record_json, source_repo,
                         source_path, run_id, reason_code, dedupe_key, metadata_json)
                        VALUES ('classics', 0, ?, ?, 'ocr-transcript', ?, ?, ?, ?, json(?))""",
                        (h, json.dumps(e, ensure_ascii=False), e.get("source_file", ""),
                         run_id, reason, dk,
                         json.dumps({"image_ids": e.get("image_ids", []), "flags": flags}, ensure_ascii=False)))
                    stats["quarantined"] += 1
                except sqlite3.IntegrityError:
                    stats["quarantine_dup"] += 1
                continue

            # 2) classics: hash 幂等
            if h in seen_hashes:
                stats["classics_dup"] += 1
                continue
            seen_hashes.add(h)
            raw_path = f"{e.get('source_file','')}#imgs={'|'.join(e.get('image_ids', []))}"
            cur = conn.execute(
                "INSERT INTO classics (book_name, chapter_name, chapter_num, content, annotation, word_count, raw_path, content_hash) VALUES (?,?,?,?,?,?,?,?)",
                (e["book"], e.get("chapter", ""), chapter_num_of(e.get("chapter", "")),
                 e["text"], e.get("caption", "") or None, len(e["text"]), raw_path, h))
            cid = cur.lastrowid
            stats["classics_inserted"] += 1

            # 3) evidence: image 溯源（每 image_id 一行）
            for img in e.get("image_ids", []):
                try:
                    conn.execute("""INSERT INTO evidence
                        (subject_type, subject_id, relation_type, evidence_kind, source_type,
                         source_record_type, source_record_id, source_path, evidence_text,
                         confidence, extraction_method, dedupe_key, metadata_json)
                        VALUES ('classic', ?, 'source_record', 'source_record', 'image',
                                'classic', ?, ?, ?, 0.8, 'etl', ?, json(?))""",
                        (cid, str(img), e.get("source_file", ""), e["text"][:500],
                         f"transcript|{h}|{img}",
                         json.dumps({"jsonl_id": e["id"], "content_hash": h}, ensure_ascii=False)))
                    stats["evidence_inserted"] += 1
                except sqlite3.IntegrityError:
                    pass

            # 4) formulas 候选（不与现有合并）
            for fname in e.get("formula_names", []):
                if not fname:
                    continue
                cur = conn.execute(
                    "INSERT INTO formulas (name, source_book, chapter, commentary, raw_path, source_repo) VALUES (?,?,?,?,?,?)",
                    (fname, e["book"], e.get("chapter", ""), e["text"][:2000], raw_path, "ocr-candidate"))
                fid = cur.lastrowid
                stats["formulas_inserted"] += 1
                for img in e.get("image_ids", [])[:1]:  # 候选行只挂首图
                    try:
                        conn.execute("""INSERT INTO evidence
                            (subject_type, subject_id, relation_type, evidence_kind, source_type,
                             source_record_type, source_record_id, source_path, evidence_text,
                             confidence, extraction_method, dedupe_key, metadata_json)
                            VALUES ('formula', ?, 'source_record', 'source_record', 'image',
                                    'formula', ?, ?, ?, 0.6, 'etl', ?, json(?))""",
                            (fid, str(img), e.get("source_file", ""), fname,
                             f"transcript|{h}|formula|{fname}",
                             json.dumps({"jsonl_id": e["id"], "content_hash": h}, ensure_ascii=False)))
                    except sqlite3.IntegrityError:
                        pass

        if a.dry_run:
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    print(json.dumps({"run_id": run_id, "dry_run": a.dry_run, **stats}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
