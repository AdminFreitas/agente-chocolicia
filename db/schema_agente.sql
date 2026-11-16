CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    phase INTEGER NOT NULL,
    result TEXT,
    git_sha TEXT,
    prompt_version TEXT
);

CREATE TABLE IF NOT EXISTS agent_generations (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    content_type TEXT NOT NULL CHECK (content_type IN ('recipe','technique','tip','feature')),
    topic TEXT NOT NULL,
    topic_slug TEXT NOT NULL,
    subcategory_slug TEXT,
    status TEXT NOT NULL CHECK (status IN ('planned','generated','rejected','sent','published','unpublished','error')),
    rejection_code TEXT,
    rejection_detail TEXT,
    site_content_id TEXT,
    site_content_slug TEXT,
    model TEXT,
    prompt_version TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER,
    cost_usd REAL,
    sources TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (content_type, topic_slug)
);

CREATE TABLE IF NOT EXISTS agent_topic_queue (
    id INTEGER PRIMARY KEY,
    content_type TEXT NOT NULL,
    topic TEXT NOT NULL,
    topic_slug TEXT NOT NULL UNIQUE,
    subcategory_slug TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    origin TEXT NOT NULL CHECK (origin IN ('calendar','coverage','search_console','manual')),
    earliest_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued','taken','done','rejected'))
);

CREATE TABLE IF NOT EXISTS agent_costs (
    day TEXT NOT NULL,
    component TEXT NOT NULL CHECK (component IN ('llm','search','image')),
    amount_usd REAL NOT NULL DEFAULT 0,
    units INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, component)
);
