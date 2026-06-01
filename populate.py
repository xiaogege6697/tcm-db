#!/usr/bin/env python3
"""
倪海厦中医知识数据库 - 一键构建脚本
用法:
    python3 populate.py --download   # 仅下载源仓库
    python3 populate.py              # 下载 + 构建数据库
    python3 populate.py --rebuild    # 仅重建数据库（已有源数据）
"""

import sqlite3, re, json, os, sys, subprocess
from pathlib import Path

BASE = Path(__file__).parent.parent  # tcm-project/
DB_PATH = Path(__file__).parent / "tcm_knowledge.db"
SCHEMA = Path(__file__).parent / "schema_v2.sql"

# 源仓库配置
REPOS = {
    "hantang-nihaixia-follower": "https://github.com/9527qingfeng/hantang-nihaixia-follower.git",
    "nihaixia": "https://github.com/JuneYaooo/nihaixia.git",
    "nihaixia-kb": "https://github.com/nivance/nihaixia-kb.git",
    "jangviktor-nihaixia": "https://github.com/jangviktor-web/nihaixia.git",
    "ebook-nihaixia": "https://github.com/elliott10/ebook-nihaixia.git",
    "hantang-notes": "https://github.com/wdsheng999/hantang_medicine.git",
    "renji-notes": "https://github.com/privateheart/renji.git",
}

# ============================================================
# 下载源仓库
# ============================================================
def download_repos():
    print("📥 下载源仓库...\n")
    for name, url in REPOS.items():
        target = BASE / name
        if target.exists():
            print(f"   ✅ 已存在: {name}")
            continue
        print(f"   ⬇️  克隆: {name}...")
        subprocess.run(["git", "clone", "--depth", "1", url, str(target)],
                      capture_output=True)
        print(f"   ✅ 完成: {name}")
    print()

# ============================================================
# 工具函数
# ============================================================
def read_file(path):
    for enc in ['utf-8', 'gbk', 'latin-1']:
        try: return Path(path).read_text(encoding=enc)
        except: pass
    return ""

def parse_fm(raw):
    meta = {}
    if not raw.startswith("---"): return meta
    try:
        end = raw.index("---", 3)
        for line in raw[3:end].strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"): continue
            m = re.match(r'(\S+):\s*\[(.+?)\]', line)
            if m: meta[m.group(1)] = [x.strip().strip('"') for x in m.group(2).split(',')]; continue
            m = re.match(r'(\S+):\s*"([^"]*)"', line)
            if m: meta[m.group(1)] = m.group(2); continue
            m = re.match(r'(\S+):\s*(.+)', line)
            if m: meta[m.group(1)] = m.group(2).strip().strip('"')
    except: pass
    return meta

def to_str(v):
    if isinstance(v, list): return ",".join(str(x) for x in v)
    return str(v) if v else ""

def wc(text): return len(text) if text else 0

# ============================================================
# 数据库初始化
# ============================================================
def init_db():
    if DB_PATH.exists(): DB_PATH.unlink()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    with open(SCHEMA) as f: conn.executescript(f.read())
    conn.commit()
    return conn

# ============================================================
# 主构建流程
# ============================================================
def build():
    print("🏥 构建倪海厦中医知识数据库\n")
    
    HANTANG = BASE / "hantang-nihaixia-follower" / "倪海厦"
    NIHAIXIA = BASE / "nihaixia"
    FOLK = BASE / "hantang-nihaixia-follower" / "妙方收集"
    SELECTED = BASE / "hantang-nihaixia-follower" / "精选书籍"
    XIAOBIAN = BASE / "hantang-nihaixia-follower" / "小编医案"
    NEW = BASE
    
    conn = init_db()
    
    # ... (完整构建逻辑在 GitHub 仓库中)
    # 此脚本为骨架，实际构建需配合各源仓库
    print("⚠️ 请使用 --download 先下载源仓库，再运行构建")
    print("   完整构建脚本见 GitHub 仓库说明")
    
    conn.close()

if __name__ == '__main__':
    if '--download' in sys.argv:
        download_repos()
    elif '--rebuild' in sys.argv:
        build()
    else:
        download_repos()
        build()
