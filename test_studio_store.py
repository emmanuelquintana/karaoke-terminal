import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import studio_store


class StudioStoreTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "Requiere PostgreSQL de prueba con TLS")
    def test_postgres_round_trip_without_process_memory(self):
        session_id = uuid.uuid4().hex
        export_id = uuid.uuid4().hex
        with patch.dict(os.environ, {"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}):
            studio_store.init_database()
            studio_store.init_database()
            try:
                session = {"videoPath": "/data/video.mp4", "song": {"lines": [{"text": "Canción", "time": 1}]}}
                studio_store.save_session(session_id, session, {})
                self.assertEqual(studio_store.load_session(session_id, {}), session)
                session["song"]["lines"][0]["time"] = 2
                studio_store.save_session(session_id, session, {})
                self.assertEqual(studio_store.load_session(session_id, {}), session)
                studio_store.save_export(export_id, Path("/data/clip.mp4"), {})
                self.assertEqual(studio_store.load_export(export_id, {}), Path("/data/clip.mp4"))
                self.assertIsNone(studio_store.load_session(uuid.uuid4().hex, {}))
            finally:
                with studio_store._connect() as connection:
                    connection.execute("DELETE FROM karaoke_studio_sessions WHERE id = %s", (session_id,))
                    connection.execute("DELETE FROM karaoke_studio_exports WHERE id = %s", (export_id,))

    def test_local_mode_needs_no_database(self):
        sessions, exports = {}, {}
        session = {"videoPath": "video.mp4", "song": {"lines": []}}
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            studio_store.save_session("session", session, sessions)
            studio_store.save_export("export", Path("clip.mp4"), exports)
            self.assertEqual(studio_store.load_session("session", sessions), session)
            self.assertEqual(studio_store.load_export("export", exports), Path("clip.mp4"))
            self.assertIsNone(studio_store.load_session("missing", sessions))

    def test_neon_sessions_are_written_and_reloaded_without_memory(self):
        session = {"videoPath": "/data/video.mp4", "song": {"lines": [{"text": "Canción", "time": 0}]}}
        with patch.dict(os.environ, {"DATABASE_URL": "configured"}), patch.object(studio_store, "_connect") as connect:
            connection = connect.return_value.__enter__.return_value
            studio_store.save_session("id'", session, {})
            query, params = connection.execute.call_args.args
            self.assertIn("ON CONFLICT", query)
            self.assertEqual(params[0], "id'")
            self.assertEqual(params[1].obj, session)
            connection.execute.return_value.fetchone.return_value = (session,)
            self.assertEqual(studio_store.load_session("id'", {}), session)
            self.assertEqual(connection.execute.call_args.args[1], ("id'",))
            connection.execute.return_value.fetchone.return_value = None
            self.assertIsNone(studio_store.load_session("missing", {}))

    def test_neon_exports_are_reloaded_as_paths(self):
        with patch.dict(os.environ, {"DATABASE_URL": "configured"}), patch.object(studio_store, "_connect") as connect:
            connection = connect.return_value.__enter__.return_value
            studio_store.save_export("export", Path("clip.mp4"), {})
            self.assertEqual(connection.execute.call_args.args[1], ("export", "clip.mp4"))
            connection.execute.return_value.fetchone.return_value = ("clip.mp4",)
            self.assertEqual(studio_store.load_export("export", {}), Path("clip.mp4"))
            connection.execute.return_value.fetchone.return_value = None
            self.assertIsNone(studio_store.load_export("missing", {}))

    def test_configured_database_failure_does_not_silently_lose_data(self):
        with patch.dict(os.environ, {"DATABASE_URL": "configured"}), patch.object(studio_store, "_connect", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                studio_store.save_session("id", {}, {})

    def test_neon_connection_requires_tls_and_has_a_timeout(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example/neondb", "PGSSLROOTCERT": ""}), patch("psycopg.connect") as connect:
            studio_store._connect()
            connect.assert_called_once_with("postgresql://example/neondb", sslmode="verify-full", sslrootcert="system", connect_timeout=10)

    def test_database_custom_ca_is_preserved_and_tls_cannot_be_downgraded(self):
        url = "postgresql://example/neondb?sslmode=disable&sslrootcert=custom-ca.pem"
        with patch.dict(os.environ, {"DATABASE_URL": url}), patch("psycopg.connect") as connect:
            studio_store._connect()
            connect.assert_called_once_with(url, sslmode="verify-full", sslrootcert="custom-ca.pem", connect_timeout=10)

    def test_schema_initialization_is_idempotent_and_transactional(self):
        with patch.object(studio_store, "_connect") as connect:
            studio_store.init_database()
            connection = connect.return_value.__enter__.return_value
            self.assertEqual(connection.execute.call_count, 2)
            for call in connection.execute.call_args_list:
                self.assertIn("CREATE TABLE IF NOT EXISTS", call.args[0])
            connect.return_value.__exit__.assert_called_once_with(None, None, None)


if __name__ == "__main__":
    unittest.main()
