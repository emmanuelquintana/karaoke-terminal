"""Persistencia de sesiones en Neon; el modo local conserva sus diccionarios."""
import os
from pathlib import Path


def _connect():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    url = os.environ["DATABASE_URL"]
    root_cert = conninfo_to_dict(url).get("sslrootcert") or os.environ.get("PGSSLROOTCERT") or "system"
    return psycopg.connect(url, sslmode="verify-full", sslrootcert=root_cert, connect_timeout=10)


def init_database() -> None:
    with _connect() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS karaoke_studio_sessions "
            "(id TEXT PRIMARY KEY, payload JSONB NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS karaoke_studio_exports "
            "(id TEXT PRIMARY KEY, path TEXT NOT NULL)"
        )


def save_session(session_id: str, session: dict, local: dict) -> None:
    if not os.environ.get("DATABASE_URL"):
        local[session_id] = session
        return
    from psycopg.types.json import Jsonb

    with _connect() as connection:
        connection.execute(
            "INSERT INTO karaoke_studio_sessions (id, payload) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload",
            (session_id, Jsonb(session)),
        )


def load_session(session_id: str, local: dict):
    if not os.environ.get("DATABASE_URL"):
        return local.get(session_id)
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM karaoke_studio_sessions WHERE id = %s", (session_id,)
        ).fetchone()
    return row[0] if row else None


def save_export(export_id: str, path: Path, local: dict) -> None:
    if not os.environ.get("DATABASE_URL"):
        local[export_id] = path
        return
    with _connect() as connection:
        connection.execute(
            "INSERT INTO karaoke_studio_exports (id, path) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET path = EXCLUDED.path",
            (export_id, str(path)),
        )


def load_export(export_id: str, local: dict):
    if not os.environ.get("DATABASE_URL"):
        return local.get(export_id)
    with _connect() as connection:
        row = connection.execute(
            "SELECT path FROM karaoke_studio_exports WHERE id = %s", (export_id,)
        ).fetchone()
    return Path(row[0]) if row else None


if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Configura DATABASE_URL con la conexión PostgreSQL de Neon.")
    init_database()
