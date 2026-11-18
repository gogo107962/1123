-- SQLite schema: generated from db.SCHEMA

PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS policies (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, agency TEXT, region TEXT,
  category TEXT, description TEXT, demo_only INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS policy_versions (
  id TEXT PRIMARY KEY, policy_code TEXT NOT NULL REFERENCES policies(code) ON DELETE CASCADE,
  version TEXT NOT NULL, status TEXT NOT NULL, reviewed_by TEXT,
  reviewed_at TEXT, open_date TEXT, close_date TEXT,
  source_url TEXT, payload_json TEXT NOT NULL, sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(policy_code, version)
);
CREATE TABLE IF NOT EXISTS policy_sources (
  id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES policy_versions(id) ON DELETE CASCADE,
  reference TEXT NOT NULL, kind TEXT, title TEXT, url TEXT, anchor TEXT, excerpt TEXT,
  verified INTEGER NOT NULL DEFAULT 0, UNIQUE(version_id, reference)
);
CREATE TABLE IF NOT EXISTS policy_rules (
  id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES policy_versions(id) ON DELETE CASCADE,
  rule_type TEXT NOT NULL, source_ref TEXT NOT NULL, predicate_json TEXT NOT NULL, message TEXT
);
CREATE TABLE IF NOT EXISTS document_requirements (
  id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES policy_versions(id) ON DELETE CASCADE,
  document_code TEXT NOT NULL, title TEXT NOT NULL, issuer TEXT, source_ref TEXT NOT NULL,
  constraints_json TEXT NOT NULL, required_when_json TEXT, alternatives_json TEXT NOT NULL,
  instructions TEXT
);
CREATE TABLE IF NOT EXISTS demo_sessions (
  id TEXT PRIMARY KEY, persona TEXT NOT NULL, facts_json TEXT NOT NULL,
  selected_json TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS session_documents (
  session_id TEXT NOT NULL REFERENCES demo_sessions(id) ON DELETE CASCADE,
  document_code TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('unknown','owned','missing')),
  PRIMARY KEY(session_id,document_code)
);
CREATE TABLE IF NOT EXISTS preparation_tasks (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES demo_sessions(id) ON DELETE CASCADE,
  task_key TEXT NOT NULL, title TEXT NOT NULL, instructions TEXT, status TEXT NOT NULL DEFAULT 'todo'
  CHECK(status IN ('todo','doing','done')), source_refs_json TEXT NOT NULL,
  generated_revision INTEGER NOT NULL DEFAULT 0,
  generated_fingerprint TEXT NOT NULL DEFAULT '',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(session_id,task_key)
);
CREATE TABLE IF NOT EXISTS eligibility_checks (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES demo_sessions(id) ON DELETE CASCADE,
  policy_version_id TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT NOT NULL,
  checked_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS agent_runs (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES demo_sessions(id) ON DELETE CASCADE,
  user_message TEXT NOT NULL, status TEXT NOT NULL, response_text TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  tool_name TEXT NOT NULL, status TEXT NOT NULL, sanitized_result_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_policy_version_status ON policy_versions(status);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON preparation_tasks(session_id);
CREATE TABLE IF NOT EXISTS ontong_sync_runs (
  id TEXT PRIMARY KEY, keyword TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, pages INTEGER NOT NULL DEFAULT 0,
  received INTEGER NOT NULL DEFAULT 0, changed INTEGER NOT NULL DEFAULT 0,
  matched_total INTEGER, has_more INTEGER NOT NULL DEFAULT 0, error_code TEXT
);
CREATE TABLE IF NOT EXISTS ontong_candidates (
  external_id TEXT PRIMARY KEY, name TEXT NOT NULL, agency TEXT NOT NULL,
  summary TEXT NOT NULL, application_text TEXT NOT NULL, source_url TEXT NOT NULL,
  payload_json TEXT NOT NULL, sha256 TEXT NOT NULL,
  first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
  last_run_id TEXT NOT NULL REFERENCES ontong_sync_runs(id)
);
CREATE TABLE IF NOT EXISTS ontong_snapshots (
  external_id TEXT NOT NULL REFERENCES ontong_candidates(external_id),
  sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, fetched_at TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES ontong_sync_runs(id),
  PRIMARY KEY(external_id, sha256)
);
CREATE TABLE IF NOT EXISTS desk_workspaces (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS desk_bookmarks (
  workspace_id TEXT NOT NULL REFERENCES desk_workspaces(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL REFERENCES ontong_candidates(external_id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(workspace_id,external_id)
);
CREATE TABLE IF NOT EXISTS desk_tasks (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES desk_workspaces(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL REFERENCES ontong_candidates(external_id),
  task_key TEXT NOT NULL, title TEXT NOT NULL, instructions TEXT NOT NULL,
  sources_json TEXT NOT NULL, evidence_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','done')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(workspace_id,external_id,task_key)
);
CREATE TABLE IF NOT EXISTS desk_agent_runs (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES desk_workspaces(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL, status TEXT NOT NULL, tools_json TEXT NOT NULL DEFAULT '[]',
  elapsed_ms INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
