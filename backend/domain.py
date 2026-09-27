from datetime import datetime, timezone

TOLERANCE_NM = 0.08

DEFAULT_THRESHOLD = 2
DEFAULT_HOLD_SECONDS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id serial PRIMARY KEY,
    lamp text NOT NULL,
    nominal_nm double precision NOT NULL,
    measured_nm double precision NOT NULL,
    status text NOT NULL,
    verdict text NOT NULL DEFAULT '',
    reason text NOT NULL DEFAULT '',
    priority text NOT NULL DEFAULT 'normal',
    created_by text NOT NULL,
    created_at timestamptz NOT NULL
);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS priority text NOT NULL DEFAULT 'normal';
CREATE TABLE IF NOT EXISTS gate_settings (
    id smallint PRIMARY KEY,
    threshold integer NOT NULL,
    hold_seconds integer NOT NULL,
    updated_by text NOT NULL DEFAULT '',
    updated_at timestamptz
);
CREATE TABLE IF NOT EXISTS gate_state (
    id smallint PRIMARY KEY,
    hold_until timestamptz
);
CREATE TABLE IF NOT EXISTS gate_events (
    id serial PRIMARY KEY,
    event text NOT NULL,
    detail text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL
);
"""


def ensure_gate_rows(conn) -> None:
    now = datetime.now(timezone.utc)
    conn.execute(
        """
        INSERT INTO gate_settings(id, threshold, hold_seconds, updated_by, updated_at)
        VALUES (1, %s, %s, 'system', %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (DEFAULT_THRESHOLD, DEFAULT_HOLD_SECONDS, now),
    )
    conn.execute(
        "INSERT INTO gate_state(id, hold_until) VALUES (1, NULL) ON CONFLICT (id) DO NOTHING"
    )


def judge(nominal: float, measured: float) -> tuple[str, str]:
    delta = abs(measured - nominal)
    if delta <= TOLERANCE_NM:
        return "合格", f"偏差 {delta:.4f} nm 在允差内"
    return "超差", f"偏差 {delta:.4f} nm 超过允差 {TOLERANCE_NM}"


def get_gate_settings(conn) -> dict:
    return conn.execute(
        "SELECT threshold, hold_seconds, updated_by, updated_at FROM gate_settings WHERE id = 1"
    ).fetchone()


def get_hold_until(conn):
    row = conn.execute("SELECT hold_until FROM gate_state WHERE id = 1").fetchone()
    return row["hold_until"] if row else None


def recent_fail_streak(conn, limit: int = 200) -> int:
    """最近已结案记录里连续超差的条数（遇到合格即断）。"""
    rows = conn.execute(
        "SELECT verdict FROM jobs WHERE status = 'done' ORDER BY id DESC LIMIT %s",
        (limit,),
    ).fetchall()
    streak = 0
    for row in rows:
        if row["verdict"] == "超差":
            streak += 1
        else:
            break
    return streak
