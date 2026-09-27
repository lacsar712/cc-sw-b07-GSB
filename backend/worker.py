import os
import time
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from domain import ensure_schema, judge

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54395/spectrum")


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


def release_if_expired(conn, now):
    """缓领到点则解除并写解除流水，返回最新闸门状态行。"""
    st = conn.execute(
        "SELECT consecutive_overruns, gating, release_at FROM gate_state WHERE id=1 FOR UPDATE"
    ).fetchone()
    if st["gating"] and st["release_at"] and st["release_at"] <= now:
        cfg = conn.execute(
            "SELECT threshold, pause_seconds FROM gate_config WHERE id=1"
        ).fetchone()
        conn.execute(
            """
            INSERT INTO gate_journal(action, threshold_snapshot, pause_seconds_snapshot,
                                     consecutive_overruns, trigger_job_id, created_at)
            VALUES ('解除缓领', %s, %s, %s, NULL, %s)
            """,
            (cfg["threshold"], cfg["pause_seconds"], st["consecutive_overruns"], now),
        )
        conn.execute(
            "UPDATE gate_state SET gating=false, release_at=NULL WHERE id=1"
        )
        conn.commit()
        st = conn.execute(
            "SELECT consecutive_overruns, gating, release_at FROM gate_state WHERE id=1 FOR UPDATE"
        ).fetchone()
    return st


def claim_one(conn):
    now = datetime.now(timezone.utc)
    st = release_if_expired(conn, now)
    if st["gating"]:
        # 缓领中：普通待处理暂停领取，急测待处理仍可领取
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
        conn.commit()
        return None
    verdict, reason = judge(row["nominal_nm"], row["measured_nm"])
    conn.execute(
        "UPDATE jobs SET status='done', verdict=%s, reason=%s, finished_at=%s WHERE id=%s",
        (verdict, reason, now, row["id"]),
    )

    # 连续超差串只随新结案更新；阈值只在结案这一刻起效，改阈值不追溯旧流水
    streak = st["consecutive_overruns"] + 1 if verdict == "超差" else 0
    if not st["gating"] and verdict == "超差":
        cfg = conn.execute(
            "SELECT threshold, pause_seconds FROM gate_config WHERE id=1"
        ).fetchone()
        if streak >= cfg["threshold"]:
            release_at = now + timedelta(seconds=cfg["pause_seconds"])
            conn.execute(
                "UPDATE gate_state SET consecutive_overruns=0, gating=true, release_at=%s WHERE id=1",
                (release_at,),
            )
            conn.execute(
                """
                INSERT INTO gate_journal(action, threshold_snapshot, pause_seconds_snapshot,
                                         consecutive_overruns, trigger_job_id, created_at)
                VALUES ('开始缓领', %s, %s, %s, %s, %s)
                """,
                (cfg["threshold"], cfg["pause_seconds"], streak, row["id"], now),
            )
            conn.commit()
            return row["id"]
    conn.execute(
        "UPDATE gate_state SET consecutive_overruns=%s WHERE id=1", (streak,)
    )
    conn.commit()
    return row["id"]


def main():
    while True:
        try:
            with connect() as conn:
                ensure_schema(conn)
                conn.commit()
            break
        except Exception as exc:
            print("worker init err", exc, flush=True)
            time.sleep(1)
    while True:
        try:
            with connect() as conn:
                claim_one(conn)
        except Exception as exc:
            print("worker err", exc, flush=True)
        time.sleep(0.4)


if __name__ == "__main__":
    main()
