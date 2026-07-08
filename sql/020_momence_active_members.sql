-- Momence Active Members weekly snapshots → imports/momence/inbox/ActiveMembers/

CREATE TABLE IF NOT EXISTS momence_active_members (
    id                  TEXT PRIMARY KEY,
    source_file         TEXT NOT NULL,
    snapshot_date       DATE NOT NULL,
    membership          TEXT NOT NULL,
    membership_type     TEXT,
    avg_usage           NUMERIC(8, 2),
    active_count        INTEGER NOT NULL,
    is_presale          BOOLEAN NOT NULL DEFAULT FALSE,
    raw_data            JSONB NOT NULL,
    imported_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_momence_active_members_snapshot ON momence_active_members(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_momence_active_members_presale ON momence_active_members(is_presale);

ALTER TABLE momence_active_members ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE momence_active_members FROM anon, authenticated;
