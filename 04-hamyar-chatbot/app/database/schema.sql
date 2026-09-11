-- Hamyar — SQLite schema.
-- Applied on every start; all statements are idempotent.

PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------- knowledge base
CREATE TABLE IF NOT EXISTS faq (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'عمومی',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_faq_category ON faq(category);

-- Alternative phrasings of a question. They are indexed together with the
-- primary question, which raises recall for paraphrased user input.
CREATE TABLE IF NOT EXISTS faq_variant (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    faq_id INTEGER NOT NULL REFERENCES faq(id) ON DELETE CASCADE,
    text   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_variant_faq ON faq_variant(faq_id);

-- ------------------------------------------------------------------ conversation
CREATE TABLE IF NOT EXISTS conversation (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    user_text      TEXT NOT NULL,
    matched_faq_id INTEGER REFERENCES faq(id) ON DELETE SET NULL,
    matched_text   TEXT,
    score          REAL NOT NULL DEFAULT 0,
    confidence     TEXT NOT NULL DEFAULT 'low',
    answered       INTEGER NOT NULL DEFAULT 0,
    category       TEXT,
    feedback       TEXT,
    latency_ms     INTEGER,
    created_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversation(session_id, id);
CREATE INDEX IF NOT EXISTS idx_conv_created ON conversation(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_matched ON conversation(matched_faq_id);
CREATE INDEX IF NOT EXISTS idx_conv_answered ON conversation(answered);

-- ---------------------------------------------------------------------- handoff
CREATE TABLE IF NOT EXISTS handoff (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    reason     TEXT,
    last_query TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_handoff_created ON handoff(created_at DESC);
