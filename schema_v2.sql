-- ============================================================
-- 倪海厦中医知识数据库 Schema V2
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ========== 核心实体 ==========

CREATE TABLE IF NOT EXISTS herbs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    alias TEXT,
    category TEXT,          -- 上经/中经/下经/倪师补充/小编补充/医案补充
    nature TEXT,            -- 寒/热/温/凉/平
    flavor TEXT,            -- 酸/苦/甘/辛/咸
    toxicity TEXT,
    meridian_tropism TEXT,
    origin TEXT,
    indication TEXT,
    bencao_raw TEXT,        -- 本经原文
    commentary TEXT,        -- 全文讲解
    raw_path TEXT,
    source_repo TEXT
);

CREATE TABLE IF NOT EXISTS formulas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    alias TEXT,
    source_book TEXT,       -- 伤寒论/金匮要略/汉唐方剂/临床记录
    chapter TEXT,
    six_channel TEXT,
    syndrome TEXT,
    indication TEXT,
    composition TEXT,
    dosage TEXT,
    contraindication TEXT,
    differentiation TEXT,
    lesson_ref TEXT,
    is_high_risk INTEGER DEFAULT 0,
    commentary TEXT,
    raw_path TEXT,
    source_repo TEXT
);

CREATE TABLE IF NOT EXISTS symptoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    first_gateway TEXT,
    target_module TEXT,
    required_questions TEXT,
    differential TEXT
);

CREATE TABLE IF NOT EXISTS syndromes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    six_channel TEXT,
    eight_principles TEXT,
    location TEXT,
    core_symptoms TEXT,
    key_differentiation TEXT,
    representative_formulas TEXT,
    contraindication TEXT,
    course_ref TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS acupoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pinyin TEXT,
    meridian TEXT,
    location TEXT,
    indication TEXT,
    technique TEXT,
    is_key_point INTEGER DEFAULT 0,
    commentary TEXT,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS meridians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    organ TEXT,
    type TEXT,
    flow_direction TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS clinical_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_date TEXT,
    patient_id TEXT,
    gender TEXT,
    age TEXT,
    chief_complaint TEXT,
    inquiry TEXT,
    pulse_diagnosis TEXT,
    tongue_diagnosis TEXT,
    eye_diagnosis TEXT,
    diagnosis TEXT,
    acupuncture_rx TEXT,
    herbal_rx TEXT,
    notes TEXT,
    disease_tags TEXT,
    raw_path TEXT,
    source_repo TEXT
);

CREATE TABLE IF NOT EXISTS folk_formulas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    disease TEXT,
    indication TEXT,
    composition TEXT,
    usage_info TEXT,
    source TEXT,
    commentary TEXT,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    order_num INTEGER,
    total_hours REAL,
    lesson_count INTEGER,
    description TEXT,
    key_topics TEXT,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS classics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_name TEXT NOT NULL,
    chapter_name TEXT,
    chapter_num TEXT,
    content TEXT,
    annotation TEXT,
    word_count INTEGER,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS course_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module_name TEXT NOT NULL,
    note_type TEXT,
    title TEXT,
    content TEXT,
    word_count INTEGER,
    raw_path TEXT,
    source_repo TEXT DEFAULT 'nihaixia'
);

CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    category TEXT,
    content TEXT,
    word_count INTEGER,
    format TEXT,            -- md/pdf
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    speaker TEXT,
    lecture_type TEXT,
    date_info TEXT,
    content TEXT,
    word_count INTEGER,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS tianji (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,
    content TEXT,
    word_count INTEGER,
    raw_path TEXT
);

CREATE TABLE IF NOT EXISTS treatment_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    related_pathomechanism TEXT,
    related_herbs TEXT,
    related_acupoints TEXT,
    raw_path TEXT,
    source_repo TEXT DEFAULT 'nihaixia-kb'
);

CREATE TABLE IF NOT EXISTS diagnostic_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    note_type TEXT,
    content TEXT,
    word_count INTEGER,
    raw_path TEXT
);

-- ========== 关系表 ==========

CREATE TABLE IF NOT EXISTS formula_herbs (
    formula_id INTEGER REFERENCES formulas(id),
    herb_id INTEGER REFERENCES herbs(id),
    role TEXT,
    dosage_in_formula TEXT,
    note TEXT,
    PRIMARY KEY (formula_id, herb_id)
);

CREATE TABLE IF NOT EXISTS formula_syndromes (
    formula_id INTEGER REFERENCES formulas(id),
    syndrome_id INTEGER REFERENCES syndromes(id),
    relevance TEXT DEFAULT 'primary',
    PRIMARY KEY (formula_id, syndrome_id)
);

CREATE TABLE IF NOT EXISTS syndrome_symptoms (
    syndrome_id INTEGER REFERENCES syndromes(id),
    symptom_id INTEGER REFERENCES symptoms(id),
    is_key INTEGER DEFAULT 0,
    PRIMARY KEY (syndrome_id, symptom_id)
);

CREATE TABLE IF NOT EXISTS case_formulas (
    case_id INTEGER REFERENCES clinical_cases(id),
    formula_id INTEGER REFERENCES formulas(id),
    is_acupuncture INTEGER DEFAULT 0,
    PRIMARY KEY (case_id, formula_id)
);

CREATE TABLE IF NOT EXISTS case_herbs (
    case_id INTEGER REFERENCES clinical_cases(id),
    herb_id INTEGER REFERENCES herbs(id),
    dosage TEXT,
    note TEXT,
    PRIMARY KEY (case_id, herb_id)
);

-- ========== 索引 ==========

CREATE INDEX IF NOT EXISTS idx_herbs_name ON herbs(name);
CREATE INDEX IF NOT EXISTS idx_herbs_cat ON herbs(category);
CREATE INDEX IF NOT EXISTS idx_herbs_nature ON herbs(nature);
CREATE INDEX IF NOT EXISTS idx_formulas_name ON formulas(name);
CREATE INDEX IF NOT EXISTS idx_formulas_channel ON formulas(six_channel);
CREATE INDEX IF NOT EXISTS idx_formulas_source ON formulas(source_book);
CREATE INDEX IF NOT EXISTS idx_classics_book ON classics(book_name);
CREATE INDEX IF NOT EXISTS idx_notes_module ON course_notes(module_name);
CREATE INDEX IF NOT EXISTS idx_notes_type ON course_notes(note_type);
CREATE INDEX IF NOT EXISTS idx_cases_date ON clinical_cases(case_date);
CREATE INDEX IF NOT EXISTS idx_cases_diag ON clinical_cases(diagnosis);
CREATE INDEX IF NOT EXISTS idx_books_cat ON books(category);
CREATE INDEX IF NOT EXISTS idx_lectures_type ON lectures(lecture_type);
CREATE INDEX IF NOT EXISTS idx_syndromes_channel ON syndromes(six_channel);
CREATE INDEX IF NOT EXISTS idx_treatment_name ON treatment_methods(name);
