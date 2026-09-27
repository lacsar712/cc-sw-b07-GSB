TOLERANCE_NM = 0.08

DEFAULT_GATE_THRESHOLD = 2
DEFAULT_GATE_PAUSE_SECONDS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id serial PRIMARY KEY,
    lamp text NOT NULL,
    nominal_nm double precision NOT NULL,
    measured_nm double precision NOT NULL,
    status text NOT NULL,
    verdict text NOT NULL DEFAULT '',
    reason text NOT NULL DEFAULT '',
    created_by text NOT NULL,
    created_at timestamptz NOT NULL
);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS priority text NOT NULL DEFAULT 'normal';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at timestamptz;

CREATE TABLE IF NOT EXISTS gate_config (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    threshold integer NOT NULL,
    pause_seconds integer NOT NULL,
    updated_by text NOT NULL DEFAULT '',
    updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS gate_state (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    consecutive_overruns integer NOT NULL DEFAULT 0,
    gating boolean NOT NULL DEFAULT false,
    release_at timestamptz
);

CREATE TABLE IF NOT EXISTS gate_journal (
    id serial PRIMARY KEY,
    action text NOT NULL,
    threshold_snapshot integer NOT NULL,
    pause_seconds_snapshot integer NOT NULL,
    consecutive_overruns integer NOT NULL,
    trigger_job_id integer,
    created_at timestamptz NOT NULL
);
"""


def ensure_schema(conn):
    """建表、补列并写入闸门配置/状态单行，幂等，API 与 worker 启动时各调一次。"""
    conn.execute(SCHEMA)
    conn.execute(
        """
        INSERT INTO gate_config(id, threshold, pause_seconds, updated_by, updated_at)
        VALUES (1, %s, %s, 'system', now())
        ON CONFLICT (id) DO NOTHING
        """,
        (DEFAULT_GATE_THRESHOLD, DEFAULT_GATE_PAUSE_SECONDS),
    )
    conn.execute("INSERT INTO gate_state(id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def judge(nominal: float, measured: float) -> tuple[str, str]:
    delta = abs(measured - nominal)
    if delta <= TOLERANCE_NM:
        return "合格", f"偏差 {delta:.4f} nm 在允差内"
    return "超差", f"偏差 {delta:.4f} nm 超过允差 {TOLERANCE_NM}"
