import os
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("celesto_ledger")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ledger:ledger@ledger:5432/ledger")

# In-memory storage fallback if postgres is not accessible (e.g. unit tests without compose)
_memory_runs: Dict[str, Dict[str, Any]] = {
    "run-seed-001": {
        "run_id": "run-seed-001",
        "sandbox_name": "sbx-seeddemo1",
        "problem_id": "prob-hostile-autograder",
        "state": "deleted",
        "execution_target": "celesto_sandbox",
        "created_at": "2026-10-24T05:00:00Z",
        "metadata": {"seeded": True, "description": "Initial demonstration seed run"}
    }
}

def get_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
        return conn
    except Exception as e:
        logger.warning(f"Could not connect to Postgres at {DATABASE_URL}: {e}. Using fallback storage.")
        return None

def init_db():
    conn = get_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
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
                """)
                conn.commit()
                logger.info("Database initialized successfully with seed data.")
        except Exception as e:
            logger.error(f"Error initializing DB schema: {e}")
            conn.rollback()
        finally:
            conn.close()

def list_runs() -> List[Dict[str, Any]]:
    conn = get_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT run_id, sandbox_name, problem_id, state, execution_target, created_at, metadata FROM runs ORDER BY created_at ASC")
                rows = cur.fetchall()
                results = []
                for row in rows:
                    item = dict(row)
                    if isinstance(item.get("created_at"), datetime):
                        item["created_at"] = item["created_at"].isoformat()
                    results.append(item)
                return results
        except Exception as e:
            logger.error(f"Error querying runs from DB: {e}")
            return list(_memory_runs.values())
        finally:
            conn.close()
    return list(_memory_runs.values())

def insert_run(run_data: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "run_id": run_data["run_id"],
        "sandbox_name": run_data["sandbox_name"],
        "problem_id": run_data["problem_id"],
        "state": run_data["state"],
        "execution_target": run_data["execution_target"],
        "created_at": now_iso,
        "metadata": run_data.get("metadata", {})
    }
    _memory_runs[record["run_id"]] = record

    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    sandbox_name = EXCLUDED.sandbox_name,
                    problem_id = EXCLUDED.problem_id,
                    state = EXCLUDED.state,
                    execution_target = EXCLUDED.execution_target,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING run_id, sandbox_name, problem_id, state, execution_target, created_at, metadata
                """, (
                    record["run_id"],
                    record["sandbox_name"],
                    record["problem_id"],
                    record["state"],
                    record["execution_target"],
                    json.dumps(record["metadata"])
                ))
                saved_row = cur.fetchone()
                conn.commit()
                res = dict(saved_row)
                if isinstance(res.get("created_at"), datetime):
                    res["created_at"] = res["created_at"].isoformat()
                return res
        except Exception as e:
            logger.error(f"Error inserting run into DB: {e}")
            conn.rollback()
            return record
        finally:
            conn.close()
    return record
