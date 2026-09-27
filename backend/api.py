import os
from datetime import datetime, timedelta, timezone

import psycopg
from jose import JWTError, jwt
from litestar import Litestar, Request, get, post, put
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from passlib.context import CryptContext
from psycopg.rows import dict_row
from pydantic import BaseModel

from domain import ensure_schema

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54395/spectrum")
SECRET = os.environ.get("JWT_SECRET", "spectrum-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "calibrator": {"role": "writer", "password_hash": pwd.hash("calib123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

JOB_COLS = "id, lamp, nominal_nm, measured_nm, status, verdict, reason, priority, created_by"


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


class LoginIn(BaseModel):
    username: str
    password: str


class JobIn(BaseModel):
    lamp: str
    nominal_nm: float
    measured_nm: float
    priority: str = "normal"


class GateConfigIn(BaseModel):
    threshold: int
    pause_seconds: int


def user_from_request(request: Request) -> dict:
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = jwt.decode(auth[7:], SECRET, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="无效令牌") from exc
    if payload.get("sub") not in USERS:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="无效令牌")
    return {"username": payload["sub"], "role": payload.get("role")}


def gate_snapshot(conn) -> dict:
    cfg = conn.execute(
        "SELECT threshold, pause_seconds, updated_by, updated_at FROM gate_config WHERE id=1"
    ).fetchone()
    st = conn.execute(
        "SELECT consecutive_overruns, gating, release_at FROM gate_state WHERE id=1"
    ).fetchone()
    journal = conn.execute(
        """
        SELECT id, action, threshold_snapshot, pause_seconds_snapshot,
               consecutive_overruns, trigger_job_id, created_at
        FROM gate_journal ORDER BY id DESC LIMIT 50
        """
    ).fetchall()
    now = datetime.now(timezone.utc)
    gating = bool(st["gating"] and st["release_at"] and st["release_at"] > now)
    return {
        "threshold": cfg["threshold"],
        "pause_seconds": cfg["pause_seconds"],
        "updated_by": cfg["updated_by"],
        "updated_at": cfg["updated_at"].isoformat() if cfg["updated_at"] else None,
        "gating": gating,
        "release_at": st["release_at"].isoformat() if gating else None,
        "consecutive_overruns": st["consecutive_overruns"],
        "journal": [
            {
                "id": j["id"],
                "action": j["action"],
                "threshold_snapshot": j["threshold_snapshot"],
                "pause_seconds_snapshot": j["pause_seconds_snapshot"],
                "consecutive_overruns": j["consecutive_overruns"],
                "trigger_job_id": j["trigger_job_id"],
                "created_at": j["created_at"].isoformat(),
            }
            for j in journal
        ],
    }


@get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "spectrum-wavelength-desk"}


@post("/api/login")
async def login(data: LoginIn) -> dict:
    u = USERS.get(data.username)
    if not u or not pwd.verify(data.password, u["password_hash"]):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    token = jwt.encode(
        {
            "sub": data.username,
            "role": u["role"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        },
        SECRET,
        algorithm="HS256",
    )
    return {"access_token": token, "role": u["role"], "username": data.username}


@get("/api/jobs")
async def list_jobs(request: Request) -> list:
    user_from_request(request)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {JOB_COLS} FROM jobs ORDER BY id DESC"
        ).fetchall()
        return list(rows)


@get("/api/jobs/{job_id:int}")
async def get_job(request: Request, job_id: int) -> dict:
    user_from_request(request)
    with connect() as conn:
        row = conn.execute(
            f"SELECT {JOB_COLS} FROM jobs WHERE id = %s",
            (job_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        return dict(row)


@post("/api/jobs")
async def create_job(request: Request, data: JobIn) -> dict:
    user = user_from_request(request)
    if user["role"] != "writer":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="仅校准员可提交")
    if data.priority not in ("normal", "urgent"):
        raise HTTPException(status_code=400, detail="优先级仅支持 normal 或 urgent")
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO jobs(lamp, nominal_nm, measured_nm, status, verdict, reason, priority, created_by, created_at)
            VALUES (%s,%s,%s,'pending','','',%s,%s,%s) RETURNING id
            """,
            (
                data.lamp.strip(),
                data.nominal_nm,
                data.measured_nm,
                data.priority,
                user["username"],
                datetime.now(timezone.utc),
            ),
        ).fetchone()
        conn.commit()
        return {"id": row["id"], "status": "pending"}


@get("/api/gate")
async def get_gate(request: Request) -> dict:
    user_from_request(request)
    with connect() as conn:
        return gate_snapshot(conn)


@put("/api/gate/config")
async def put_gate_config(request: Request, data: GateConfigIn) -> dict:
    user = user_from_request(request)
    if user["role"] != "writer":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="仅校准员可改阈值与秒数")
    if data.threshold < 1:
        raise HTTPException(status_code=400, detail="连续超差阈值至少为 1")
    if data.pause_seconds < 1:
        raise HTTPException(status_code=400, detail="缓领秒数至少为 1")
    with connect() as conn:
        # 只改配置本身，不动既有流水：新阈值/秒数只约束此后的新结案串
        conn.execute(
            "UPDATE gate_config SET threshold=%s, pause_seconds=%s, updated_by=%s, updated_at=%s WHERE id=1",
            (data.threshold, data.pause_seconds, user["username"], datetime.now(timezone.utc)),
        )
        conn.commit()
        return gate_snapshot(conn)


def on_startup() -> None:
    with connect() as conn:
        ensure_schema(conn)
        n = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        if n == 0:
            now = datetime.now(timezone.utc)
            conn.execute(
                """
                INSERT INTO jobs(lamp, nominal_nm, measured_nm, status, verdict, reason, priority, created_by, created_at, finished_at)
                VALUES
                ('氦灯-587', 587.56, 587.50, 'done', '合格', '偏差 0.0600 nm 在允差内', 'normal', 'seed', %s, %s),
                ('汞灯-546', 546.07, 546.30, 'done', '超差', '偏差 0.2300 nm 超过允差 0.08', 'normal', 'seed', %s, %s)
                """,
                (now, now, now, now),
            )
        conn.commit()


app = Litestar(
    route_handlers=[health, login, list_jobs, get_job, create_job, get_gate, put_gate_config],
    on_startup=[on_startup],
)
