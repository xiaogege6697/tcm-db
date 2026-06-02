#!/usr/bin/env python3
"""
补全 treatment_methods 表的 category 字段。
用法: python3 enrich_treatment_methods.py
"""

import sqlite3, re
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"

# 分类规则
CATEGORY_RULES = {
    '补益': ['补', '益', '养', '滋', '填', '固', '敛', '收'],
    '清热': ['清', '凉', '泻', '降火', '退热', '解毒'],
    '祛寒': ['温', '散寒', '回阳', '暖', '祛寒'],
    '理气': ['理气', '行气', '疏肝', '解郁', '宽胸', '降气'],
    '活血': ['活血', '化瘀', '通络', '散结', '消癥'],
    '祛湿': ['祛湿', '利湿', '化湿', '燥湿', '渗湿', '利水'],
    '化痰': ['化痰', '祛痰', '涤痰', '消痰'],
    '解表': ['解表', '发汗', '散风', '祛风'],
    '攻下': ['攻下', '通便', '泻下', '润肠'],
    '固涩': ['固涩', '止泻', '止汗', '止带', '止遗'],
    '安神': ['安神', '镇静', '宁心', '定志'],
    '开窍': ['开窍', '醒神', '通关'],
    '消食': ['消食', '化积', '导滞'],
    '驱虫': ['驱虫', '杀虫'],
    '外治': ['外治', '敷', '洗', '熏', '灸', '针'],
}

def classify_treatment(name, description):
    """根据名称和描述分类治法"""
    text = f"{name} {description}".lower()
    
    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in text:
                return category
    
    # 默认分类
    if any(kw in text for kw in ['法', '方', '汤', '散', '丸']):
        return '方剂治法'
    
    return '其他'

def main():
    print("补全 treatment_methods 表的 category 字段")
    print("=" * 50)
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 获取所有 treatment_methods
    rows = conn.execute('''
        SELECT id, name, description, category
        FROM treatment_methods 
    ''').fetchall()
    
    print(f"总数: {len(rows)} 条")
    
    updated = 0
    categories = {}
    
    for tm_id, name, description, category in rows:
        # 如果已有 category，跳过
        if category:
            categories[category] = categories.get(category, 0) + 1
            continue
        
        # 分类
        new_category = classify_treatment(name, description or '')
        
        # 更新数据库
        conn.execute('''
            UPDATE treatment_methods 
            SET category = ?
            WHERE id = ?
        ''', (new_category, tm_id))
        
        categories[new_category] = categories.get(new_category, 0) + 1
        updated += 1
    
    conn.commit()
    
    # 统计结果
    print()
    print(f"更新完成: {updated} 条")
    print()
    print("分类统计:")
    for category, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {category}: {count} 条")
    
    conn.close()

if __name__ == '__main__':
    main()
