#!/usr/bin/env python3
"""
从源文件补全 courses 表的缺失字段。
用法: python3 enrich_courses.py
"""

import sqlite3, os
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"
BASE_DIR = Path(__file__).parent.parent / "hantang-nihaixia-follower" / "倪海厦"

# 课程目录映射
COURSE_DIRS = {
    '针灸大成': '人纪-1-针灸',
    '黄帝内经': '人纪-2-黄帝内经',
    '神农本草经': '人纪-3-神农本草经',
    '伤寒论': '人纪-4-伤寒论',
    '金匮要略': '人纪-5-金匮要略',
    '人纪班闭门课': '人纪-6-人纪班闭门课',
    '天纪': '天纪',
}

# 课程描述
COURSE_DESCRIPTIONS = {
    '针灸大成': '倪海厦老师讲解针灸学，包括经络穴位、针刺手法、临床应用等。基于《针灸大成》等经典著作，结合多年临床经验，系统讲解针灸治疗各种疾病的方法。',
    '黄帝内经': '倪海厦老师讲解《黄帝内经》，包括素问和灵枢两部分。系统讲解中医基础理论、脏腑经络、病因病机、诊断治疗等内容。',
    '神农本草经': '倪海厦老师讲解《神农本草经》，系统介绍365种中药的性味归经、功效主治、用法用量等。结合临床经验，讲解中药的配伍禁忌和应用技巧。',
    '伤寒论': '倪海厦老师讲解《伤寒论》，系统介绍张仲景的六经辨证体系。包括太阳病、阳明病、少阳病、太阴病、少阴病、厥阴病的辨证论治。',
    '金匮要略': '倪海厦老师讲解《金匮要略》，系统介绍杂病的辨证论治。包括内科、外科、妇科等各种疾病的治疗方法。',
    '人纪班闭门课': '倪海厦老师给人纪班学生讲授的闭门课程，包括临床案例分析、方剂应用、针灸技巧等深入内容。',
    '天纪': '倪海厦老师讲解天纪，包括易经、紫微斗数、堪舆、命理等内容。属于倪海厦老师的高级课程。',
}

# 关键主题
COURSE_TOPICS = {
    '针灸大成': '经络,穴位,针刺手法,艾灸,临床应用,十四经脉,奇经八脉',
    '黄帝内经': '阴阳五行,脏腑经络,病因病机,诊法治则,养生保健',
    '神农本草经': '中药性味,归经,功效,配伍禁忌,上经中经下经',
    '伤寒论': '六经辨证,太阳病,阳明病,少阳病,太阴病,少阴病,厥阴病,方剂',
    '金匮要略': '杂病,内科,外科,妇科,方剂,辨证论治',
    '人纪班闭门课': '临床案例,方剂应用,针灸技巧,辨证思路',
    '天纪': '易经,紫微斗数,堪舆,命理,天机道',
}

def count_lessons(course_dir):
    """统计课程目录中的课时数"""
    if not course_dir.exists():
        return 0
    
    # 统计 md 文件数量
    md_files = list(course_dir.glob('*.md'))
    return len(md_files)

def estimate_hours(lesson_count):
    """估算课程总时长（假设每课时1-2小时）"""
    if not lesson_count:
        return None
    # 假设每课时平均1.5小时
    return round(lesson_count * 1.5, 1)

def main():
    print("补全 courses 表")
    print("=" * 50)
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 获取所有课程
    rows = conn.execute('''
        SELECT id, name, order_num, total_hours, lesson_count, description, key_topics
        FROM courses 
        ORDER BY order_num
    ''').fetchall()
    
    updated = 0
    
    for course_id, name, order_num, total_hours, lesson_count, description, key_topics in rows:
        print(f"课程: {name}")
        
        # 获取课程目录
        dir_name = COURSE_DIRS.get(name)
        if dir_name:
            course_dir = BASE_DIR / dir_name
            
            # 统计课时数（如果缺失）
            if not lesson_count:
                lesson_count = count_lessons(course_dir)
                if lesson_count:
                    print(f"  课时数: {lesson_count}")
            
            # 估算总时长（如果缺失）
            if not total_hours:
                total_hours = estimate_hours(lesson_count)
                if total_hours:
                    print(f"  总时长: {total_hours} 小时")
        
        # 获取描述（如果缺失）
        if not description:
            description = COURSE_DESCRIPTIONS.get(name, '')
            if description:
                print(f"  描述: {description[:50]}...")
        
        # 获取关键主题（如果缺失）
        if not key_topics:
            key_topics = COURSE_TOPICS.get(name, '')
            if key_topics:
                print(f"  主题: {key_topics}")
        
        # 更新数据库
        conn.execute('''
            UPDATE courses 
            SET total_hours = COALESCE(?, total_hours),
                lesson_count = COALESCE(?, lesson_count),
                description = COALESCE(?, description),
                key_topics = COALESCE(?, key_topics)
            WHERE id = ?
        ''', (total_hours, lesson_count, description, key_topics, course_id))
        
        updated += 1
    
    conn.commit()
    
    # 统计结果
    print()
    print(f"更新完成: {updated} 门课程")
    
    # 检查最终状态
    rows = conn.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN total_hours IS NOT NULL THEN 1 ELSE 0 END) as has_hours,
            SUM(CASE WHEN lesson_count IS NOT NULL THEN 1 ELSE 0 END) as has_lessons,
            SUM(CASE WHEN description IS NOT NULL AND description != "" THEN 1 ELSE 0 END) as has_desc,
            SUM(CASE WHEN key_topics IS NOT NULL AND key_topics != "" THEN 1 ELSE 0 END) as has_topics
        FROM courses
    ''').fetchone()
    
    print()
    print("最终状态:")
    print(f"  总数: {rows[0]}")
    print(f"  有总时长: {rows[1]}")
    print(f"  有课时数: {rows[2]}")
    print(f"  有描述: {rows[3]}")
    print(f"  有主题: {rows[4]}")
    
    conn.close()

if __name__ == '__main__':
    main()
