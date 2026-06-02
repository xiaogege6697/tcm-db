#!/usr/bin/env python3
"""
从方剂表的 composition 字段提取药物，建立 formula_herbs 关联。
用法: python3 populate_formula_herbs.py
"""

import sqlite3, re, json
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"

def normalize_herb_name(name):
    """标准化药名，用于匹配"""
    # 去除空格
    name = name.strip()
    # 去除常见前缀/后缀
    name = re.sub(r'^(生|熟|炙|炒|酒|醋|盐|姜|蜜|土|麸|煅|煨|炮|制)', '', name)
    # 去除剂量信息
    name = re.sub(r'\d+.*$', '', name)
    # 去除括号内容
    name = re.sub(r'[（(].*?[）)]', '', name)
    return name.strip()

def extract_herbs_from_composition(composition):
    """从 composition 字段提取药物列表"""
    if not composition:
        return []
    
    # 按逗号分割
    herbs = []
    for part in composition.split(','):
        part = part.strip()
        if not part:
            continue
        
        # 去除剂量信息（如 "桂枝三钱" -> "桂枝"）
        herb_name = re.sub(r'[一二三四五六七八九十百千万\d]+[钱两克斤升斗个枚条]', '', part)
        herb_name = herb_name.strip()
        
        if herb_name:
            herbs.append(herb_name)
    
    return herbs

def match_herb_to_database(herb_name, herbs_dict):
    """将药名匹配到数据库中的 herb_id"""
    # 精确匹配
    if herb_name in herbs_dict:
        return herbs_dict[herb_name]
    
    # 标准化后匹配
    normalized = normalize_herb_name(herb_name)
    if normalized in herbs_dict:
        return herbs_dict[normalized]
    
    # 部分匹配（药名包含在数据库药名中，或反之）
    for db_name, herb_id in herbs_dict.items():
        if herb_name in db_name or db_name in herb_name:
            return herb_id
    
    return None

def populate_formula_herbs(conn):
    """填充 formula_herbs 表"""
    # 获取所有 herbs
    rows = conn.execute('SELECT id, name FROM herbs').fetchall()
    herbs_dict = {r[1]: r[0] for r in rows}
    
    # 获取所有 formulas
    rows = conn.execute('''
        SELECT id, name, composition
        FROM formulas 
        WHERE composition IS NOT NULL AND composition != ""
    ''').fetchall()
    
    inserted = 0
    skipped = 0
    unmatched_herbs = set()
    
    for formula_id, formula_name, composition in rows:
        # 提取药物
        herbs = extract_herbs_from_composition(composition)
        
        for herb_name in herbs:
            # 匹配到数据库
            herb_id = match_herb_to_database(herb_name, herbs_dict)
            
            if herb_id:
                # 插入关联
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO formula_herbs (formula_id, herb_id, role)
                        VALUES (?, ?, ?)
                    ''', (formula_id, herb_id, '未知'))
                    inserted += 1
                except Exception as e:
                    skipped += 1
            else:
                unmatched_herbs.add(herb_name)
                skipped += 1
    
    return inserted, skipped, unmatched_herbs

def main():
    print("填充 formula_herbs 表")
    print("=" * 50)
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 检查表结构
    try:
        conn.execute('SELECT * FROM formula_herbs LIMIT 1')
        print("formula_herbs 表已存在")
    except:
        print("创建 formula_herbs 表...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS formula_herbs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                formula_id INTEGER NOT NULL,
                herb_id INTEGER NOT NULL,
                role TEXT DEFAULT '未知',
                FOREIGN KEY (formula_id) REFERENCES formulas(id),
                FOREIGN KEY (herb_id) REFERENCES herbs(id),
                UNIQUE(formula_id, herb_id)
            )
        ''')
    
    # 统计当前状态
    cnt = conn.execute('SELECT COUNT(*) FROM formula_herbs').fetchone()[0]
    print(f"当前记录数: {cnt}")
    
    print()
    print("开始填充...")
    inserted, skipped, unmatched = populate_formula_herbs(conn)
    
    conn.commit()
    
    # 统计填充后状态
    cnt_after = conn.execute('SELECT COUNT(*) FROM formula_herbs').fetchone()[0]
    print()
    print(f"填充后记录数: {cnt_after} (+{cnt_after - cnt})")
    
    print()
    print(f"结果:")
    print(f"  新增关联: {inserted} 条")
    print(f"  跳过: {skipped} 条")
    print(f"  未匹配的药物: {len(unmatched)} 种")
    
    if unmatched:
        print(f"  未匹配药物示例: {list(unmatched)[:10]}")
    
    # 显示一些示例
    print()
    print("示例关联:")
    rows = conn.execute('''
        SELECT f.name as formula_name, h.name as herb_name, fh.role
        FROM formula_herbs fh
        JOIN formulas f ON fh.formula_id = f.id
        JOIN herbs h ON fh.herb_id = h.id
        LIMIT 10
    ''').fetchall()
    for r in rows:
        print(f"  {r[0]} -> {r[1]} ({r[2]})")
    
    conn.close()

if __name__ == '__main__':
    main()
