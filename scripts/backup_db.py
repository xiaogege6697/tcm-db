#!/usr/bin/env python3
"""tcm-db WAL 安全备份工具（纯标准库）。

用 sqlite3.Connection.backup() API 做在线热备（自动合并 -wal 中未 checkpoint 的页），
生成带时间戳的备份文件（不覆盖旧备份），并对源库与备份分别做：
- PRAGMA integrity_check
- SHA-256
- 表数量、各表行数（源 vs 备份必须一致）

用法:
    python3 scripts/backup_db.py
    python3 scripts/backup_db.py --source /path/to.db --dest-dir /path/to/backups

退出码 0 = 备份有效；1 = 异常。
"""
import sqlite3
import hashlib
import sys
import argparse
from pathlib import Path
from datetime import datetime


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def db_signature(db_path):
    """返回 (表数, {表: 行数}, integrity_check 结果)"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    counts = {}
    for t in tables:
        counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    return len(tables), counts, integrity


def backup(source, dest_dir):
    src = Path(source).resolve()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"tcm_knowledge-backup-{ts}.db"

    if not src.exists():
        print(f"❌ 源库不存在: {src}", file=sys.stderr)
        return False, None, None

    # 1. 源签名（备份前快照）
    src_tables, src_counts, src_integ = db_signature(src)

    # 2. backup API 在线热备（自动合并 WAL）
    src_conn = sqlite3.connect(str(src))
    src_conn.execute("PRAGMA foreign_keys = ON")
    dst_conn = sqlite3.connect(str(dest_path))
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    # 3. 备份签名
    dst_tables, dst_counts, dst_integ = db_signature(dest_path)
    sha = sha256_file(dest_path)

    # 4. 校验
    same_tables = src_tables == dst_tables
    same_counts = src_counts == dst_counts
    integ_ok = (src_integ == 'ok' and dst_integ == 'ok')
    ok = same_tables and same_counts and integ_ok

    print(f"备份文件 : {dest_path}")
    print(f"SHA-256  : {sha}")
    print(f"大小     : {dest_path.stat().st_size:,} bytes")
    print(f"表数     : 源 {src_tables} / 备份 {dst_tables} {'✅' if same_tables else '❌'}")
    print(f"integrity: 源={src_integ} 备份={dst_integ} {'✅' if integ_ok else '❌'}")
    print(f"行数一致 : {'✅' if same_counts else '❌ MISMATCH'}")
    if not same_counts:
        for t, n in src_counts.items():
            if dst_counts.get(t) != n:
                print(f"   ❌ {t}: 源 {n} / 备份 {dst_counts.get(t)}")
    print(f"\n=== {'✅ 备份有效' if ok else '❌ 备份异常，请检查'} ===")
    return ok, dest_path, sha


if __name__ == '__main__':
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="tcm-db WAL 安全备份")
    ap.add_argument('--source', default=str(here.parent / 'tcm_knowledge.db'))
    ap.add_argument('--dest-dir', default=str(here.parent / 'backups'))
    args = ap.parse_args()
    ok, path, sha = backup(args.source, args.dest_dir)
    sys.exit(0 if ok else 1)
