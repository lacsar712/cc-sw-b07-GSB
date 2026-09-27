import os
import time
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from domain import (
    SCHEMA,
    ensure_gate_rows,
    get_gate_settings,
    get_hold_until,
    judge,
    recent_fail_streak,
)

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54395/spectrum")


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


def release_expired_hold(conn, now, settings) -> bool:
    """缓领到点则解除并写一条解除流水。返回当前是否仍在缓领。"""
    hold_until = get_hold_until(conn)
    if hold_until is None:
        return False
    if hold_until > now:
        return True
    conn.execute(
        "INSERT INTO gate_events(event, detail, created_at) VALUES ('hold_end', %s, %s)",
        (f"缓领 {settings['hold_seconds']} 秒耗尽，普通待处理恢复领取", now),
    )
    conn.execute("UPDATE gate_state SET hold_until = NULL WHERE id = 1")
    conn.commit()
    return False


def claim_one(conn, holding: bool):
    if holding:
        row = conn.execute(
            """
            SELECT id, nominal_nm, measured_nm FROM jobs
            WHERE status='pending' AND priority='urgent'
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id, nominal_nm, measured_nm FROM jobs
            WHERE status='pending'
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
    if not row:
        conn.rollback()
        return None
    verdict, reason = judge(row["nominal_nm"], row["measured_nm"])
    conn.execute(
        "UPDATE jobs SET status='done', verdict=%s, reason=%s WHERE id=%s",
        (verdict, reason, row["id"]),
    )
    return row["id"], verdict


def maybe_start_hold(conn, now, settings, verdict: str, holding: bool) -> None:
    """新结案为超差且当前未缓领时，连续超差条数达阈值即开始缓领并写开始流水。"""
    if holding or verdict != "超差":
        return
    streak = recent_fail_streak(conn)
    if streak < settings["threshold"]:
        return
    until = now + timedelta(seconds=settings["hold_seconds"])
    conn.execute(
        "INSERT INTO gate_events(event, detail, created_at) VALUES ('hold_start', %s, %s)",
        (
            f"连续超差 {streak} 条达到阈值 {settings['threshold']}，"
            f"缓领 {settings['hold_seconds']} 秒，普通待处理暂停领取",
            now,
        ),
    )
    conn.execute("UPDATE gate_state SET hold_until = %s WHERE id = 1", (until,))


def tick(conn) -> None:
    now = datetime.now(timezone.utc)
    settings = get_gate_settings(conn)
    holding = release_expired_hold(conn, now, settings)
    claimed = claim_one(conn, holding)
    if claimed:
        _, verdict = claimed
        maybe_start_hold(conn, now, settings, verdict, holding)
    conn.commit()


def main():
    while True:
        try:
            with connect() as conn:
                conn.execute(SCHEMA)
                ensure_gate_rows(conn)
                conn.commit()
            break
        except Exception as exc:
            print("worker init err", exc, flush=True)
            time.sleep(1)
    while True:
        try:
            with connect() as conn:
                tick(conn)
        except Exception as exc:
            print("worker err", exc, flush=True)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
