#!/usr/bin/env python3
"""
填充所有关系表：formula_syndromes, syndrome_symptoms, case_formulas, case_herbs
用法: python3 populate_relationship_tables.py
"""

import sqlite3, re, json
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"

def extract_formulas_from_text(text):
    """从文本中提取方剂名称"""
    if not text:
        return []
    
    # 常见方剂名称模式
    formula_patterns = [
        r'([一-龥]{2,6}汤)',
        r'([一-龥]{2,6}丸)',
        r'([一-龥]{2,6}散)',
        r'([一-龥]{2,6}饮)',
        r'([一-龥]{2,6}膏)',
        r'([一-龥]{2,6}丹)',
    ]
    
    formulas = []
    for pattern in formula_patterns:
        matches = re.findall(pattern, text)
        formulas.extend(matches)
    
    # 去重
    return list(set(formulas))

def extract_herbs_from_text(text):
    """从文本中提取药物名称"""
    if not text:
        return []
    
    # 按行分割
    lines = text.split('\n')
    herbs = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 跳过非药物行
        if any(kw in line for kw in ['付', '碗', '煮', '服', '次', '日', '帖', '包', '颗', '丸']):
            continue
        
        # 提取药物名称（去除剂量）
        # 格式: "药名 + 剂量" 或 "药名"
        parts = re.split(r'[一二三四五六七八九十百千万\d]+[钱两克斤升斗个枚条]', line)
        for part in parts:
            part = part.strip()
            # 去除括号内容
            part = re.sub(r'[（(].*?[）)]', '', part)
            part = part.strip()
            
            # 检查是否是有效的药名（2-4个汉字）
            if re.match(r'^[一-龥]{2,4}$', part):
                herbs.append(part)
    
    return list(set(herbs))

def match_formula_to_database(formula_name, formulas_dict):
    """将方剂名匹配到数据库中的 formula_id"""
    # 精确匹配
    if formula_name in formulas_dict:
        return formulas_dict[formula_name]
    
    # 部分匹配
    for db_name, formula_id in formulas_dict.items():
        if formula_name in db_name or db_name in formula_name:
            return formula_id
    
    return None

def match_herb_to_database(herb_name, herbs_dict):
    """将药名匹配到数据库中的 herb_id"""
    # 精确匹配
    if herb_name in herbs_dict:
        return herbs_dict[herb_name]
    
    # 部分匹配
    for db_name, herb_id in herbs_dict.items():
        if herb_name in db_name or db_name in herb_name:
            return herb_id
    
    return None

def populate_formula_syndromes(conn):
    """填充 formula_syndromes 表"""
    # 获取所有 formulas
    rows = conn.execute('SELECT id, name FROM formulas').fetchall()
    formulas_dict = {r[1]: r[0] for r in rows}
    
    # 获取所有 syndromes
    rows = conn.execute('''
        SELECT id, name, representative_formulas
        FROM syndromes 
        WHERE representative_formulas IS NOT NULL AND representative_formulas != ""
    ''').fetchall()
    
    inserted = 0
    skipped = 0
    
    for syndrome_id, syndrome_name, rep_formulas in rows:
        # 提取方剂名称
        formulas = extract_formulas_from_text(rep_formulas)
        
        for formula_name in formulas:
            # 匹配到数据库
            formula_id = match_formula_to_database(formula_name, formulas_dict)
            
            if formula_id:
                # 插入关联
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO formula_syndromes (formula_id, syndrome_id)
                        VALUES (?, ?)
                    ''', (formula_id, syndrome_id))
                    inserted += 1
                except Exception as e:
                    skipped += 1
            else:
                skipped += 1
    
    return inserted, skipped

def populate_syndrome_symptoms(conn):
    """填充 syndrome_symptoms 表"""
    # 获取所有 syndromes
    rows = conn.execute('''
        SELECT id, name, core_symptoms
        FROM syndromes 
        WHERE core_symptoms IS NOT NULL AND core_symptoms != ""
    ''').fetchall()
    
    syndromes_data = [(r[0], r[1], r[2]) for r in rows]
    
    # 获取所有 symptoms
    rows = conn.execute('SELECT id, name FROM symptoms').fetchall()
    symptoms_dict = {r[1]: r[0] for r in rows}
    
    inserted = 0
    skipped = 0
    
    for syndrome_id, syndrome_name, core_symptoms in syndromes_data:
        # 从 core_symptoms 提取症状
        # core_symptoms 可能是 JSON 数组或逗号分隔的字符串
        try:
            if core_symptoms.startswith('['):
                symptoms_list = json.loads(core_symptoms)
            else:
                symptoms_list = [s.strip() for s in core_symptoms.split(',')]
        except:
            symptoms_list = [core_symptoms]
        
        for symptom_name in symptoms_list:
            symptom_name = symptom_name.strip()
            if not symptom_name:
                continue
            
            # 匹配到数据库
            symptom_id = None
            for db_name, sid in symptoms_dict.items():
                if symptom_name in db_name or db_name in symptom_name:
                    symptom_id = sid
                    break
            
            if symptom_id:
                # 插入关联
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO syndrome_symptoms (syndrome_id, symptom_id)
                        VALUES (?, ?)
                    ''', (syndrome_id, symptom_id))
                    inserted += 1
                except Exception as e:
                    skipped += 1
            else:
                skipped += 1
    
    return inserted, skipped

def populate_case_formulas(conn):
    """填充 case_formulas 表"""
    # 获取所有 formulas
    rows = conn.execute('SELECT id, name FROM formulas').fetchall()
    formulas_dict = {r[1]: r[0] for r in rows}
    
    # 获取所有 clinical_cases with herbal_rx
    rows = conn.execute('''
        SELECT id, patient_id, herbal_rx
        FROM clinical_cases 
        WHERE herbal_rx IS NOT NULL AND herbal_rx != ""
    ''').fetchall()
    
    inserted = 0
    skipped = 0
    
    for case_id, patient_id, herbal_rx in rows:
        # 提取方剂名称
        formulas = extract_formulas_from_text(herbal_rx)
        
        for formula_name in formulas:
            # 匹配到数据库
            formula_id = match_formula_to_database(formula_name, formulas_dict)
            
            if formula_id:
                # 插入关联
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO case_formulas (case_id, formula_id)
                        VALUES (?, ?)
                    ''', (case_id, formula_id))
                    inserted += 1
                except Exception as e:
                    skipped += 1
            else:
                skipped += 1
    
    return inserted, skipped

def populate_case_herbs(conn):
    """填充 case_herbs 表"""
    # 获取所有 herbs
    rows = conn.execute('SELECT id, name FROM herbs').fetchall()
    herbs_dict = {r[1]: r[0] for r in rows}
    
    # 获取所有 clinical_cases with herbal_rx
    rows = conn.execute('''
        SELECT id, patient_id, herbal_rx
        FROM clinical_cases 
        WHERE herbal_rx IS NOT NULL AND herbal_rx != ""
    ''').fetchall()
    
    inserted = 0
    skipped = 0
    
    for case_id, patient_id, herbal_rx in rows:
        # 提取药物名称
        herbs = extract_herbs_from_text(herbal_rx)
        
        for herb_name in herbs:
            # 匹配到数据库
            herb_id = match_herb_to_database(herb_name, herbs_dict)
            
            if herb_id:
                # 插入关联
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO case_herbs (case_id, herb_id)
                        VALUES (?, ?)
                    ''', (case_id, herb_id))
                    inserted += 1
                except Exception as e:
                    skipped += 1
            else:
                skipped += 1
    
    return inserted, skipped

def main():
    print("填充所有关系表")
    print("=" * 50)
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 检查表结构
    tables = ['formula_syndromes', 'syndrome_symptoms', 'case_formulas', 'case_herbs']
    for t in tables:
        try:
            conn.execute(f'SELECT * FROM {t} LIMIT 1')
            print(f"{t} 表已存在")
        except:
            print(f"创建 {t} 表...")
            if t == 'formula_syndromes':
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS formula_syndromes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        formula_id INTEGER NOT NULL,
                        syndrome_id INTEGER NOT NULL,
                        FOREIGN KEY (formula_id) REFERENCES formulas(id),
                        FOREIGN KEY (syndrome_id) REFERENCES syndromes(id),
                        UNIQUE(formula_id, syndrome_id)
                    )
                ''')
            elif t == 'syndrome_symptoms':
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS syndrome_symptoms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        syndrome_id INTEGER NOT NULL,
                        symptom_id INTEGER NOT NULL,
                        FOREIGN KEY (syndrome_id) REFERENCES syndromes(id),
                        FOREIGN KEY (symptom_id) REFERENCES symptoms(id),
                        UNIQUE(syndrome_id, symptom_id)
                    )
                ''')
            elif t == 'case_formulas':
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS case_formulas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id INTEGER NOT NULL,
                        formula_id INTEGER NOT NULL,
                        FOREIGN KEY (case_id) REFERENCES clinical_cases(id),
                        FOREIGN KEY (formula_id) REFERENCES formulas(id),
                        UNIQUE(case_id, formula_id)
                    )
                ''')
            elif t == 'case_herbs':
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS case_herbs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id INTEGER NOT NULL,
                        herb_id INTEGER NOT NULL,
                        FOREIGN KEY (case_id) REFERENCES clinical_cases(id),
                        FOREIGN KEY (herb_id) REFERENCES herbs(id),
                        UNIQUE(case_id, herb_id)
                    )
                ''')
    
    print()
    
    # 填充各表
    print("开始填充...")
    
    print("\n1. formula_syndromes:")
    inserted, skipped = populate_formula_syndromes(conn)
    print(f"   新增: {inserted}, 跳过: {skipped}")
    
    print("\n2. syndrome_symptoms:")
    inserted, skipped = populate_syndrome_symptoms(conn)
    print(f"   新增: {inserted}, 跳过: {skipped}")
    
    print("\n3. case_formulas:")
    inserted, skipped = populate_case_formulas(conn)
    print(f"   新增: {inserted}, 跳过: {skipped}")
    
    print("\n4. case_herbs:")
    inserted, skipped = populate_case_herbs(conn)
    print(f"   新增: {inserted}, 跳过: {skipped}")
    
    conn.commit()
    
    # 统计最终状态
    print()
    print("最终状态:")
    for t in tables:
        cnt = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f"  {t}: {cnt} 条记录")
    
    conn.close()

if __name__ == '__main__':
    main()
