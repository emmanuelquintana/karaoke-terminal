"""RUN_DOCKER_TESTS=1 python -m unittest test_docker_deployment -v (requiere Docker)."""
import hashlib
import json
import os
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path


SEED = r'''
import json
import subprocess
import karaoke_terminal as engine
import karaoke_web as web
import studio_store

with studio_store._connect() as connection:
    assert connection.pgconn.ssl_in_use
engine.cache_result(engine.TrackInfo("AuditArtist", "AuditSong", duration=6),
                    "[00:00.20]Hola Vercel\n[00:03.00]Sesión persistente", "")
engine.ensure_audio_cache_dir()
web.ensure_studio_cache_dir()
key = web._studio_key("audit-video")
video = web.STUDIO_CACHE_DIR / f"video-{key}.mp4"
subprocess.run([web._ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=6:r=24",
               "-f", "lavfi", "-i", "aevalsrc=sin(2*PI*440*t)*(0.5+0.3*sin(2*PI*0.7*t)):s=44100:d=6",
               "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video)], check=True, capture_output=True)
(web.STUDIO_CACHE_DIR / f"video-{key}.json").write_text(
    json.dumps({"title": "Audit video", "duration": 6, "webpageUrl": "", "thumbnail": None}), encoding="utf8")
subprocess.run([web._ffmpeg_exe(), "-y", "-i", str(video), "-vn",
               engine.audio_cache_path("AuditArtist", "AuditSong")], check=True, capture_output=True)
# La única sustitución de red del servidor evita depender de iTunes en esta prueba.
(engine.DATA_DIR / "audit_gunicorn.py").write_text(
    "def post_worker_init(worker):\n    import karaoke_web\n    karaoke_web.fetch_cover_art = lambda *args, **kwargs: None\n")
print("Fixtures sintéticos y conexión TLS verificada preparados")
'''


@unittest.skipUnless(os.environ.get("RUN_DOCKER_TESTS") == "1", "Activar RUN_DOCKER_TESTS=1 para la integración Docker")
class DockerDeploymentTests(unittest.TestCase):
    def docker(self, *args, source=None):
        result = subprocess.run(["docker", *args], input=source, text=True, encoding="utf8",
                                capture_output=True, timeout=300)
        if result.returncode:
            self.fail(f"docker {args[0]} falló:\n{result.stdout[-2000:]}\n{result.stderr[-3000:]}")
        return result.stdout.strip()

    def cleanup_docker(self, *args):
        subprocess.run(["docker", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)

    def setUp(self):
        self.prefix = f"karaoke-audit-{uuid.uuid4().hex[:10]}"
        self.image = self.prefix + "-image"
        self.api = self.prefix + "-api"
        self.database = self.prefix + "-db"
        self.origin = "https://audit.example.com"
        self.docker("build", "-q", "-t", self.image, str(Path(__file__).resolve().parent))
        self.addCleanup(self.cleanup_docker, "image", "rm", self.image)
        self.docker("network", "create", self.prefix)
        self.addCleanup(self.cleanup_docker, "network", "rm", self.prefix)
        for volume in (self.prefix + "-certs", self.prefix + "-data"):
            self.docker("volume", "create", volume)
            self.addCleanup(self.cleanup_docker, "volume", "rm", volume)
        self.certs = f"source={self.prefix}-certs,target=/certs"
        self.data = f"source={self.prefix}-data,target=/data"
        self.docker("run", "--rm", "--mount", self.certs, "--entrypoint", "openssl", self.image,
                    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "/certs/server.key",
                    "-out", "/certs/server.crt", "-days", "1", "-subj", f"/CN={self.database}",
                    "-addext", f"subjectAltName=DNS:{self.database},DNS:localhost,IP:127.0.0.1")
        self.docker("run", "--detach", "--rm", "--name", self.database, "--network", self.prefix,
                    "--mount", self.certs + ",readonly", "--env", "POSTGRES_HOST_AUTH_METHOD=trust",
                    "--entrypoint", "sh", "postgres:17-alpine", "-c",
                    "cp /certs/server.* /tmp/ && chmod 600 /tmp/server.key && "
                    "chown postgres:postgres /tmp/server.* && exec docker-entrypoint.sh postgres "
                    "-c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key")
        self.addCleanup(self.cleanup_docker, "rm", "-f", self.database)
        for _ in range(100):
            result = subprocess.run(["docker", "exec", self.database, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(0.2)
        else:
            self.fail("PostgreSQL no arrancó")
        self.database_url = f"postgresql://postgres@{self.database}:5432/postgres?sslrootcert=/certs/server.crt"
        self.docker("run", "--rm", "-i", "--network", self.prefix, "--user", "karaoke",
                    "--mount", self.certs + ",readonly", "--mount", self.data,
                    "--env", f"DATABASE_URL={self.database_url}", "--entrypoint", "python", self.image, "-", source=SEED)
        self.addCleanup(self.cleanup_docker, "rm", "-f", self.api)
        self.start_api()

    def start_api(self, port=""):
        self.docker("run", "--detach", "--rm", "--name", self.api, "--network", self.prefix,
                    "--memory", "512m", "--memory-swap", "512m", "--cpus", "0.1",
                    "--publish", f"127.0.0.1:{port}:8000", "--mount", self.data, "--mount", self.certs + ",readonly",
                    "--env", f"DATABASE_URL={self.database_url}", "--env", f"FRONTEND_ORIGINS={self.origin}",
                    "--env", "GUNICORN_CMD_ARGS=--config /data/audit_gunicorn.py", self.image)
        self.port = self.docker("port", self.api, "8000/tcp").rsplit(":", 1)[-1]
        self.base = f"http://127.0.0.1:{self.port}"
        for _ in range(100):
            try:
                self.request("/api/v1/health")
                return
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        self.fail("API no arrancó:\n" + self.docker("logs", "--tail", "30", self.api))

    def request(self, path, payload=None, method=None, headers=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request_headers = {"Origin": self.origin, **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            self.fail(f"HTTP {error.code}: {error.read().decode('utf8', errors='replace')}")

    def test_prepare_sync_export_and_recover_after_container_replacement(self):
        status, headers, _ = self.request("/api/v1/studio-sessions", method="OPTIONS", headers={
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.origin)
        self.assertIn("Content-Type", headers["Access-Control-Allow-Headers"])
        status, _, body = self.request("/api/v1/studio-sessions", {"video": "audit-video", "artist": "AuditArtist", "title": "AuditSong"})
        self.assertEqual(status, 201)
        session = json.loads(body)["data"]
        session_path = f"/api/v1/studio-sessions/{session['sessionId']}"
        status, _, body = self.request(session_path + "/sync", {})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(json.loads(body)["data"]["confidence"], 0.24)
        status, _, body = self.request(session_path + "/exports", {"length": 2, "format": "vertical"})
        self.assertEqual(status, 201)
        download = json.loads(body)["data"]["downloadUrl"]
        _, _, original = self.request(download)
        self.assertGreater(len(original), 1000)

        self.docker("rm", "-f", self.api)
        self.start_api(self.port)
        for path in (session["videoUrl"], download, "/api/v1/songs/audio?artist=AuditArtist&title=AuditSong"):
            status, headers, body = self.request(path, headers={"Range": "bytes=0-63"})
            self.assertEqual(status, 206)
            self.assertEqual(len(body), 64)
            self.assertEqual(headers["Access-Control-Allow-Origin"], self.origin)
            self.assertTrue(headers["Content-Range"].startswith("bytes 0-63/"))
        status, headers, recovered = self.request(download)
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(hashlib.sha256(original).digest(), hashlib.sha256(recovered).digest())
        _, headers, _ = self.request("/api/v1/health", headers={"Origin": "https://evil.example.com"})
        self.assertNotIn("Access-Control-Allow-Origin", headers)

        sql_tests = Path(__file__).with_name("test_studio_store.py").read_text(encoding="utf8")
        self.docker("exec", "-i", "--user", "karaoke", "--env", f"TEST_DATABASE_URL={self.database_url}",
                    self.api, "python", "-", source=sql_tests)
        print("PostgreSQL store suite passed with a real TLS database (including the optional round trip)")

        check = r'''
import os
import socket
import json
import subprocess
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import karaoke_terminal as engine
import karaoke_web as web
import studio_store
assert engine.DATA_DIR == Path('/data')
assert not web.STUDIO_SESSIONS and not web.STUDIO_EXPORTS
for pattern in ('segment-*.mp4','video-only-*.mp4','concat-*.txt','caption-*.png'):
    assert not list(web.STUDIO_CACHE_DIR.glob(pattern)), pattern
with studio_store._connect() as connection:
    assert connection.pgconn.ssl_in_use
    assert connection.execute('SELECT count(*) FROM karaoke_studio_sessions').fetchone()[0] == 1
    assert connection.execute('SELECT count(*) FROM karaoke_studio_exports').fetchone()[0] == 1
    path = connection.execute('SELECT path FROM karaoke_studio_exports').fetchone()[0]
probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',path]))
video = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
audio = next(stream for stream in probe['streams'] if stream['codec_type'] == 'audio')
assert (video['codec_name'],video['width'],video['height']) == ('h264',1080,1920)
assert 1.8 <= float(video['duration']) <= 2.2
assert audio['codec_name'] == 'aac'
original = os.environ['DATABASE_URL']
os.environ['DATABASE_URL'] = original.replace('sslrootcert=/certs/server.crt','sslrootcert=system')
try:
    studio_store._connect()
except psycopg.OperationalError:
    pass
else:
    raise AssertionError('Se aceptó una CA no confiable')
address = socket.gethostbyname(conninfo_to_dict(original)['host'])
os.environ['DATABASE_URL'] = make_conninfo(original, host='wrong-host.invalid', hostaddr=address)
try:
    studio_store._connect()
except psycopg.OperationalError:
    pass
else:
    raise AssertionError('Se aceptó un hostname TLS incorrecto')
print('Session, audio, video, MP4, temp cleanup, TLS CA and hostname verified after container replacement')
'''
        print(self.docker("exec", "-i", "--user", "karaoke", self.api, "python", "-", source=check))


if __name__ == "__main__":
    unittest.main()
