#!/usr/bin/env python3
"""
从 nihaixia-kb 源文件重新解析医案，补全数据库中的结构化字段。
最终版：支持两种格式 + 更强的匹配逻辑。
用法: python3 enrich_clinical_cases.py
"""

import sqlite3, re, os, json
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"
SOURCE_DIR = Path(__file__).parent.parent / "new-repos" / "nihaixia-kb" / "raw" / "医案"

def clean_html(text):
    """清理 HTML 标签和 Markdown 标记"""
    text = re.sub(r'<p>', '', text)
    text = re.sub(r'</p>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\*\*', '', text)
    text = text.strip()
    return text

def normalize_name(name):
    """标准化姓名，用于匹配"""
    # 转小写
    name = name.lower()
    # 去除标点符号
    name = re.sub(r'[,.\-\']', ' ', name)
    # 去除多余空格
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def parse_table_format(text):
    """解析表格+HTML格式的医案"""
    cases = []
    
    # 按行分割
    lines = text.strip().split('\n')
    
    current_case = {}
    expect_data_row = False  # 标记下一行是数据行
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 跳过分隔线
        if re.match(r'^\|[-:]+\|$', line):
            continue
        
        # 移除首尾的 |
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]
        
        # 检测初诊日期
        if '初诊日期' in line and '倪医师病案纪录' in line:
            # 保存上一个案例
            if current_case.get('chief_complaint') or current_case.get('diagnosis'):
                cases.append(current_case)
            current_case = {}
            # 提取日期
            date_match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})', line)
            if date_match:
                current_case['case_date'] = date_match.group(1).replace('/', '-')
            continue
        
        # 检测表头行（姓名、性别等）
        if '姓名' in line and '性别' in line:
            expect_data_row = True
            continue
        
        # 数据行（姓名、性别、年龄、日期）
        if expect_data_row:
            expect_data_row = False
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 4:
                current_case['name'] = clean_html(parts[0])
                gender = clean_html(parts[1])
                current_case['gender'] = gender if gender in ['男', '女'] else ''
                current_case['age'] = clean_html(parts[2])
                # 日期已经在初诊日期行提取了
            continue
        
        # 检测各个字段
        if '来诊原因' in line:
            content = clean_html(re.sub(r'.*来诊原因[：:]?\s*', '', line))
            current_case['chief_complaint'] = content
            continue
        
        if '问诊' in line:
            content = clean_html(re.sub(r'.*问诊[：:]?\s*', '', line))
            current_case['inquiry'] = content
            continue
        
        if '脉诊' in line:
            content = clean_html(re.sub(r'.*脉诊[：:]?\s*', '', line))
            current_case['pulse_diagnosis'] = content
            continue
        
        if '望诊' in line or '舌诊' in line:
            content = clean_html(re.sub(r'.*(?:望诊|舌诊)[：:]?\s*', '', line))
            if '舌诊' in line:
                current_case['tongue_diagnosis'] = content
            continue
        
        if '眼诊' in line:
            content = clean_html(re.sub(r'.*眼诊[：:]?\s*', '', line))
            current_case['eye_diagnosis'] = content
            continue
        
        if '诊断' in line and '特殊' not in line:
            content = clean_html(re.sub(r'.*诊断[：:]?\s*', '', line))
            current_case['diagnosis'] = content
            continue
        
        if '针灸处方' in line:
            content = clean_html(re.sub(r'.*针灸处方[：:]?\s*', '', line))
            current_case['acupuncture_rx'] = content
            continue
        
        if '中药处方' in line:
            content = clean_html(re.sub(r'.*中药处方[：:]?\s*', '', line))
            current_case['herbal_rx'] = content
            continue
        
        if '解说' in line and '备注' not in line:
            content = clean_html(re.sub(r'.*解说[：:]?\s*', '', line))
            current_case['notes'] = content
            continue
        
        if '备注' in line:
            continue
    
    # 保存最后一个案例
    if current_case.get('chief_complaint') or current_case.get('diagnosis'):
        cases.append(current_case)
    
    return cases

def parse_standard_format(text):
    """解析标准 Markdown 格式的医案"""
    cases = []
    
    # 按"初诊日期"分割多个就诊记录
    visits = re.split(r'(?=初诊日期[：:])', text)
    
    for visit in visits:
        if len(visit.strip()) < 50:
            continue
        
        case = {}
        
        # 按行处理
        lines = visit.strip().split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 检测表头行（姓名、性别、年龄、日期）
            if '姓名' in line and '性别' in line and '年龄' in line:
                # 下一行是数据
                if i + 1 < len(lines):
                    data_line = lines[i + 1].strip()
                    parts = [p.strip() for p in data_line.split('\t') if p.strip()]
                    if len(parts) >= 4:
                        case['name'] = parts[0]
                        case['gender'] = parts[1] if parts[1] in ['男', '女'] else ''
                        case['age'] = parts[2]
                        # 解析日期
                        date_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', parts[3])
                        if date_match:
                            case['case_date'] = date_match.group(1).replace('/', '-')
                i += 2
                continue
            
            # 检测各个字段
            if line.startswith('来诊原因'):
                content = re.sub(r'^来诊原因[：:]?\s*', '', line)
                case['chief_complaint'] = content
                i += 1
                continue
            
            if line.startswith('问诊'):
                content = re.sub(r'^问诊[：:]?\s*', '', line)
                case['inquiry'] = content
                i += 1
                continue
            
            if line.startswith('脉诊'):
                content = re.sub(r'^脉诊[：:]?\s*', '', line)
                case['pulse_diagnosis'] = content
                i += 1
                continue
            
            if line.startswith('舌诊'):
                content = re.sub(r'^舌诊[：:]?\s*', '', line)
                case['tongue_diagnosis'] = content
                i += 1
                continue
            
            if line.startswith('眼诊'):
                content = re.sub(r'^眼诊[：:]?\s*', '', line)
                case['eye_diagnosis'] = content
                i += 1
                continue
            
            if line.startswith('诊断'):
                content = re.sub(r'^诊断[：:]?\s*', '', line)
                case['diagnosis'] = content
                i += 1
                continue
            
            if line.startswith('针灸处方'):
                content = re.sub(r'^针灸处方[：:]?\s*', '', line)
                case['acupuncture_rx'] = content
                i += 1
                continue
            
            if line.startswith('中药处方'):
                content = re.sub(r'^中药处方[：:]?\s*', '', line)
                case['herbal_rx'] = content
                i += 1
                continue
            
            if line.startswith('解说'):
                content = re.sub(r'^解说[：:]?\s*', '', line)
                case['notes'] = content
                i += 1
                continue
            
            if line.startswith('备注'):
                i += 1
                continue
            
            # 其他行，可能是多行内容的延续
            # 检查是否是来诊原因的延续
            if 'chief_complaint' in case and not any(line.startswith(k) for k in ['问诊', '脉诊', '望诊', '舌诊', '眼诊', '诊断', '针灸', '中药', '解说', '备注']):
                # 可能是来诊原因的延续
                if not line.startswith('初诊日期'):
                    case['chief_complaint'] += ' ' + line
            
            i += 1
        
        if case.get('chief_complaint') or case.get('diagnosis') or case.get('herbal_rx'):
            cases.append(case)
    
    return cases

def parse_case_file(filepath):
    """解析医案文件，自动检测格式"""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # 检测格式
    if '|**倪医师病案纪录**' in text or '|**来诊原因**|' in text:
        return parse_table_format(text)
    else:
        return parse_standard_format(text)

def normalize_patient_id(pid):
    """从 patient_id 中提取姓名部分（去掉日期）"""
    # 格式: "姓名 YYYYMMDD" 或 "姓名"
    m = re.match(r'^(.+?)\s+\d{8}$', pid)
    if m:
        return m.group(1).strip()
    return pid.strip()

def match_and_update(conn):
    """匹配源文件和数据库记录，更新数据库"""
    # 获取所有 nihaixia-kb 来源的医案
    rows = conn.execute('''
        SELECT id, patient_id, case_date, chief_complaint
        FROM clinical_cases 
        WHERE source_repo = "nihaixia-kb"
        ORDER BY id
    ''').fetchall()
    
    # 按标准化的姓名分组
    db_cases = {}
    for r in rows:
        pid = r[1]
        norm_name = normalize_patient_id(pid)
        norm_key = normalize_name(norm_name)
        if norm_key not in db_cases:
            db_cases[norm_key] = []
        db_cases[norm_key].append({
            'id': r[0], 
            'original_pid': pid,
            'norm_name': norm_name,
            'case_date': r[2], 
            'complaint': r[3],
            '_used': False
        })
    
    updated = 0
    matched_files = 0
    no_match_cases = 0
    
    # 遍历所有源文件（包括子目录）
    for filepath in SOURCE_DIR.rglob('*.md'):
        # 跳过非医案文件
        if 'README' in filepath.name or 'INDEX' in filepath.name:
            continue
        
        cases = parse_case_file(filepath)
        if not cases:
            continue
        
        matched_files += 1
        file_stem = filepath.stem
        file_stem_norm = normalize_name(file_stem)
        
        for case in cases:
            matched_db = None
            
            # 方式1: 精确匹配（标准化后）
            if file_stem_norm in db_cases:
                # 按日期匹配
                if case.get('case_date'):
                    for db in db_cases[file_stem_norm]:
                        if db['case_date'] and case['case_date'] == db['case_date']:
                            matched_db = db
                            break
                
                # 日期匹配失败，取第一个未使用的
                if not matched_db:
                    for db in db_cases[file_stem_norm]:
                        if not db['_used']:
                            matched_db = db
                            break
            
            # 方式2: 部分匹配（文件名包含在 patient_id 中，或反之）
            if not matched_db:
                for norm_key, dbs in db_cases.items():
                    # 检查是否匹配
                    if (file_stem_norm in norm_key or norm_key in file_stem_norm or
                        file_stem_norm.startswith(norm_key) or norm_key.startswith(file_stem_norm)):
                        for db in dbs:
                            if not db['_used']:
                                matched_db = db
                                break
                        if matched_db:
                            break
            
            # 方式3: 按案例中的姓名匹配
            if not matched_db and case.get('name'):
                case_name_norm = normalize_name(case['name'])
                for norm_key, dbs in db_cases.items():
                    if (case_name_norm in norm_key or norm_key in case_name_norm or
                        case_name_norm.startswith(norm_key) or norm_key.startswith(case_name_norm)):
                        for db in dbs:
                            if not db['_used']:
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
                    print(f'  未匹配: {filepath.name} | 姓名={case.get("name", "")} | 日期={case.get("case_date", "")}')
    
    # 统计未使用的数据库记录
    unused = sum(1 for dbs in db_cases.values() for db in dbs if not db['_used'])
    
    return updated, matched_files, no_match_cases, unused

def main():
    print("医案数据补全脚本 (最终版)")
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
