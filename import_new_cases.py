#!/usr/bin/env python3
"""
从 nihaixia-kb 源文件导入新的医案记录到数据库。
用法: python3 import_new_cases.py
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

def get_existing_patient_ids(conn):
    """获取数据库中已有的 patient_id（标准化后）"""
    rows = conn.execute('''
        SELECT DISTINCT patient_id FROM clinical_cases WHERE source_repo = "nihaixia-kb"
    ''').fetchall()
    
    existing = set()
    for r in rows:
        pid = r[0]
        norm = normalize_patient_id(pid)
        existing.add(norm.lower())
    
    return existing

def import_new_cases(conn):
    """导入新的医案记录"""
    # 获取已有的 patient_id
    existing_pids = get_existing_patient_ids(conn)
    
    imported = 0
    skipped = 0
    errors = 0
    
    # 遍历所有源文件（包括子目录）
    for filepath in SOURCE_DIR.rglob('*.md'):
        # 跳过非医案文件
        if 'README' in filepath.name or 'INDEX' in filepath.name:
            continue
        
        file_stem = filepath.stem
        
        # 检查是否已存在
        if file_stem.lower() in existing_pids:
            skipped += 1
            continue
        
        # 解析文件
        try:
            cases = parse_case_file(filepath)
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f'  解析错误: {filepath.name}: {e}')
            continue
        
        if not cases:
            skipped += 1
            continue
        
        # 导入每个案例
        for case in cases:
            # 构建 patient_id
            if case.get('name'):
                patient_id = case['name']
            else:
                patient_id = file_stem
            
            # 如果有日期，添加到 patient_id
            if case.get('case_date'):
                date_str = case['case_date'].replace('-', '')
                patient_id = f"{patient_id} {date_str}"
            
            # 插入数据库
            try:
                conn.execute('''
                    INSERT INTO clinical_cases (
                        patient_id, case_date, gender, age,
                        chief_complaint, inquiry, pulse_diagnosis,
                        tongue_diagnosis, eye_diagnosis, diagnosis,
                        acupuncture_rx, herbal_rx, notes,
                        disease_tags, source_repo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    patient_id,
                    case.get('case_date', ''),
                    case.get('gender', ''),
                    case.get('age', ''),
                    case.get('chief_complaint', ''),
                    case.get('inquiry', ''),
                    case.get('pulse_diagnosis', ''),
                    case.get('tongue_diagnosis', ''),
                    case.get('eye_diagnosis', ''),
                    case.get('diagnosis', ''),
                    case.get('acupuncture_rx', ''),
                    case.get('herbal_rx', ''),
                    case.get('notes', ''),
                    json.dumps([file_stem], ensure_ascii=False),
                    'nihaixia-kb'
                ))
                imported += 1
            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f'  插入错误: {filepath.name}: {e}')
    
    return imported, skipped, errors

def main():
    print("医案数据导入脚本")
    print("=" * 50)
    print(f"源目录: {SOURCE_DIR}")
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 统计当前状态
    total = conn.execute('SELECT COUNT(*) FROM clinical_cases').fetchone()[0]
    nihaixia_kb = conn.execute('SELECT COUNT(*) FROM clinical_cases WHERE source_repo = "nihaixia-kb"').fetchone()[0]
    print(f"当前状态:")
    print(f"  医案总数: {total}")
    print(f"  nihaixia-kb 来源: {nihaixia_kb}")
    
    print()
    print("开始导入...")
    imported, skipped, errors = import_new_cases(conn)
    
    conn.commit()
    
    # 统计导入后状态
    total_after = conn.execute('SELECT COUNT(*) FROM clinical_cases').fetchone()[0]
    nihaixia_kb_after = conn.execute('SELECT COUNT(*) FROM clinical_cases WHERE source_repo = "nihaixia-kb"').fetchone()[0]
    
    print()
    print(f"导入后状态:")
    print(f"  医案总数: {total_after} (+{total_after - total})")
    print(f"  nihaixia-kb 来源: {nihaixia_kb_after} (+{nihaixia_kb_after - nihaixia_kb})")
    
    print()
    print(f"结果:")
    print(f"  新增记录: {imported} 条")
    print(f"  跳过（已存在）: {skipped} 个")
    print(f"  错误: {errors} 个")
    
    conn.close()

if __name__ == '__main__':
    main()
