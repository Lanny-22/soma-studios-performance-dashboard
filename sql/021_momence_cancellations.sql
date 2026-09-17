-- Momence membership cancellations → imports/momence/inbox/Cancellations/

CREATE TABLE IF NOT EXISTS momence_cancellations (
    id                      TEXT PRIMARY KEY,
    source_file             TEXT NOT NULL,
    cancelled_at            TIMESTAMPTZ NOT NULL,
    customer_name           TEXT,
    customer_email          TEXT,
    membership              TEXT,
    reason                  TEXT,
    possible_improvements   TEXT,
    home_location           TEXT,
    raw_data                JSONB NOT NULL,
    imported_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_momence_cancellations_cancelled_at
    ON momence_cancellations (cancelled_at);

ALTER TABLE momence_cancellations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE momence_cancellations FROM anon, authenticated;
