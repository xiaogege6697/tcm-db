#!/usr/bin/env python3
"""
从 hantang 仓库的医案文件补全数据库中的结构化字段。
最终版：支持 Markdown 标题格式和纯文本格式。
用法: python3 enrich_hantang_cases.py
"""

import sqlite3, re, os, json
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"
SOURCE_DIR = Path(__file__).parent.parent / "hantang-nihaixia-follower" / "倪海厦" / "倪师医案整理"

def parse_hantang_case(filepath):
    """解析 hantang 仓库的医案文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    case = {}
    
    # 提取标题（第一行）
    lines = text.strip().split('\n')
    if lines:
        title = lines[0].strip().lstrip('#').strip()
        case['name'] = title
    
    # 检查是否有 Markdown 标题
    has_headers = bool(re.search(r'^#{2,3} ', text, re.MULTILINE))
    
    if has_headers:
        # 按 ## 或 ### 分割各个部分
        sections = re.split(r'^#{2,3} ', text, flags=re.MULTILINE)
        
        for section in sections:
            if not section.strip():
                continue
            
            # 提取部分标题和内容
            lines = section.strip().split('\n')
            header = lines[0].strip()
            content = '\n'.join(lines[1:]).strip()
            
            # 来诊日期
            if '来诊日期' in header or '初诊' in header:
                # 提取日期
                date_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', content)
                if date_match:
                    case['case_date'] = date_match.group(1).replace('/', '-')
                
                # 提取性别和年龄
                gender_match = re.search(r'(男|女)', content)
                if gender_match:
                    case['gender'] = gender_match.group(1)
                
                age_match = re.search(r'(\d+)\s*岁', content)
                if age_match:
                    case['age'] = age_match.group(1) + '岁'
            
            # 来诊原因
            elif '来诊原因' in header:
                case['chief_complaint'] = content
            
            # 问诊
            elif '问诊' in header:
                case['inquiry'] = content
            
            # 脉诊
            elif '脉诊' in header:
                case['pulse_diagnosis'] = content
            
            # 望诊
            elif '望诊' in header:
                # 提取舌诊
                tongue_match = re.search(r'舌诊[：:]\s*(.+?)(?=\n|$)', content)
                if tongue_match:
                    case['tongue_diagnosis'] = tongue_match.group(1).strip()
                
                # 提取眼诊
                eye_match = re.search(r'眼诊[：:]\s*(.+?)(?=\n|$)', content)
                if eye_match:
                    case['eye_diagnosis'] = eye_match.group(1).strip()
            
            # 诊断
            elif '诊断' in header and '特殊' not in header:
                case['diagnosis'] = content
            
            # 针灸处方
            elif '针灸处方' in header:
                case['acupuncture_rx'] = content
            
            # 中药处方
            elif '中药处方' in header:
                case['herbal_rx'] = content
            
            # 解说
            elif '解说' in header:
                case['notes'] = content
    
    else:
        # 纯文本格式，使用正则表达式提取
        # 提取日期
        date_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', text)
        if date_match:
            case['case_date'] = date_match.group(1).replace('/', '-')
        
        # 提取性别和年龄
        gender_match = re.search(r'(男|女)', text)
        if gender_match:
            case['gender'] = gender_match.group(1)
        
        age_match = re.search(r'(\d+)\s*岁', text)
        if age_match:
            case['age'] = age_match.group(1) + '岁'
        
        # 提取问诊
        inquiry_match = re.search(r'问诊[：:]\s*(.+?)(?=\n(?:脉诊|望诊|诊断|针灸|中药|解说|备注|$))', text, re.DOTALL)
        if inquiry_match:
            case['inquiry'] = inquiry_match.group(1).strip()
        
        # 提取脉诊
        pulse_match = re.search(r'脉诊[：:]\s*(.+?)(?=\n(?:望诊|诊断|针灸|中药|解说|备注|$))', text, re.DOTALL)
        if pulse_match:
            case['pulse_diagnosis'] = pulse_match.group(1).strip()
        
        # 提取舌诊
        tongue_match = re.search(r'舌诊[：:]\s*(.+?)(?=\n|$)', text)
        if tongue_match:
            case['tongue_diagnosis'] = tongue_match.group(1).strip()
        
        # 提取眼诊
        eye_match = re.search(r'眼诊[：:]\s*(.+?)(?=\n|$)', text)
        if eye_match:
            case['eye_diagnosis'] = eye_match.group(1).strip()
        
        # 提取诊断
        diagnosis_match = re.search(r'诊断[：:]\s*(.+?)(?=\n(?:针灸|中药|解说|备注|$))', text, re.DOTALL)
        if diagnosis_match:
            case['diagnosis'] = diagnosis_match.group(1).strip()
        
        # 提取针灸处方
        acupuncture_match = re.search(r'针灸处方[：:]\s*(.+?)(?=\n(?:中药|解说|备注|$))', text, re.DOTALL)
        if acupuncture_match:
            case['acupuncture_rx'] = acupuncture_match.group(1).strip()
        
        # 提取中药处方
        herbal_match = re.search(r'中药处方[：:]\s*(.+?)(?=\n(?:解说|备注|$))', text, re.DOTALL)
        if herbal_match:
            case['herbal_rx'] = herbal_match.group(1).strip()
        
        # 提取解说
        notes_match = re.search(r'解说[：:]\s*(.+?)(?=\n(?:备注|$))', text, re.DOTALL)
        if notes_match:
            case['notes'] = notes_match.group(1).strip()
    
    return case

def match_and_update(conn):
    """匹配源文件和数据库记录，更新数据库"""
    # 获取所有 hantang 来源的医案
    rows = conn.execute('''
        SELECT id, patient_id, case_date, chief_complaint
        FROM clinical_cases 
        WHERE source_repo = "hantang"
        ORDER BY id
    ''').fetchall()
    
    # 按 patient_id 分组
    db_cases = {}
    for r in rows:
        pid = r[1]
        if pid not in db_cases:
            db_cases[pid] = []
        db_cases[pid].append({
            'id': r[0], 
            'original_pid': pid,
            'case_date': r[2], 
            'complaint': r[3],
            '_used': False
        })
    
    updated = 0
    matched_files = 0
    no_match_cases = 0
    
    # 遍历所有源文件
    for filepath in SOURCE_DIR.rglob('*.md'):
        # 跳过非医案文件
        if 'README' in filepath.name or 'INDEX' in filepath.name:
            continue
        
        # 解析文件
        try:
            case = parse_hantang_case(filepath)
        except Exception as e:
            if no_match_cases <= 10:
                print(f'  解析错误: {filepath.name}: {e}')
            no_match_cases += 1
            continue
        
        if not case.get('chief_complaint') and not case.get('diagnosis') and not case.get('inquiry'):
            continue
        
        matched_files += 1
        file_stem = filepath.stem
        
        # 尝试匹配数据库记录
        matched_db = None
        
        # 方式1: 文件名匹配 patient_id
        if file_stem in db_cases:
            for db in db_cases[file_stem]:
                if not db['_used']:
                    matched_db = db
                    break
        
        # 方式2: 按日期匹配
        if not matched_db and case.get('case_date'):
            for pid, dbs in db_cases.items():
                for db in dbs:
                    if not db['_used'] and db['case_date'] == case['case_date']:
                        matched_db = db
                        break
                if matched_db:
                    break
        
        # 方式3: 按主诉匹配
        if not matched_db and case.get('chief_complaint'):
            complaint_short = case['chief_complaint'][:50]
            for pid, dbs in db_cases.items():
                for db in dbs:
                    if not db['_used'] and db['complaint'] and complaint_short in db['complaint']:
                        matched_db = db
                        break
                if matched_db:
                    break
        
        if matched_db:
            matched_db['_used'] = True
            # 更新数据库
            conn.execute('''
                UPDATE clinical_cases SET
                    gender = COALESCE(NULLIF(?, ''), gender),
                    age = COALESCE(NULLIF(?, ''), age),
                    chief_complaint = CASE WHEN ? != '' THEN ? ELSE chief_complaint END,
                    inquiry = COALESCE(NULLIF(?, ''), inquiry),
                    pulse_diagnosis = COALESCE(NULLIF(?, ''), pulse_diagnosis),
                    tongue_diagnosis = COALESCE(NULLIF(?, ''), tongue_diagnosis),
                    eye_diagnosis = COALESCE(NULLIF(?, ''), eye_diagnosis),
                    diagnosis = CASE WHEN ? != '' THEN ? ELSE diagnosis END,
                    acupuncture_rx = COALESCE(NULLIF(?, ''), acupuncture_rx),
                    herbal_rx = COALESCE(NULLIF(?, ''), herbal_rx),
                    notes = COALESCE(NULLIF(?, ''), notes)
                WHERE id = ?
            ''', (
                case.get('gender', ''),
                case.get('age', ''),
                case.get('chief_complaint', ''), case.get('chief_complaint', ''),
                case.get('inquiry', ''),
                case.get('pulse_diagnosis', ''),
                case.get('tongue_diagnosis', ''),
                case.get('eye_diagnosis', ''),
                case.get('diagnosis', ''), case.get('diagnosis', ''),
                case.get('acupuncture_rx', ''),
                case.get('herbal_rx', ''),
                case.get('notes', ''),
                matched_db['id']
            ))
            updated += 1
        else:
            no_match_cases += 1
            if no_match_cases <= 10:
                print(f'  未匹配: {filepath.name}')
    
    # 统计未使用的数据库记录
    unused = sum(1 for dbs in db_cases.values() for db in dbs if not db['_used'])
    
    return updated, matched_files, no_match_cases, unused

def main():
    print("hantang 医案补全脚本 (最终版)")
    print("=" * 50)
    print(f"源目录: {SOURCE_DIR}")
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 统计当前状态
    print("当前状态:")
    for field in ['inquiry', 'pulse_diagnosis', 'tongue_diagnosis', 'eye_diagnosis', 'herbal_rx', 'acupuncture_rx']:
        cnt = conn.execute(f'SELECT COUNT(*) FROM clinical_cases WHERE {field} IS NOT NULL AND {field} != ""').fetchone()[0]
        print(f"  {field}: {cnt} 条有数据")
    
    print()
    print("开始解析和更新...")
    updated, matched_files, no_match_cases, unused_db = match_and_update(conn)
    
    conn.commit()
    
    # 统计更新后状态
    print()
    print("更新后状态:")
    for field in ['inquiry', 'pulse_diagnosis', 'tongue_diagnosis', 'eye_diagnosis', 'herbal_rx', 'acupuncture_rx']:
        cnt = conn.execute(f'SELECT COUNT(*) FROM clinical_cases WHERE {field} IS NOT NULL AND {field} != ""').fetchone()[0]
        print(f"  {field}: {cnt} 条有数据")
    
    print()
    print(f"结果:")
    print(f"  更新记录: {updated} 条")
    print(f"  匹配文件: {matched_files} 个")
    print(f"  未匹配源案例: {no_match_cases} 个")
    print(f"  未使用的数据库记录: {unused_db} 条")
    
    conn.close()

if __name__ == '__main__':
    main()
