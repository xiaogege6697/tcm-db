#!/usr/bin/env python3
"""
倪海厦中医知识数据库 - 查询示例
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path.home() / "tcm-project" / "tcm-db" / "tcm_knowledge.db"

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# 中文全文搜索（LIKE 替代 FTS5）
# ============================================================
def search_all(keyword, limit=10):
    """跨表全文搜索"""
    conn = get_db()
    kw = f"%{keyword}%"
    
    results = []
    
    # 搜索中药
    rows = conn.execute("""
        SELECT '中药' as type, name as title, 
               COALESCE(nature,'')||COALESCE(flavor,'') as info,
               indication as detail
        FROM herbs 
        WHERE name LIKE ? OR alias LIKE ? OR indication LIKE ? 
              OR commentary LIKE ? OR bencao_raw LIKE ?
        LIMIT ?
    """, (kw, kw, kw, kw, kw, limit)).fetchall()
    results.extend(rows)
    
    # 搜索方剂
    rows = conn.execute("""
        SELECT '方剂' as type, name as title,
               six_channel||' '||source_book as info,
               COALESCE(syndrome,'')||' '||COALESCE(indication,'') as detail
        FROM formulas
        WHERE name LIKE ? OR syndrome LIKE ? OR indication LIKE ?
              OR composition LIKE ? OR commentary LIKE ?
        LIMIT ?
    """, (kw, kw, kw, kw, kw, limit)).fetchall()
    results.extend(rows)
    
    # 搜索医案
    rows = conn.execute("""
        SELECT '医案' as type, chief_complaint as title,
               COALESCE(diagnosis,'') as info,
               COALESCE(herbal_rx,'') as detail
        FROM clinical_cases
        WHERE chief_complaint LIKE ? OR diagnosis LIKE ? 
              OR herbal_rx LIKE ? OR inquiry LIKE ?
        LIMIT ?
    """, (kw, kw, kw, kw, limit)).fetchall()
    results.extend(rows)
    
    # 搜索妙方
    rows = conn.execute("""
        SELECT '妙方' as type, name as title,
               COALESCE(disease,'') as info,
               commentary as detail
        FROM folk_formulas
        WHERE name LIKE ? OR disease LIKE ? OR commentary LIKE ?
        LIMIT ?
    """, (kw, kw, kw, limit)).fetchall()
    results.extend(rows)
    
    conn.close()
    return results

def print_results(results, keyword):
    print(f"\n🔍 全库搜索: '{keyword}'  →  {len(results)} 条结果")
    for r in results:
        icon = {'中药':'🌿','方剂':'💊','医案':'📋','妙方':'🧪'}.get(r['type'],'📄')
        print(f"  {icon} [{r['type']}] {r['title']}")
        if r['info']:
            print(f"     {r['info'][:60]}")

# ============================================================
# 按六经查方剂
# ============================================================
def formulas_by_channel(channel):
    conn = get_db()
    rows = conn.execute("""
        SELECT name, syndrome, differentiation, is_high_risk, contraindication
        FROM formulas WHERE six_channel = ?
        ORDER BY source_book, name
    """, (channel,)).fetchall()
    
    print(f"\n📋 {channel}病方剂  →  {len(rows)} 个")
    for r in rows:
        risk = " ⚠️" if r['is_high_risk'] else ""
        print(f"  💊 {r['name']}{risk}")
        if r['syndrome']:
            print(f"     {r['syndrome'][:70]}")
    conn.close()

# ============================================================
# 症状 → 辨证
# ============================================================
def diagnose(symptom_text):
    conn = get_db()
    kw = f"%{symptom_text}%"
    
    print(f"\n🩺 症状辨证: '{symptom_text}'")
    
    # 匹配症状表
    symptoms = conn.execute("""
        SELECT name, first_gateway, target_module, required_questions
        FROM symptoms WHERE name LIKE ? OR first_gateway LIKE ?
    """, (kw, kw)).fetchall()
    
    if symptoms:
        for s in symptoms:
            print(f"  📍 症状: {s['name']}")
            print(f"     分水岭: {s['first_gateway']}")
            print(f"     模块: {s['target_module']}")
            if s['required_questions']:
                print(f"     追问: {s['required_questions'][:100]}")
    
    # 匹配方剂
    formulas = conn.execute("""
        SELECT name, source_book, six_channel, syndrome
        FROM formulas
        WHERE syndrome LIKE ? OR indication LIKE ? OR differentiation LIKE ?
        LIMIT 10
    """, (kw, kw, kw)).fetchall()
    
    if formulas:
        print(f"  💊 可能方剂:")
        for f in formulas:
            ch = f['six_channel'] or ''
            print(f"    {f['name']} [{f['source_book']}] {ch}")
    
    conn.close()

# ============================================================
# 搜索医案
# ============================================================
def search_cases(keyword, limit=10):
    conn = get_db()
    kw = f"%{keyword}%"
    rows = conn.execute("""
        SELECT chief_complaint, diagnosis, herbal_rx, acupuncture_rx, disease_tags
        FROM clinical_cases
        WHERE chief_complaint LIKE ? OR diagnosis LIKE ? 
              OR herbal_rx LIKE ? OR inquiry LIKE ?
        LIMIT ?
    """, (kw, kw, kw, kw, limit)).fetchall()
    
    print(f"\n📖 医案搜索: '{keyword}'  →  {len(rows)} 条")
    for r in rows:
        tags = json.loads(r['disease_tags']) if r['disease_tags'] else []
        print(f"  📋 {r['chief_complaint'][:50]}  标签:{tags}")
        if r['diagnosis']:
            print(f"     诊断: {r['diagnosis'][:60]}")
        if r['herbal_rx']:
            print(f"     处方: {r['herbal_rx'][:80]}")
    conn.close()

# ============================================================
# 按药性查中药
# ============================================================
def herbs_by_nature(nature=None, category=None):
    conn = get_db()
    conditions = []
    params = []
    if nature:
        conditions.append("nature = ?")
        params.append(nature)
    if category:
        conditions.append("category = ?")
        params.append(category)
    
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = conn.execute(f"""
        SELECT name, category, nature, flavor, indication
        FROM herbs {where} ORDER BY category, name
    """, params).fetchall()
    
    label = f"性味:{nature}" if nature else ""
    if category:
        label += f" 分类:{category}"
    print(f"\n🌿 中药筛选 {label}  →  {len(rows)} 味")
    for r in rows:
        ind = (r['indication'] or '')[:50]
        print(f"  {r['name']:8s} [{r['category']}] {r['nature']}{r['flavor']}  {ind}")
    conn.close()

# ============================================================
# 医案统计
# ============================================================
def case_stats():
    conn = get_db()
    
    total = conn.execute("SELECT COUNT(*) FROM clinical_cases").fetchone()[0]
    print(f"\n📊 医案总数: {total}")
    
    # 按年份
    rows = conn.execute("""
        SELECT SUBSTR(case_date,1,4) as year, COUNT(*) as cnt
        FROM clinical_cases WHERE case_date != ''
        GROUP BY year ORDER BY year
    """).fetchall()
    if rows:
        print("  按年份:")
        for r in rows:
            print(f"    {r['year']}: {'█'*min(r['cnt'],30)} {r['cnt']}")
    
    # 按性别
    rows = conn.execute("""
        SELECT gender, COUNT(*) as cnt
        FROM clinical_cases WHERE gender != ''
        GROUP BY gender
    """).fetchall()
    if rows:
        print("  按性别:")
        for r in rows:
            print(f"    {r['gender']}: {r['cnt']}")
    
    conn.close()

# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("🏥 倪海厦中医知识数据库 - 查询示例")
    print("=" * 60)
    
    # 1. 全库搜索
    results = search_all("柴胡")
    print_results(results, "柴胡")
    
    # 2. 按六经查方
    formulas_by_channel("太阳")
    
    # 3. 症状辨证
    diagnose("发热恶寒")
    
    # 4. 医案搜索
    search_cases("失眠")
    
    # 5. 按药性查药
    herbs_by_nature(nature="寒")
    
    # 6. 医案统计
    case_stats()
