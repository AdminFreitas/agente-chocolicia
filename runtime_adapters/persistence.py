from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT PRIMARY KEY,
  content_type TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'created',
  topic_slug TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS agent_image_usage (
  image_url TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL,
  provider TEXT,
  first_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  usage_count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS agent_publications (
  run_id TEXT PRIMARY KEY REFERENCES agent_runs(run_id),
  remote_id TEXT,
  slug TEXT,
  status TEXT NOT NULL,
  url TEXT,
  published_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS agent_cost_events (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
  provider TEXT NOT NULL,
  model TEXT,
  operation TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(12,6) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

class PostgresStore:
    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("AGENT_DATABASE_URL ausente")
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True, future=True)

    def migrate(self):
        with self.engine.begin() as conn:
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(text(statement))

    def start_run(self, run_id: str, content_type: str, target: str, topic_slug: str | None = None):
        with self.engine.begin() as conn:
            conn.execute(text("""
              INSERT INTO agent_runs(run_id,content_type,target,status,stage,topic_slug)
              VALUES(:id,:type,:target,'running','started',:slug)
              ON CONFLICT(run_id) DO NOTHING
            """), {"id":run_id,"type":content_type,"target":target,"slug":topic_slug})

    def update_run(self, run_id: str, status: str, stage: str, details: dict | None = None):
        with self.engine.begin() as conn:
            conn.execute(text("""
              UPDATE agent_runs SET status=:status, stage=:stage,
                details=details || CAST(:details AS jsonb),
                finished_at=CASE WHEN :finished THEN NOW() ELSE finished_at END
              WHERE run_id=:id
            """), {"id":run_id,"status":status,"stage":stage,
                   "details":json.dumps(details or {}),"finished":status not in {"running","queued"}})

    def record_cost(self, run_id: str, provider: str, model: str, operation: str,
                    input_tokens: int, output_tokens: int, cost_usd: float):
        with self.engine.begin() as conn:
            conn.execute(text("""
              INSERT INTO agent_cost_events(run_id,provider,model,operation,input_tokens,output_tokens,cost_usd)
              VALUES(:run,:provider,:model,:op,:inp,:out,:cost)
            """), {"run":run_id,"provider":provider,"model":model,"op":operation,
                   "inp":input_tokens,"out":output_tokens,"cost":cost_usd})
            conn.execute(text("UPDATE agent_runs SET cost_usd=cost_usd+:cost WHERE run_id=:run"),
                         {"run":run_id,"cost":cost_usd})

    def record_publication(self, run_id: str, remote_id: str, slug: str, status: str, url: str | None):
        with self.engine.begin() as conn:
            conn.execute(text("""
              INSERT INTO agent_publications(run_id,remote_id,slug,status,url,published_at)
              VALUES(:run,:remote,:slug,:status,:url,CASE WHEN :status='published' THEN NOW() END)
              ON CONFLICT(run_id) DO UPDATE SET remote_id=EXCLUDED.remote_id,
                slug=EXCLUDED.slug,status=EXCLUDED.status,url=EXCLUDED.url,
                published_at=EXCLUDED.published_at
            """), {"run":run_id,"remote":remote_id,"slug":slug,"status":status,"url":url})

    def image_was_used(self, image_url: str) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT 1 FROM agent_image_usage WHERE image_url=:url"),
                                {"url":image_url}).first() is not None

    def register_image(self, image_url: str, sha256: str, provider: str = ""):
        with self.engine.begin() as conn:
            conn.execute(text("""
              INSERT INTO agent_image_usage(image_url,sha256,provider)
              VALUES(:url,:sha,:provider)
              ON CONFLICT(image_url) DO UPDATE SET last_used_at=NOW(),
                usage_count=agent_image_usage.usage_count+1
            """), {"url":image_url,"sha":sha256,"provider":provider})

    def usada_url(self, url: str) -> bool:
        return self.image_was_used(url)

    def usada_provider_id(self, provider: str, provider_image_id: str) -> bool:
        return False

    def usada_hash(self, sha256: str) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT 1 FROM agent_image_usage WHERE sha256=:sha"),
                {"sha": sha256},
            ).first() is not None

    def registrar(self, url: str, sha256: str, provider: str, provider_image_id: str) -> None:
        self.register_image(url, sha256, provider)
