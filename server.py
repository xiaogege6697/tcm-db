#!/usr/bin/env python3
"""
倪海厦中医知识数据库 - Web 查询界面
零依赖，仅用 Python 标准库
用法: python3 server.py [端口]
"""

import sqlite3, json, os, sys, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import mimetypes

DB_PATH = Path(__file__).parent / "tcm_knowledge.db"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def dict_row(row):
    return dict(row) if row else None

def dict_rows(rows):
    return [dict(r) for r in rows]

# ============================================================
# API 路由
# ============================================================
def api_search(keyword, limit=20):
    """全库搜索"""
    kw = f"%{keyword}%"
    conn = get_db()
    results = []
    
    # 中药
    for r in conn.execute("""SELECT '中药' as type, name, category, nature, flavor, 
        indication, commentary, id FROM herbs 
        WHERE name LIKE ? OR alias LIKE ? OR indication LIKE ? OR commentary LIKE ? OR bencao_raw LIKE ?
        LIMIT ?""", (kw,kw,kw,kw,kw,limit)).fetchall():
        d = dict(r)
        d['commentary'] = (d.get('commentary') or '')[:200]
        results.append(d)
    
    # 方剂
    for r in conn.execute("""SELECT '方剂' as type, name, source_book, six_channel, 
        syndrome, indication, composition, differentiation, is_high_risk, id FROM formulas
        WHERE name LIKE ? OR syndrome LIKE ? OR indication LIKE ? OR composition LIKE ? OR commentary LIKE ?
        LIMIT ?""", (kw,kw,kw,kw,kw,limit)).fetchall():
        results.append(dict(r))
    
    # 症状
    for r in conn.execute("""SELECT '症状' as type, name, category, description, 
        first_gateway, target_module, id FROM symptoms
        WHERE name LIKE ? OR description LIKE ? OR first_gateway LIKE ?
        LIMIT ?""", (kw,kw,kw,limit)).fetchall():
        results.append(dict(r))
    
    # 医案
    for r in conn.execute("""SELECT '医案' as type, patient_id, case_date, diagnosis, 
        herbal_rx, disease_tags, id FROM clinical_cases
        WHERE chief_complaint LIKE ? OR diagnosis LIKE ? OR herbal_rx LIKE ? OR inquiry LIKE ?
        LIMIT ?""", (kw,kw,kw,kw,limit)).fetchall():
        results.append(dict(r))
    
    # 穴位
    for r in conn.execute("""SELECT '穴位' as type, name, meridian, indication, 
        technique, id FROM acupoints
        WHERE name LIKE ? OR meridian LIKE ? OR indication LIKE ?
        LIMIT ?""", (kw,kw,kw,limit)).fetchall():
        results.append(dict(r))
    
    # 病机
    for r in conn.execute("""SELECT '病机' as type, name, core_symptoms, 
        description, id FROM syndromes
        WHERE name LIKE ? OR description LIKE ? OR core_symptoms LIKE ?
        LIMIT ?""", (kw,kw,kw,limit)).fetchall():
        results.append(dict(r))
    
    # 治法
    for r in conn.execute("""SELECT '治法' as type, name, description, 
        related_herbs, id FROM treatment_methods
        WHERE name LIKE ? OR description LIKE ? OR related_herbs LIKE ?
        LIMIT ?""", (kw,kw,kw,limit)).fetchall():
        results.append(dict(r))
    
    # 经典
    for r in conn.execute("""SELECT '经典' as type, book_name, chapter_name, 
        content, id FROM classics
        WHERE chapter_name LIKE ? OR content LIKE ?
        LIMIT ?""", (kw,kw,limit)).fetchall():
        d = dict(r)
        d['content'] = (d.get('content') or '')[:200]
        results.append(d)
    
    # 讲座
    for r in conn.execute("""SELECT '讲座' as type, title, lecture_type, 
        content, id FROM lectures
        WHERE title LIKE ? OR content LIKE ?
        LIMIT ?""", (kw,kw,limit)).fetchall():
        d = dict(r)
        d['content'] = (d.get('content') or '')[:200]
        results.append(d)
    
    conn.close()
    return results[:limit]

def api_browse(table, page=1, per_page=30, filters=None):
    """分页浏览"""
    conn = get_db()
    offset = (page - 1) * per_page
    
    where = "1=1"
    params = []
    if filters:
        for k, v in filters.items():
            if v:
                where += f" AND {k} LIKE ?"
                params.append(f"%{v}%")
    
    total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM {table} WHERE {where} LIMIT ? OFFSET ?", 
                       params + [per_page, offset]).fetchall()
    conn.close()
    return {"total": total, "page": page, "per_page": per_page, "data": dict_rows(rows)}

def api_detail(table, id):
    """查看详情"""
    conn = get_db()
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (id,)).fetchone()
    d = dict_row(row)
    if not d:
        conn.close()
        return None
    long_fields = ['content','commentary','bencao_raw','herbal_rx','notes','inquiry','indication','description']
    for k in long_fields:
        if k in d and d[k]:
            d[k + '_html'] = render_markdown(d[k])

    # 获取关联数据
    d['_relations'] = {}

    if table == 'formulas':
        # 方剂的药物
        rows = conn.execute('''
            SELECT h.id, h.name, h.nature, h.flavor, fh.role
            FROM formula_herbs fh
            JOIN herbs h ON fh.herb_id = h.id
            WHERE fh.formula_id = ?
        ''', (id,)).fetchall()
        d['_relations']['herbs'] = [{'id': r[0], 'name': r[1], 'nature': r[2], 'flavor': r[3], 'role': r[4]} for r in rows]

        # 方剂的证型
        rows = conn.execute('''
            SELECT s.id, s.name, s.six_channel
            FROM formula_syndromes fs
            JOIN syndromes s ON fs.syndrome_id = s.id
            WHERE fs.formula_id = ?
        ''', (id,)).fetchall()
        d['_relations']['syndromes'] = [{'id': r[0], 'name': r[1], 'six_channel': r[2]} for r in rows]

    elif table == 'syndromes':
        # 证型的方剂
        rows = conn.execute('''
            SELECT f.id, f.name, f.source_book
            FROM formula_syndromes fs
            JOIN formulas f ON fs.formula_id = f.id
            WHERE fs.syndrome_id = ?
        ''', (id,)).fetchall()
        d['_relations']['formulas'] = [{'id': r[0], 'name': r[1], 'source_book': r[2]} for r in rows]

        # 证型的症状
        rows = conn.execute('''
            SELECT s.id, s.name, s.category
            FROM syndrome_symptoms ss
            JOIN symptoms s ON ss.symptom_id = s.id
            WHERE ss.syndrome_id = ?
        ''', (id,)).fetchall()
        d['_relations']['symptoms'] = [{'id': r[0], 'name': r[1], 'category': r[2]} for r in rows]

    elif table == 'clinical_cases':
        # 医案的方剂
        rows = conn.execute('''
            SELECT f.id, f.name, f.source_book
            FROM case_formulas cf
            JOIN formulas f ON cf.formula_id = f.id
            WHERE cf.case_id = ?
        ''', (id,)).fetchall()
        d['_relations']['formulas'] = [{'id': r[0], 'name': r[1], 'source_book': r[2]} for r in rows]

        # 医案的药物
        rows = conn.execute('''
            SELECT h.id, h.name, h.nature, h.flavor
            FROM case_herbs ch
            JOIN herbs h ON ch.herb_id = h.id
            WHERE ch.case_id = ?
        ''', (id,)).fetchall()
        d['_relations']['herbs'] = [{'id': r[0], 'name': r[1], 'nature': r[2], 'flavor': r[3]} for r in rows]

    elif table == 'herbs':
        # 药物的方剂
        rows = conn.execute('''
            SELECT f.id, f.name, f.source_book, fh.role
            FROM formula_herbs fh
            JOIN formulas f ON fh.formula_id = f.id
            WHERE fh.herb_id = ?
        ''', (id,)).fetchall()
        d['_relations']['formulas'] = [{'id': r[0], 'name': r[1], 'source_book': r[2], 'role': r[3]} for r in rows]

        # 药物的医案
        rows = conn.execute('''
            SELECT c.id, c.patient_id, c.chief_complaint
            FROM case_herbs ch
            JOIN clinical_cases c ON ch.case_id = c.id
            WHERE ch.herb_id = ?
            LIMIT 20
        ''', (id,)).fetchall()
        d['_relations']['cases'] = [{'id': r[0], 'patient_id': r[1], 'chief_complaint': r[2]} for r in rows]

    elif table == 'symptoms':
        # 症状的证型
        rows = conn.execute('''
            SELECT s.id, s.name, s.six_channel
            FROM syndrome_symptoms ss
            JOIN syndromes s ON ss.syndrome_id = s.id
            WHERE ss.symptom_id = ?
        ''', (id,)).fetchall()
        d['_relations']['syndromes'] = [{'id': r[0], 'name': r[1], 'six_channel': r[2]} for r in rows]

    elif table == 'courses':
        # 课程的笔记
        rows = conn.execute('''
            SELECT cn.id, cn.title, cn.note_type, cn.module_name
            FROM course_course_notes ccn
            JOIN course_notes cn ON ccn.note_id = cn.id
            WHERE ccn.course_id = ?
            ORDER BY cn.note_type, cn.title
        ''', (id,)).fetchall()
        d['_relations']['course_notes'] = [{'id': r[0], 'title': r[1], 'note_type': r[2], 'module_name': r[3]} for r in rows]

    conn.close()
    return d

def api_stats():
    """统计信息"""
    conn = get_db()
    tables = ['herbs','formulas','symptoms','syndromes','acupoints',
              'clinical_cases','folk_formulas','classics','course_notes',
              'treatment_methods','books','lectures','tianji','courses']
    stats = {}
    for t in tables:
        try:
            stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except:
            stats[t] = 0
    conn.close()
    return stats


def render_markdown(text):
    """Markdown + 截图路径 转 HTML"""
    if not text: return ''
    # 1. 截图路径：assets/screenshots/xxx.webp -> <img>
    def fix_screenshot_path(m):
        path = m.group(1)
        fname = path.split('screenshots/')[-1]
        return f'<img src="/screenshots/{fname}" alt="截图" style="max-width:100%;border-radius:6px;margin:8px 0;box-shadow:0 2px 8px rgba(0,0,0,0.1);" loading="lazy">'
    text = re.sub(r'(?:截图路径[：:]\s*)?assets/screenshots/(\S+\.webp)', 
                  lambda m: f'<img src="/screenshots/{m.group(1)}" alt="截图" style="max-width:100%;border-radius:6px;margin:8px 0;box-shadow:0 2px 8px rgba(0,0,0,0.1);" loading="lazy">', 
                  text)
    # 2. Markdown 图片 ![alt](url)
    def fix_img(m):
        alt, path = m.group(1), m.group(2)
        if 'screenshots/' in path:
            fname = path.split('screenshots/')[-1]
            return f'<img src="/screenshots/{fname}" alt="{alt}" style="max-width:100%;border-radius:6px;margin:8px 0;" loading="lazy">'
        return f'<img src="{path}" alt="{alt}" style="max-width:100%;">'
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', fix_img, text)
    # 3. 粗体
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # 4. 标题
    text = re.sub(r'^### (.+)$', r'<h4 style="margin:12px 0 6px;color:#8b7355;">\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h3 style="margin:16px 0 8px;color:#5b4a3f;">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h2 style="margin:20px 0 10px;">\1</h2>', text, flags=re.MULTILINE)
    # 5. 引用
    text = re.sub(r'^> (.+)$', r'<blockquote style="border-left:3px solid #c9b99a;padding-left:12px;color:#666;margin:8px 0;">\1</blockquote>', text, flags=re.MULTILINE)
    # 6. 换行
    text = text.replace('\n', '<br>')
    return text

def api_filter_options(table, column):
    """获取筛选选项"""
    conn = get_db()
    rows = conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}").fetchall()
    conn.close()
    return [r[0] for r in rows]

def api_export_table(table, format='json'):
    """导出整个表的数据"""
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()

    data = []
    for row in rows:
        d = dict_row(row)
        # 移除内部字段
        d.pop('_relations', None)
        data.append(d)

    if format == 'csv':
        if not data:
            return ''
        # CSV 格式
        import csv
        import io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()
    else:
        # JSON 格式
        return data

def api_export_search(query, format='json'):
    """导出搜索结果"""
    conn = get_db()
    results = []

    # 搜索多个表
    tables_to_search = [
        ('herbs', 'name', 'category'),
        ('formulas', 'name', 'source_book'),
        ('symptoms', 'name', 'category'),
        ('syndromes', 'name', 'six_channel'),
        ('acupoints', 'name', 'meridian'),
        ('clinical_cases', 'patient_id', 'chief_complaint'),
        ('course_notes', 'title', 'content'),
    ]

    for table, name_col, desc_col in tables_to_search:
        try:
            rows = conn.execute(f'''
                SELECT id, {name_col}, {desc_col}
                FROM {table}
                WHERE {name_col} LIKE ? OR {desc_col} LIKE ?
                LIMIT 100
            ''', (f'%{query}%', f'%{query}%')).fetchall()

            for row in rows:
                results.append({
                    'table': table,
                    'id': row[0],
                    'name': row[1],
                    'description': (row[2] or '')[:200]
                })
        except:
            pass

    conn.close()

    if format == 'csv':
        if not results:
            return ''
        import csv
        import io
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['table', 'id', 'name', 'description'])
        writer.writeheader()
        writer.writerows(results)
        return output.getvalue()
    else:
        return results

# ============================================================
# HTML 模板
# ============================================================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>倪海厦中医知识数据库</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background:#f5f0e8; color:#2c2c2c; }
.header { background:linear-gradient(135deg,#5b4a3f 0%,#8b7355 100%); color:#f5f0e8; padding:20px 0; text-align:center; }
.header h1 { font-size:28px; margin-bottom:6px; }
.header p { opacity:0.85; font-size:14px; }
.container { max-width:1200px; margin:0 auto; padding:0 20px; }

/* 搜索栏 */
.search-box { margin:20px auto; max-width:700px; }
.search-box input { width:100%; padding:14px 20px; font-size:16px; border:2px solid #c9b99a; border-radius:8px; background:#fff; }
.search-box input:focus { outline:none; border-color:#8b7355; }

/* 统计卡片 */
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin:20px 0; }
.stat-card { background:#fff; border-radius:8px; padding:14px; text-align:center; cursor:pointer; border:2px solid transparent; transition:all 0.2s; }
.stat-card:hover, .stat-card.active { border-color:#8b7355; transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.1); }
.stat-card .num { font-size:24px; font-weight:bold; color:#8b7355; }
.stat-card .label { font-size:12px; color:#888; margin-top:2px; }

/* 导航标签 */
.tabs { display:flex; gap:6px; margin:15px 0; flex-wrap:wrap; }
.tab { padding:8px 16px; background:#fff; border:1px solid #ddd; border-radius:20px; cursor:pointer; font-size:13px; transition:all 0.2s; }
.tab:hover, .tab.active { background:#8b7355; color:#fff; border-color:#8b7355; }

/* 筛选栏 */
.filters { display:flex; gap:10px; margin:10px 0; flex-wrap:wrap; align-items:center; }
.filters select { padding:8px 12px; border:1px solid #ddd; border-radius:6px; background:#fff; font-size:13px; }
.filters label { font-size:13px; color:#666; }

/* 结果列表 */
.results { margin:15px 0; }
.result-item { background:#fff; border-radius:8px; padding:16px; margin-bottom:10px; border-left:4px solid #8b7355; cursor:pointer; transition:all 0.2s; }
.result-item:hover { box-shadow:0 4px 12px rgba(0,0,0,0.08); transform:translateX(4px); }
.result-item .type-badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:bold; margin-bottom:6px; }
.badge-中药 { background:#e8f5e9; color:#2e7d32; }
.badge-方剂 { background:#e3f2fd; color:#1565c0; }
.badge-症状 { background:#fff3e0; color:#e65100; }
.badge-医案 { background:#fce4ec; color:#c62828; }
.badge-穴位 { background:#f3e5f5; color:#7b1fa2; }
.badge-病机 { background:#e0f2f1; color:#00695c; }
.badge-治法 { background:#fff8e1; color:#f57f17; }
.badge-经典 { background:#efebe9; color:#4e342e; }
.badge-讲座 { background:#e8eaf6; color:#283593; }
.result-item h3 { font-size:15px; margin-bottom:4px; }
.result-item .meta { font-size:12px; color:#888; margin-bottom:4px; }
.result-item .desc { font-size:13px; color:#555; line-height:1.6; }
.risk { color:#c62828; font-weight:bold; }

/* 详情面板 */
.detail-panel { position:fixed; top:0; right:-500px; width:500px; height:100vh; background:#fff; box-shadow:-4px 0 20px rgba(0,0,0,0.15); overflow-y:auto; transition:right 0.3s; z-index:1000; padding:24px; }
.detail-panel.open { right:0; }
.detail-panel .close { position:absolute; top:16px; right:16px; font-size:24px; cursor:pointer; color:#999; }
.detail-panel h2 { font-size:20px; margin-bottom:16px; padding-bottom:12px; border-bottom:2px solid #8b7355; }
.detail-panel .field { margin-bottom:12px; }
.detail-panel .field-label { font-size:12px; color:#888; margin-bottom:2px; }
.detail-panel .field-value { font-size:14px; line-height:1.7; }
.detail-panel .field-value pre { white-space:pre-wrap; font-family:inherit; background:#f9f7f3; padding:12px; border-radius:6px; max-height:300px; overflow-y:auto; }
.detail-panel .tag { display:inline-block; background:#f0ebe3; color:#6b5b4a; padding:3px 10px; border-radius:12px; margin:2px 4px; font-size:13px; cursor:pointer; transition:all 0.2s; border:1px solid #d4c9b8; }
.detail-panel .tag:hover { background:#8b7355; color:#fff; border-color:#8b7355; }
.detail-panel .case-link { padding:6px 10px; margin:4px 0; background:#faf8f5; border-radius:6px; cursor:pointer; font-size:13px; border-left:3px solid #c9b99a; transition:all 0.2s; }
.detail-panel .case-link:hover { background:#f0ebe3; border-left-color:#8b7355; }

/* 分页 */
.pagination { display:flex; justify-content:center; gap:8px; margin:20px 0; }
.pagination button { padding:8px 14px; border:1px solid #ddd; border-radius:6px; background:#fff; cursor:pointer; }
.pagination button:hover { background:#8b7355; color:#fff; border-color:#8b7355; }
.pagination button:disabled { opacity:0.4; cursor:default; }
.pagination button:disabled:hover { background:#fff; color:#333; border-color:#ddd; }
.page-info { padding:8px 14px; font-size:13px; color:#888; }

.overlay { position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.3); z-index:999; display:none; }
.overlay.show { display:block; }

.loading { text-align:center; padding:40px; color:#888; }
</style>
</head>
<body>

<div class="header">
  <div class="container">
    <h1>🏥 倪海厦中医知识数据库</h1>
    <p>基于人纪/天纪课程体系 | 3,867 条记录 | 中药 · 方剂 · 医案 · 经典 · 针灸 · 天纪</p>
  </div>
</div>

<div class="container">
  <div class="search-box">
    <input type="text" id="searchInput" placeholder="搜索中药、方剂、症状、穴位、医案…" autofocus>
  </div>
  
  <div class="stats" id="statsGrid"></div>
  
  <div class="tabs" id="tabs"></div>
  <div class="filters" id="filters"></div>
  <div class="export-buttons" id="exportButtons" style="margin:10px 0; display:none;">
    <span style="color:#888; font-size:13px;">导出：</span>
    <button onclick="exportCurrentTable('json')" style="padding:4px 12px; background:#8b7355; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:12px;">JSON</button>
    <button onclick="exportCurrentTable('csv')" style="padding:4px 12px; background:#6b8e6b; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:12px;">CSV</button>
  </div>
  <div class="results" id="results"></div>
  <div class="pagination" id="pagination"></div>
</div>

<div class="overlay" id="overlay" onclick="closeDetail()"></div>
<div class="detail-panel" id="detailPanel">
  <span class="close" onclick="closeDetail()">&times;</span>
  <div id="detailContent"></div>
</div>

<script>
const TABLE_LABELS = {
  herbs:'中药', formulas:'方剂', symptoms:'症状', syndromes:'证型/病机',
  acupoints:'穴位', clinical_cases:'医案', folk_formulas:'妙方',
  classics:'经典原文', course_notes:'课程笔记', treatment_methods:'治法',
  books:'书籍', lectures:'讲座', tianji:'天纪', courses:'课程'
};

const TABLE_FILTERS = {
  herbs: [{col:'category',label:'分类'},{col:'nature',label:'性味'}],
  formulas: [{col:'source_book',label:'来源'},{col:'six_channel',label:'六经'}],
  symptoms: [{col:'category',label:'分类'}],
  syndromes: [{col:'six_channel',label:'六经'}],
  acupoints: [{col:'meridian',label:'经络'}],
  clinical_cases: [{col:'source_repo',label:'来源'}],
  books: [{col:'category',label:'分类'},{col:'format',label:'格式'}],
  lectures: [{col:'lecture_type',label:'类型'}],
  tianji: [{col:'category',label:'分类'}],
  course_notes: [{col:'module_name',label:'模块'},{col:'note_type',label:'类型'}],
};

let currentTable = '';
let currentPage = 1;
let currentFilters = {};

// API 调用
async function api(endpoint) {
  const res = await fetch('/api/' + endpoint);
  return res.json();
}

// 初始化
async function init() {
  const stats = await api('stats');
  renderStats(stats);
  renderTabs();
}

function renderStats(stats) {
  const grid = document.getElementById('statsGrid');
  const order = ['herbs','formulas','symptoms','syndromes','acupoints',
                 'clinical_cases','classics','course_notes','treatment_methods',
                 'lectures','tianji','books','folk_formulas','courses'];
  grid.innerHTML = order.map(t => `
    <div class="stat-card ${currentTable===t?'active':''}" onclick="selectTable('${t}')">
      <div class="num">${stats[t]||0}</div>
      <div class="label">${TABLE_LABELS[t]||t}</div>
    </div>
  `).join('');
}

function renderTabs() {
  const tabs = document.getElementById('tabs');
  const tables = ['herbs','formulas','symptoms','syndromes','acupoints',
                  'clinical_cases','classics','treatment_methods','lectures','tianji','books'];
  tabs.innerHTML = tables.map(t => 
    `<div class="tab ${currentTable===t?'active':''}" onclick="selectTable('${t}')">${TABLE_LABELS[t]}</div>`
  ).join('');
}

async function selectTable(table) {
  currentTable = table;
  currentPage = 1;
  currentFilters = {};
  document.getElementById('searchInput').value = '';
  renderStats(await api('stats'));
  renderTabs();
  renderFilters(table);
  await loadBrowse();
}

async function renderFilters(table) {
  const container = document.getElementById('filters');
  const filterDefs = TABLE_FILTERS[table] || [];
  if (!filterDefs.length) { container.innerHTML = ''; return; }
  
  let html = '<label>筛选：</label>';
  for (const f of filterDefs) {
    const options = await api(`filter/${table}/${f.col}`);
    html += `<select onchange="applyFilter('${f.col}', this.value)">
      <option value="">全部${f.label}</option>
      ${options.map(o => `<option value="${o}">${o}</option>`).join('')}
    </select>`;
  }
  container.innerHTML = html;
}

function applyFilter(col, val) {
  if (val) currentFilters[col] = val;
  else delete currentFilters[col];
  currentPage = 1;
  loadBrowse();
}

async function loadBrowse() {
  const params = new URLSearchParams({table:currentTable, page:currentPage});
  for (const [k,v] of Object.entries(currentFilters)) params.set(k,v);
  const data = await api('browse?' + params);
  renderResults(data.data, data.total, data.page, data.per_page);

  // 显示导出按钮
  const exportBtn = document.getElementById('exportButtons');
  if (currentTable) {
    exportBtn.style.display = 'block';
  } else {
    exportBtn.style.display = 'none';
  }
}

function exportCurrentTable(format) {
  if (!currentTable) return;
  const url = `/api/export/${currentTable}?format=${format}`;
  window.open(url, '_blank');
}

function exportSearchResults(format) {
  const kw = document.getElementById('searchInput').value.trim();
  if (!kw) return;
  const url = `/api/export/search?q=${encodeURIComponent(kw)}&format=${format}`;
  window.open(url, '_blank');
}

function renderResults(items, total, page, perPage) {
  const container = document.getElementById('results');
  if (!items || !items.length) { container.innerHTML = '<div class="loading">无结果</div>'; return; }
  
  container.innerHTML = items.map(item => {
    const type = TABLE_LABELS[currentTable] || currentTable;
    const title = item.name || item.title || item.patient_id || item.chapter_name || '未知';
    let desc = '';
    
    if (currentTable === 'herbs') desc = `[${item.category||''}] ${item.nature||''}${item.flavor||''} ${(item.indication||'').substring(0,80)}`;
    else if (currentTable === 'formulas') desc = `${item.source_book||''} ${item.six_channel||''} ${(item.syndrome||'').substring(0,80)}`;
    else if (currentTable === 'symptoms') desc = `${item.category||''} 分水岭:${item.first_gateway||''} ${(item.description||'').substring(0,60)}`;
    else if (currentTable === 'syndromes') desc = `${item.six_channel||''} ${(item.description||'').substring(0,80)}`;
    else if (currentTable === 'acupoints') desc = `${item.meridian||''} ${(item.indication||'').substring(0,80)}`;
    else if (currentTable === 'clinical_cases') desc = `${item.case_date||''} ${(item.diagnosis||'').substring(0,80)}`;
    else if (currentTable === 'classics') desc = `${item.book_name||''} ${(item.content||'').substring(0,80)}`;
    else if (currentTable === 'lectures') desc = `${item.lecture_type||''} ${(item.content||'').substring(0,80)}`;
    else if (currentTable === 'treatment_methods') desc = `${item.related_herbs||''} ${(item.description||'').substring(0,80)}`;
    else if (currentTable === 'books') desc = `${item.author||''} [${item.category||''}] ${(item.content||'').substring(0,80)}`;
    else if (currentTable === 'tianji') desc = `${item.category||''} ${(item.content||'').substring(0,80)}`;
    else desc = JSON.stringify(item).substring(0,100);
    
    return `<div class="result-item" onclick="showDetail('${currentTable}',${item.id})">
      <span class="type-badge badge-${type}">${type}</span>
      ${item.is_high_risk ? '<span class="risk">⚠️高风险</span>' : ''}
      <h3>${title}</h3>
      <div class="desc">${desc}</div>
    </div>`;
  }).join('');
  
  // 分页
  const totalPages = Math.ceil(total / perPage);
  const pag = document.getElementById('pagination');
  if (totalPages <= 1) { pag.innerHTML = ''; return; }
  pag.innerHTML = `
    <button ${page<=1?'disabled':''} onclick="goPage(${page-1})">上一页</button>
    <span class="page-info">${page} / ${totalPages} (共${total}条)</span>
    <button ${page>=totalPages?'disabled':''} onclick="goPage(${page+1})">下一页</button>
  `;
}

function goPage(p) { currentPage = p; loadBrowse(); }

async function showDetail(table, id) {
  const item = await api(`detail/${table}/${id}`);
  if (!item) return;

  const panel = document.getElementById('detailPanel');
  const content = document.getElementById('detailContent');
  const label = TABLE_LABELS[table] || table;

  let html = `<h2>${item.name || item.title || item.patient_id || item.chapter_name || '详情'}</h2>`;

  const SKIP = new Set(['id','raw_path','source_repo','word_count','_relations']);
  const LONG = new Set(['content','commentary','bencao_raw','herbal_rx','notes','inquiry','indication','description','acupuncture_rx','diagnosis','pulse_diagnosis','tongue_diagnosis','eye_diagnosis']);
  // 收集有 _html 版本的字段名，后面跳过原始字段
  const hasHtml = new Set();
  for (const k of Object.keys(item)) {
    if (k.endsWith('_html') && item[k]) hasHtml.add(k.replace(/_html$/, ''));
  }

  for (const [k, v] of Object.entries(item)) {
    if (SKIP.has(k) || !v) continue;
    // 跳过有 _html 版本的原始字段（如 content，因为 content_html 会替代它）
    if (hasHtml.has(k)) continue;
    // _html 字段直接渲染为 HTML，标签名去掉 _html 后缀
    const isHtmlField = k.endsWith('_html');
    const displayName = isHtmlField ? k.replace(/_html$/, '') : k;
    const isLong = isHtmlField || LONG.has(k);
    html += `<div class="field">
      <div class="field-label">${displayName}</div>
      <div class="field-value">${isHtmlField ? v : (isLong ? '<pre>'+v+'</pre>' : v)}</div>
    </div>`;
  }

  // 渲染关联数据
  const rel = item._relations || {};
  if (rel.herbs && rel.herbs.length) {
    html += `<div class="field"><div class="field-label">💊 相关药物 (${rel.herbs.length})</div><div class="field-value">`;
    html += rel.herbs.map(h =>
      `<span class="tag" onclick="showDetail('herbs',${h.id})" title="${h.nature||''} ${h.flavor||''}">${h.name}${h.role && h.role !== '未知' ? '('+h.role+')' : ''}</span>`
    ).join(' ');
    html += `</div></div>`;
  }
  if (rel.formulas && rel.formulas.length) {
    html += `<div class="field"><div class="field-label">📋 相关方剂 (${rel.formulas.length})</div><div class="field-value">`;
    html += rel.formulas.map(f =>
      `<span class="tag" onclick="showDetail('formulas',${f.id})" title="${f.source_book||''}">${f.name}</span>`
    ).join(' ');
    html += `</div></div>`;
  }
  if (rel.syndromes && rel.syndromes.length) {
    html += `<div class="field"><div class="field-label">🔍 相关证型 (${rel.syndromes.length})</div><div class="field-value">`;
    html += rel.syndromes.map(s =>
      `<span class="tag" onclick="showDetail('syndromes',${s.id})" title="${s.six_channel||''}">${s.name}</span>`
    ).join(' ');
    html += `</div></div>`;
  }
  if (rel.symptoms && rel.symptoms.length) {
    html += `<div class="field"><div class="field-label">🩺 相关症状 (${rel.symptoms.length})</div><div class="field-value">`;
    html += rel.symptoms.map(s =>
      `<span class="tag" onclick="showDetail('symptoms',${s.id})" title="${s.category||''}">${s.name}</span>`
    ).join(' ');
    html += `</div></div>`;
  }
  if (rel.cases && rel.cases.length) {
    html += `<div class="field"><div class="field-label">📖 相关医案 (${rel.cases.length})</div><div class="field-value">`;
    html += rel.cases.map(c =>
      `<div class="case-link" onclick="showDetail('clinical_cases',${c.id})">${c.patient_id}: ${(c.chief_complaint||'').substring(0,60)}</div>`
    ).join('');
    html += `</div></div>`;
  }
  if (rel.course_notes && rel.course_notes.length) {
    html += `<div class="field"><div class="field-label">📚 课程资料 (${rel.course_notes.length})</div><div class="field-value">`;
    html += rel.course_notes.map(n =>
      `<div class="case-link" onclick="showDetail('course_notes',${n.id})">[${n.note_type}] ${n.title}</div>`
    ).join('');
    html += `</div></div>`;
  }

  content.innerHTML = html;
  panel.classList.add('open');
  document.getElementById('overlay').classList.add('show');
}

function closeDetail() {
  document.getElementById('detailPanel').classList.remove('open');
  document.getElementById('overlay').classList.remove('show');
}

// 搜索
let searchTimer;
document.getElementById('searchInput').addEventListener('input', function() {
  clearTimeout(searchTimer);
  const kw = this.value.trim();
  if (!kw) { if(currentTable) loadBrowse(); else document.getElementById('results').innerHTML=''; return; }
  searchTimer = setTimeout(async () => {
    const results = await api('search?q=' + encodeURIComponent(kw));
    renderSearchResults(results);
  }, 300);
});

function renderSearchResults(results) {
  const container = document.getElementById('results');
  document.getElementById('pagination').innerHTML = '';

  // 显示搜索导出按钮
  const exportBtn = document.getElementById('exportButtons');
  if (results.length > 0) {
    exportBtn.style.display = 'block';
    exportBtn.innerHTML = `
      <span style="color:#888; font-size:13px;">导出搜索结果：</span>
      <button onclick="exportSearchResults('json')" style="padding:4px 12px; background:#8b7355; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:12px;">JSON</button>
      <button onclick="exportSearchResults('csv')" style="padding:4px 12px; background:#6b8e6b; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:12px;">CSV</button>
    `;
  } else {
    exportBtn.style.display = 'none';
  }

  if (!results.length) { container.innerHTML = '<div class="loading">无结果</div>'; return; }

  // 类型到表名的映射
  const TYPE_TO_TABLE = {
    '中药': 'herbs', '方剂': 'formulas', '症状': 'symptoms',
    '医案': 'clinical_cases', '穴位': 'acupoints', '病机': 'syndromes',
    '治法': 'treatment_methods', '经典': 'classics', '讲座': 'lectures'
  };

  container.innerHTML = results.map(item => {
    const type = item.type;
    const table = TYPE_TO_TABLE[type] || '';
    const title = item.name || item.title || item.patient_id || item.chapter_name || '未知';
    let desc = '';
    if (type === '中药') desc = `[${item.category||''}] ${item.nature||''} ${(item.indication||'').substring(0,80)}`;
    else if (type === '方剂') desc = `${item.source_book||''} ${(item.syndrome||'').substring(0,80)}`;
    else if (type === '症状') desc = `${item.category||''} ${(item.description||'').substring(0,80)}`;
    else if (type === '医案') desc = `${item.case_date||''} ${(item.diagnosis||'').substring(0,80)}`;
    else if (type === '穴位') desc = `${item.meridian||''} ${(item.indication||'').substring(0,80)}`;
    else if (type === '病机') desc = `${(item.description||'').substring(0,80)}`;
    else if (type === '治法') desc = `${(item.description||'').substring(0,80)}`;
    else if (type === '经典') desc = `${item.book_name||''} ${(item.content||'').substring(0,80)}`;
    else if (type === '讲座') desc = `${item.lecture_type||''} ${(item.content||'').substring(0,80)}`;
    else desc = JSON.stringify(item).substring(0,100);

    return `<div class="result-item" ${table ? `onclick="showDetail('${table}',${item.id})"` : ''} style="${table ? 'cursor:pointer' : ''}">
      <span class="type-badge badge-${type}">${type}</span>
      <h3>${title}</h3>
      <div class="desc">${desc}</div>
    </div>`;
  }).join('');
}

// ESC 关闭
document.addEventListener('keydown', e => { if(e.key==='Escape') closeDetail(); });

init();
</script>
</body>
</html>'''

# ============================================================
# HTTP 服务器
# ============================================================
class TCMHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默日志
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        # 截图静态文件服务
        if path.startswith('/screenshots/'):
            rel = path[len('/screenshots/'):]
            file_path = SCREENSHOTS_DIR / rel
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                self.send_header('Content-Type', 'image/webp')
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
            return
        
        try:
            if path == '/' or path == '/index.html':
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
            
            elif path == '/api/stats':
                self.send_json(api_stats())
            
            elif path == '/api/search':
                kw = params.get('q', [''])[0]
                self.send_json(api_search(kw))
            
            elif path == '/api/browse':
                table = params.get('table', ['herbs'])[0]
                page = int(params.get('page', [1])[0])
                filters = {k:v[0] for k,v in params.items() if k not in ('table','page')}
                self.send_json(api_browse(table, page, filters=filters))
            
            elif path.startswith('/api/detail/'):
                parts = path.split('/')
                table, id = parts[3], int(parts[4])
                self.send_json(api_detail(table, id))
            
            elif path.startswith('/api/filter/'):
                parts = path.split('/')
                table, col = parts[3], parts[4]
                self.send_json(api_filter_options(table, col))

            elif path.startswith('/api/export/'):
                parts = path.split('/')
                if len(parts) >= 4:
                    target = parts[3]
                    fmt = params.get('format', ['json'])[0]

                    if target == 'search':
                        query = params.get('q', [''])[0]
                        if fmt == 'csv':
                            data = api_export_search(query, 'csv')
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/csv; charset=utf-8')
                            self.send_header('Content-Disposition', f'attachment; filename="search_{query}.csv"')
                            self.end_headers()
                            self.wfile.write(data.encode('utf-8'))
                        else:
                            self.send_json(api_export_search(query, 'json'))
                    else:
                        # 导出指定表
                        if fmt == 'csv':
                            data = api_export_table(target, 'csv')
                            self.send_response(200)
                            self.send_header('Content-Type', 'text/csv; charset=utf-8')
                            self.send_header('Content-Disposition', f'attachment; filename="{target}.csv"')
                            self.end_headers()
                            self.wfile.write(data.encode('utf-8'))
                        else:
                            self.send_json(api_export_table(target, 'json'))
                else:
                    self.send_error(400)

            else:
                self.send_error(404)
        
        except Exception as e:
            self.send_json({"error": str(e)}, 500)
    
    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode('utf-8'))

if __name__ == '__main__':
    print(f"🏥 倪海厦中医知识数据库 - Web 界面")
    print(f"   地址: http://localhost:{PORT}")
    print(f"   数据库: {DB_PATH}")
    print(f"   截图: {SCREENSHOTS_DIR}")
    print(f"   按 Ctrl+C 停止\n")
    server = HTTPServer(('0.0.0.0', PORT), TCMHandler)
    server.serve_forever()
