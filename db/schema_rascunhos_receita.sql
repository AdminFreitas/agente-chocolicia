-- Rascunhos do motor local. Não é a tabela recipes do site.
CREATE TABLE IF NOT EXISTS agent_recipe_drafts (
    id BIGSERIAL PRIMARY KEY,
    title TEXT,
    slug TEXT,
    description TEXT,
    prep_time TEXT,
    cook_time TEXT,
    servings TEXT,
    difficulty TEXT,
    ingredients JSONB,
    steps JSONB,
    tips JSONB,
    meta_description TEXT,
    schema_org JSONB,
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'failed')),
    error_log TEXT,
    topic TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS agent_recipe_drafts_status_idx
    ON agent_recipe_drafts (status, created_at DESC);
