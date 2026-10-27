-- Storage for the web app. One database file keeps every run and the
-- work the business does on its findings (status, owner, comment).
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    created_at    TEXT NOT NULL,
    label         TEXT NOT NULL,
    path          TEXT NOT NULL,
    source        TEXT NOT NULL,          -- upload or sample
    extract_dir   TEXT NOT NULL,
    seconds       REAL,
    totals_json   TEXT NOT NULL           -- records per object at run time
);

CREATE TABLE IF NOT EXISTS findings (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    rule        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    object      TEXT NOT NULL,
    key         TEXT NOT NULL,
    field       TEXT,
    message     TEXT,
    fix         TEXT,
    related     TEXT,
    weight      REAL NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    owner       TEXT NOT NULL DEFAULT '',
    comment     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_findings_run_rule ON findings(run_id, rule);
CREATE INDEX IF NOT EXISTS ix_findings_run_status ON findings(run_id, status);

-- Who changed what and when. Auditors ask for this first.
CREATE TABLE IF NOT EXISTS finding_events (
    id          INTEGER PRIMARY KEY,
    finding_id  INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    at          TEXT NOT NULL,
    changed_by  TEXT NOT NULL,
    old_status  TEXT,
    new_status  TEXT,
    comment     TEXT
);
