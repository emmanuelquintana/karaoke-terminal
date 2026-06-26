import json
import unittest
from unittest.mock import patch

import karaoke_terminal as engine
import karaoke_web
from karaoke_terminal import LyricLine, TrackInfo


class CoverArtTests(unittest.TestCase):
    def test_score_prefers_exact_match(self) -> None:
        exact = {"artistName": "Coldplay", "trackName": "Yellow"}
        partial = {"artistName": "Coldplay", "trackName": "Yellow (Live)"}
        self.assertGreater(
            karaoke_web._itunes_score(exact, "Coldplay", "Yellow"),
            karaoke_web._itunes_score(partial, "Coldplay", "Yellow"),
        )

    def test_fetch_cover_art_upgrades_resolution(self) -> None:
        fake = {
            "results": [
                {
                    "artistName": "Coldplay",
                    "trackName": "Yellow",
                    "artworkUrl100": "https://x/100x100bb.jpg",
                }
            ]
        }

        class FakeResp:
            def read(self):
                return json.dumps(fake).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            url = karaoke_web.fetch_cover_art("Coldplay", "Yellow", size=600)
        self.assertEqual(url, "https://x/600x600bb.jpg")

    def test_fetch_cover_art_handles_empty_results(self) -> None:
        class FakeResp:
            def read(self):
                return b'{"results": []}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            self.assertIsNone(karaoke_web.fetch_cover_art("X", "Y"))


class ResolveForWebTests(unittest.TestCase):
    def test_payload_shape_with_synced_lyrics(self) -> None:
        track = TrackInfo(artist="A", title="B", album="Disco", duration=120.0)
        with patch.object(engine, "search_track", return_value=(track, "[00:01.00]hola", "")), \
                patch.object(karaoke_web, "fetch_cover_art", return_value="http://cover"):
            payload = karaoke_web.resolve_for_web("A", "B")
        self.assertEqual(payload["mode"], "sincronizado")
        self.assertEqual(payload["cover"], "http://cover")
        self.assertEqual(payload["lines"][0], {"time": 1.0, "text": "hola"})
        self.assertIn("audioAvailable", payload)

    def test_raises_when_no_lyrics(self) -> None:
        track = TrackInfo(artist="A", title="B")
        with patch.object(engine, "search_track", return_value=(track, "", "")):
            with self.assertRaises(engine.LyricsLookupError):
                karaoke_web.resolve_for_web("A", "B")


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = karaoke_web.app.test_client()

    def test_index_and_static_served(self) -> None:
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/web/app.js").status_code, 200)

    def test_song_requires_params(self) -> None:
        self.assertEqual(self.client.get("/api/song").status_code, 400)

    def test_song_returns_payload(self) -> None:
        payload = {"title": "B", "artist": "A", "lines": [], "mode": "sincronizado"}
        with patch.object(karaoke_web, "resolve_for_web", return_value=payload):
            res = self.client.get("/api/song?artist=A&title=B")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["title"], "B")

    def test_cover_rejects_untrusted_host(self) -> None:
        res = self.client.get("/api/cover?u=https://evil.example.com/x.jpg")
        self.assertEqual(res.status_code, 400)
        res2 = self.client.get("/api/cover?u=http://127.0.0.1/secret")
        self.assertEqual(res2.status_code, 400)

    def test_cover_allows_itunes_host(self) -> None:
        with patch("urllib.request.urlopen") as fake:
            fake.return_value.__enter__.return_value.read.return_value = b"img"
            fake.return_value.__enter__.return_value.headers = {"Content-Type": "image/jpeg"}
            res = self.client.get("/api/cover?u=https://is1-ssl.mzstatic.com/a/1000x1000bb.jpg")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "image/jpeg")

    def test_song_404_when_not_found(self) -> None:
        with patch.object(karaoke_web, "resolve_for_web", side_effect=engine.LyricsLookupError("nope")):
            res = self.client.get("/api/song?artist=A&title=B")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.get_json())


if __name__ == "__main__":
    unittest.main()
