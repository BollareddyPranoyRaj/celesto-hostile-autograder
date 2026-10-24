-- Table definition for runs ledger
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR(128) PRIMARY KEY,
    sandbox_name VARCHAR(128) NOT NULL,
    problem_id VARCHAR(128) NOT NULL,
    state VARCHAR(32) NOT NULL CHECK (state IN ('created', 'ready', 'running', 'succeeded', 'failed', 'deleted')),
    execution_target VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs(sandbox_name);
CREATE INDEX IF NOT EXISTS idx_runs_state ON runs(state);

-- Seed row with sbx-seeddemo1, state deleted, execution target celesto_sandbox
-- Idempotent: re-running does not duplicate
INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target, metadata)
VALUES (
    'run-seed-001',
    'sbx-seeddemo1',
    'prob-hostile-autograder',
    'deleted',
    'celesto_sandbox',
    '{"seeded": true, "description": "Initial demonstration seed run"}'::jsonb
)
ON CONFLICT (run_id) DO NOTHING;
