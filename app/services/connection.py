import re
import subprocess
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.connection import PGConnection
from app.utils.crypto import decrypt_password, encrypt_password


def _clean_host(host: str) -> str:
    return re.sub(r'^https?://', '', host).rstrip('/')


def create_connection(
    db: Session,
    name: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    ssl_mode: str = "prefer",
) -> PGConnection:
    conn = PGConnection(
        id=str(uuid4()),
        name=name,
        host=_clean_host(host),
        port=port,
        database=database,
        username=username,
        encrypted_password=encrypt_password(password),
        ssl_mode=ssl_mode,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def update_connection(db: Session, connection_id: str, **kwargs) -> PGConnection | None:
    conn = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not conn:
        return None
    if "password" in kwargs and kwargs["password"]:
        kwargs["encrypted_password"] = encrypt_password(kwargs.pop("password"))
    if "host" in kwargs and kwargs["host"]:
        kwargs["host"] = _clean_host(kwargs["host"])
    for key, value in kwargs.items():
        if value is not None and hasattr(conn, key):
            setattr(conn, key, value)
    db.commit()
    db.refresh(conn)
    return conn


def delete_connection(db: Session, connection_id: str) -> bool:
    conn = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not conn:
        return False
    db.delete(conn)
    db.commit()
    return True


def test_connection(conn: PGConnection) -> dict:
    password = decrypt_password(conn.encrypted_password)
    start = time.time()
    host = _clean_host(conn.host)
    env = {"PGPASSWORD": password}
    if conn.ssl_mode != "disable":
        env["PGSSLMODE"] = conn.ssl_mode
    try:
        result = subprocess.run(
            [
                "psql",
                "-h", host,
                "-p", str(conn.port),
                "-U", conn.username,
                "-d", conn.database,
                "-c", "SELECT version()",
                "-t",
                "-A",
            ],
            input=f"{password}\n",
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        latency = (time.time() - start) * 1000
        if result.returncode == 0:
            return {
                "success": True,
                "message": "Connection successful",
                "server_version": result.stdout.strip(),
                "latency_ms": round(latency, 2),
            }
        else:
            return {
                "success": False,
                "message": result.stderr.strip() or "Connection failed",
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Connection timed out"}
    except FileNotFoundError:
        return {"success": False, "message": "PostgreSQL client (psql) not found. Install postgresql-client."}
    except Exception as e:
        return {"success": False, "message": str(e)}


def get_pg_dsn(conn: PGConnection, dbname: str | None = None) -> str:
    password = decrypt_password(conn.encrypted_password)
    host = _clean_host(conn.host)
    dsn = f"postgresql://{conn.username}:{password}@{host}:{conn.port}/{dbname or conn.database}"
    if conn.ssl_mode != "disable":
        dsn += f"?sslmode={conn.ssl_mode}"
    return dsn
