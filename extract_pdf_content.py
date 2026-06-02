#!/usr/bin/env python3
"""
从 PDF 文件中提取内容到 books 表。
用法: python3 extract_pdf_content.py
"""

import sqlite3, os
from pathlib import Path

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"
BASE_DIR = Path(__file__).parent.parent

def extract_pdf_text(pdf_path):
    """从 PDF 文件中提取文本"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except Exception as e:
        print(f"  错误: {e}")
        return ""

def main():
    print("提取 PDF 内容到 books 表")
    print("=" * 50)
    print(f"数据库: {DB_PATH}")
    print()
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 获取没有内容的 PDF 书籍
    rows = conn.execute('''
        SELECT id, title, raw_path
        FROM books 
        WHERE format = "pdf" AND (content IS NULL OR content = "")
    ''').fetchall()
    
    print(f"需要提取内容的 PDF: {len(rows)} 本")
    print()
    
    extracted = 0
    errors = 0
    
    for book_id, title, raw_path in rows:
        pdf_path = BASE_DIR / raw_path
        
        if not pdf_path.exists():
            print(f"❌ 文件不存在: {title}")
            errors += 1
            continue
        
        print(f"📄 提取: {title}")
        
        # 提取文本
        text = extract_pdf_text(pdf_path)
        
        if text:
            # 更新数据库
            word_count = len(text)
            conn.execute('''
                UPDATE books 
                SET content = ?, word_count = ?
                WHERE id = ?
            ''', (text, word_count, book_id))
            
            print(f"  ✅ 成功: {word_count} 字符")
            extracted += 1
        else:
            print(f"  ❌ 提取失败")
            errors += 1
    
    conn.commit()
    
    # 统计结果
    print()
    print(f"结果:")
    print(f"  成功提取: {extracted} 本")
    print(f"  失败: {errors} 本")
    
    # 检查最终状态
    rows = conn.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN content IS NOT NULL AND content != "" THEN 1 ELSE 0 END) as has_content
        FROM books WHERE format = "pdf"
    ''').fetchone()
    print(f"  PDF 总数: {rows[0]}, 有内容: {rows[1]}")
    
    conn.close()

if __name__ == '__main__':
    main()
