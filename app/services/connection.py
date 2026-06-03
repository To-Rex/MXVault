import re
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
    return _test_pg_connection(conn.host, conn.port, conn.database, conn.username, password)


def _test_connection_raw(host: str, port: int) -> dict:
    return _test_pg_connection(host, port, "postgres", "postgres", "")


def _test_pg_connection(host: str, port: int, database: str, username: str, password: str) -> dict:
    host = _clean_host(host)
    start = time.time()

    try:
        import psycopg2
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password,
            connect_timeout=10,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        latency = (time.time() - start) * 1000
        return {
            "success": True,
            "message": "Connection successful",
            "latency_ms": round(latency, 2),
        }
    except ImportError:
        return _test_pg_connection_raw_socket(host, port, database, username, password)
    except psycopg2.OperationalError as e:
        msg = str(e).strip()
        if msg:
            msg = msg[0].upper() + msg[1:] if len(msg) > 1 else msg
        return {"success": False, "message": msg or "Connection failed"}
    except psycopg2.ProgrammingError as e:
        return {"success": False, "message": str(e).strip()}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_pg_connection_raw_socket(host: str, port: int, database: str, username: str, password: str) -> dict:
    host = _clean_host(host)
    start = time.time()

    try:
        import hashlib
        import socket
        import struct

        sock = socket.create_connection((host, port), timeout=10)
        sock.settimeout(5)

        user_bytes = username.encode()
        db_bytes = database.encode()
        payload = b"user\x00" + user_bytes + b"\x00" + b"database\x00" + db_bytes + b"\x00" + b"\x00"
        length = 4 + 4 + len(payload)
        startup = struct.pack("!ii", length, 196608) + payload

        sock.sendall(startup)

        def _recv_exact(n: int) -> bytes:
            data = b""
            while len(data) < n:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    break
                data += chunk
            return data

        while True:
            msg_type_byte = _recv_exact(1)
            if not msg_type_byte:
                sock.close()
                return {"success": False, "message": "Server closed the connection unexpectedly."}

            msg_type = msg_type_byte[0]

            if msg_type == ord('R'):
                length_bytes = _recv_exact(4)
                if len(length_bytes) < 4:
                    sock.close()
                    return {"success": False, "message": "Incomplete auth response."}
                auth_len = struct.unpack("!i", length_bytes)[0]
                if auth_len < 8 or auth_len > 1000:
                    sock.close()
                    return {"success": False, "message": "Invalid PostgreSQL response."}
                remaining = auth_len - 4
                auth_data = _recv_exact(remaining)
                if len(auth_data) < 4:
                    sock.close()
                    return {"success": False, "message": "Incomplete auth data."}
                auth_type = struct.unpack("!i", auth_data[:4])[0]

                if auth_type == 0:
                    sock.close()
                    latency = (time.time() - start) * 1000
                    return {
                        "success": True,
                        "message": "Connection successful",
                        "latency_ms": round(latency, 2),
                    }
                elif auth_type == 5:
                    if len(auth_data) < 8:
                        sock.close()
                        return {"success": False, "message": "Incomplete MD5 salt from server."}
                    salt = auth_data[4:8]
                    inner = hashlib.md5((password + username).encode()).hexdigest().encode()
                    outer_input = inner + salt
                    outer = b"md5" + hashlib.md5(outer_input).hexdigest().encode()
                    pw_msg = b"p" + struct.pack("!i", len(outer) + 5) + outer + b"\x00"
                    sock.sendall(pw_msg)
                    continue
                else:
                    sock.close()
                    return {
                        "success": True,
                        "message": "Connection successful (auth type {})".format(auth_type),
                        "latency_ms": round((time.time() - start) * 1000, 2),
                    }

            elif msg_type == ord('E'):
                length_bytes = _recv_exact(4)
                error_text = "Server rejected the connection"
                if len(length_bytes) >= 4:
                    msg_len = struct.unpack("!i", length_bytes)[0]
                    remaining = max(0, msg_len - 4)
                    if remaining > 0:
                        payload_bytes = _recv_exact(remaining)
                        error_text = _parse_pg_error(payload_bytes) or error_text
                sock.close()
                return {"success": False, "message": error_text}

            elif msg_type == ord('K'):
                length_bytes = _recv_exact(4)
                if len(length_bytes) >= 4:
                    remain = struct.unpack("!i", length_bytes)[0] - 4
                    if remain > 0:
                        _recv_exact(remain)
                sock.close()
                latency = (time.time() - start) * 1000
                return {
                    "success": True,
                    "message": "Connection successful",
                    "latency_ms": round(latency, 2),
                }

            elif msg_type == ord('S'):
                length_bytes = _recv_exact(4)
                if len(length_bytes) >= 4:
                    remain = struct.unpack("!i", length_bytes)[0] - 4
                    if remain > 0:
                        _recv_exact(remain)
                continue

            elif msg_type == ord('Z'):
                _recv_exact(4)
                sock.close()
                latency = (time.time() - start) * 1000
                return {
                    "success": True,
                    "message": "Connection successful",
                    "latency_ms": round(latency, 2),
                }

            else:
                sock.close()
                return {"success": False, "message": "Not a PostgreSQL server (unexpected response: 0x{:02x}).".format(msg_type)}

    except socket.timeout:
        return {"success": False, "message": "Connection timed out"}
    except socket.gaierror:
        return {"success": False, "message": "Host not found. Check the hostname."}
    except ConnectionRefusedError:
        return {"success": False, "message": "Connection refused. Check host and port."}
    except OSError as e:
        return {"success": False, "message": "Network error: {}".format(e)}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _parse_pg_error(data: bytes) -> str:
    try:
        fields = {}
        data_str = data.decode("utf-8", errors="replace")
        parts = data_str.split("\x00")
        i = 0
        while i < len(parts) - 1:
            code = parts[i]
            if code in ("S", "M", "D", "C", "R"):
                fields[code] = parts[i + 1] if i + 1 < len(parts) else ""
                i += 2
            else:
                i += 1
        return fields.get("M", fields.get("S", "Server rejected the connection"))
    except Exception:
        return "Server rejected the connection"


def get_pg_dsn(conn: PGConnection, dbname: str | None = None) -> str:
    password = decrypt_password(conn.encrypted_password)
    host = _clean_host(conn.host)
    dsn = f"postgresql://{conn.username}:{password}@{host}:{conn.port}/{dbname or conn.database}"
    if conn.ssl_mode != "disable":
        dsn += f"?sslmode={conn.ssl_mode}"
    return dsn
