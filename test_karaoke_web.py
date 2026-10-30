import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_plain_lyrics_use_duration_aware_estimate(self) -> None:
        track = TrackInfo(artist="A", title="B", duration=180.0)
        plain = "\n".join([f"linea {i}" for i in range(12)])
        with patch.object(engine, "search_track", return_value=(track, "", plain)), \
                patch.object(karaoke_web, "fetch_cover_art", return_value=None):
            payload = karaoke_web.resolve_for_web("A", "B")
        self.assertEqual(payload["mode"], "estimado")
        self.assertGreater(payload["lines"][0]["time"], 5.0)

    def test_plain_lyrics_keep_natural_line_pacing(self) -> None:
        track = TrackInfo(artist="Odisseo", title="Dos Extraños", duration=208.0)
        plain = (
            "Cada cuál por su lado sin volver a hablarse\n"
            "Ningún intento para poder frecuentarse\n"
            "Quedó prohibido recordar lo electrizante"
        )
        with patch.object(engine, "search_track", return_value=(track, "", plain)), \
                patch.object(karaoke_web, "fetch_cover_art", return_value=None):
            payload = karaoke_web.resolve_for_web("Odisseo", "Dos Extraños")
        first = payload["lines"][0]["time"]
        second = payload["lines"][1]["time"]
        third = payload["lines"][2]["time"]
        self.assertGreater(first, 10.0)
        self.assertLess(second - first, 7.0)
        self.assertLess(third - second, 4.0)


class StudioSubtitleTests(unittest.TestCase):
    def test_export_cleans_only_its_intermediates_on_success_and_failure(self) -> None:
        for failure in (None, "overlay", "ffmpeg"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "video.mp4"
                source.write_bytes(b"source")
                unrelated = root / "segment-other-000.mp4"
                unrelated.write_bytes(b"other export")
                export_id = "a" * 12
                session = {"videoPath": str(source), "video": {"duration": 4}, "song": {"lines": [{"time": 0, "text": "hola"}]}}

                def render(*args, **kwargs):
                    caption = root / f"caption-{export_id}-000.png"
                    mask = root / f"caption-mask-{export_id}-000.png"
                    caption.write_bytes(b"caption")
                    mask.write_bytes(b"mask")
                    if failure == "overlay":
                        raise RuntimeError("overlay failed")
                    return [(caption, mask, 0.0, 2.0)]

                def encode(command, **kwargs):
                    Path(command[-1]).write_bytes(b"encoded")
                    if failure == "ffmpeg":
                        raise RuntimeError("ffmpeg failed")

                with patch.object(karaoke_web, "STUDIO_CACHE_DIR", root), \
                        patch.object(karaoke_web, "_studio_session", return_value=session), \
                        patch.object(karaoke_web, "_ffmpeg_exe", return_value="ffmpeg"), \
                        patch.object(karaoke_web.uuid, "uuid4", return_value=SimpleNamespace(hex="a" * 32)), \
                        patch.object(karaoke_web, "render_subtitle_overlay_images", side_effect=render), \
                        patch.object(karaoke_web, "_run_export_command", side_effect=encode), \
                        patch.object(karaoke_web.studio_store, "save_export") as save:
                    if failure:
                        with self.assertRaises(RuntimeError):
                            karaoke_web.export_studio_clip("session", {"length": 2})
                        save.assert_not_called()
                    else:
                        _, final = karaoke_web.export_studio_clip("session", {"length": 2})
                        self.assertTrue(final.exists())
                        save.assert_called_once()
                expected = {source, unrelated}
                if not failure:
                    expected.add(root / f"tiktok-studio-{export_id}.mp4")
                self.assertEqual(set(root.iterdir()), expected)

    def test_build_ass_subtitles_applies_clip_start_and_offset(self) -> None:
        ass = karaoke_web.build_ass_subtitles(
            [{"time": 10.0, "text": "hola"}, {"time": 12.0, "text": "adios"}],
            start=11.0,
            length=4.0,
            offset=1.0,
            width=1080,
            height=1920,
            font="Inter",
            size=58,
            position="bottom",
            color="white",
            style="boxed",
        )
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:02.00", ass)
        self.assertIn("hola", ass)

    def test_build_ass_subtitles_respects_explicit_line_end(self) -> None:
        ass = karaoke_web.build_ass_subtitles(
            [
                {"time": 10.0, "end": 12.0, "text": "hola"},
                {"time": 20.0, "end": 22.0, "text": "adios"},
            ],
            start=0.0,
            length=25.0,
            offset=0.0,
            width=1080,
            height=1920,
            font="Inter",
            size=58,
            position="bottom",
            color="white",
            style="boxed",
        )
        self.assertIn("Dialogue: 0,0:00:10.00,0:00:12.00", ass)
        self.assertIn("Dialogue: 0,0:00:20.00,0:00:22.00", ass)

    def test_scaled_subtitle_size_matches_preview_canvas_ratio(self) -> None:
        size = karaoke_web.scaled_subtitle_size(
            33,
            1080,
            1920,
            "vertical",
            {"frameWidth": 384.0, "frameHeight": 682.67},
        )
        self.assertEqual(size, 93)

    def test_scaled_subtitle_margins_use_preview_position(self) -> None:
        margin_h, margin_v = karaoke_web.scaled_subtitle_margins(
            width=1080,
            height=1920,
            layout="vertical",
            position="bottom",
            preview={"frameWidth": 384.0, "frameHeight": 682.67, "captionWidth": 348.0, "captionBottom": 61.44},
        )
        self.assertEqual(margin_h, 51)
        self.assertAlmostEqual(margin_v, 173, delta=1)

    def test_export_timeline_segments_keep_memory_low(self) -> None:
        segments = karaoke_web.timeline_segments_for_export([
            {"start": 1.0, "end": 2.0, "text": "uno"},
            {"start": 4.0, "end": 5.0, "text": "dos"},
        ], 6.0)
        self.assertEqual(
            [(round(s["start"], 1), round(s["end"], 1), bool(s["overlay"])) for s in segments],
            [
                (0.0, 1.0, False),
                (1.0, 2.0, True),
                (2.0, 4.0, False),
                (4.0, 5.0, True),
                (5.0, 6.0, False),
            ],
        )

    def test_find_audio_offset_detects_positive_lag(self) -> None:
        reference = [0.0, 1.0, -0.4, 0.7, -0.2, 0.3, 0.9, -0.8] * 5
        video = [0.05, -0.02, 0.03, 0.01, -0.04] + reference + [0.1, -0.1]
        result = karaoke_web.find_audio_offset(
            reference,
            video,
            0.5,
            min_offset=-3.0,
            max_offset=5.0,
            min_overlap_seconds=4.0,
        )
        self.assertAlmostEqual(result["offset"], 2.5, places=1)
        self.assertGreater(result["confidence"], 0.5)

    def test_estimated_lyric_correction_shifts_old_zero_based_lines(self) -> None:
        song = {
            "mode": "estimado",
            "duration": 180.0,
            "lines": [{"time": 0.0, "text": "primera linea"} for _ in range(12)],
        }
        self.assertGreater(karaoke_web.estimated_lyric_correction(song), 5.0)

    def test_estimated_lyric_correction_is_zero_when_lines_already_have_lead_in(self) -> None:
        lead = karaoke_web.estimated_plain_lead_in(180.0, 12)
        song = {
            "mode": "estimado",
            "duration": 180.0,
            "lines": [{"time": lead, "text": "primera linea"} for _ in range(12)],
        }
        self.assertEqual(karaoke_web.estimated_lyric_correction(song), 0.0)

    def test_align_lyrics_to_timed_text_uses_caption_times(self) -> None:
        lines = [
            {"time": 18.7, "text": "Cada cuál por su lado sin volver a hablarse"},
            {"time": 22.5, "text": "Ningún intento para poder frecuentarse"},
            {"time": 24.6, "text": "Quedó prohibido recordar lo electrizante"},
        ]
        events = [
            {"start": 20.0, "end": 23.0, "text": "cada cual por su lado sin volver a hablarse"},
            {"start": 27.0, "end": 30.0, "text": "ningun intento para poder frecuentarse"},
            {"start": 34.0, "end": 37.0, "text": "quedo prohibido recordar lo electrizante"},
        ]
        aligned, confidence = karaoke_web.align_lyrics_to_timed_text(lines, events)
        self.assertGreater(confidence, 0.8)
        self.assertEqual([line["time"] for line in aligned], [20.0, 27.0, 34.0])

    def test_align_lyrics_distributes_multi_line_asr_segment(self) -> None:
        lines = [
            {"time": 18.7, "text": "Cada cuál por su lado sin volver a hablarse"},
            {"time": 24.2, "text": "Ningún intento para poder frecuentarse"},
            {"time": 27.2, "text": "Quedó prohibido recordar lo electrizante"},
        ]
        events = [
            {
                "start": 0.0,
                "end": 29.2,
                "text": "Cada cual por su lado sin volver a hablarse Ningún intento para poder frecuentarse",
            },
            {
                "start": 29.2,
                "end": 37.8,
                "text": "Quedo prohibido recordar lo electrizante",
            },
        ]
        aligned, confidence = karaoke_web.align_lyrics_to_timed_text(lines, events)
        self.assertGreater(confidence, 0.4)
        self.assertAlmostEqual(aligned[0]["time"], 18.7, delta=0.2)
        self.assertGreater(aligned[1]["time"], aligned[0]["time"] + 2.0)
        self.assertAlmostEqual(aligned[2]["time"], 29.2, delta=0.2)

    def test_align_lyrics_uses_asr_word_times_and_leaves_instrumental_gap(self) -> None:
        lines = [
            {"time": 47.4, "text": "Son dos extraños sin ganas de volverse a ver"},
            {"time": 67.8, "text": "Un gesto amable por si se ven"},
        ]
        events = [
            {
                "start": 47.0,
                "end": 58.0,
                "text": "Son dos extraños sin ganas de volverse a ver",
                "words": [
                    {"start": 47.2, "end": 47.8, "word": "Son", "probability": 0.9},
                    {"start": 47.8, "end": 48.2, "word": "dos", "probability": 0.9},
                    {"start": 48.2, "end": 49.0, "word": "extraños", "probability": 0.9},
                    {"start": 49.0, "end": 49.5, "word": "sin", "probability": 0.9},
                    {"start": 49.5, "end": 50.0, "word": "ganas", "probability": 0.9},
                    {"start": 50.0, "end": 50.4, "word": "de", "probability": 0.9},
                    {"start": 50.4, "end": 51.1, "word": "volverse", "probability": 0.9},
                    {"start": 51.1, "end": 51.5, "word": "a", "probability": 0.9},
                    {"start": 51.5, "end": 52.1, "word": "ver", "probability": 0.9},
                ],
            },
            {
                "start": 67.8,
                "end": 90.0,
                "text": "Un gesto amable por si se ven",
                "words": [
                    {"start": 81.3, "end": 82.2, "word": "Un", "probability": 0.8},
                    {"start": 82.2, "end": 82.7, "word": "gesto", "probability": 0.99},
                    {"start": 82.7, "end": 83.3, "word": "amable", "probability": 0.9},
                    {"start": 83.3, "end": 83.7, "word": "por", "probability": 0.9},
                    {"start": 83.7, "end": 84.0, "word": "si", "probability": 0.9},
                    {"start": 84.0, "end": 84.3, "word": "se", "probability": 0.9},
                    {"start": 84.3, "end": 84.8, "word": "ven", "probability": 0.9},
                ],
            },
        ]
        aligned, confidence = karaoke_web.align_lyrics_to_timed_text(lines, events)
        self.assertGreater(confidence, 0.4)
        self.assertLess(aligned[0]["end"], 53.0)
        self.assertAlmostEqual(aligned[1]["time"], 81.3, delta=0.1)

    def test_align_lyrics_right_aligns_long_segment_after_gap(self) -> None:
        lines = [
            {"time": 47.4, "text": "Son dos extraños sin ganas de volverse a ver"},
            {"time": 67.8, "text": "Un gesto amable por si se ven"},
        ]
        events = [
            {"start": 47.0, "end": 58.0, "text": "Son dos extraños sin ganas de volverse a ver"},
            {"start": 67.8, "end": 90.0, "text": "Un gesto amable por si se ven"},
        ]
        aligned, confidence = karaoke_web.align_lyrics_to_timed_text(lines, events)
        self.assertGreater(confidence, 0.4)
        self.assertLess(aligned[0]["end"], 53.5)
        self.assertGreater(aligned[1]["time"], 82.0)


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        karaoke_web.STUDIO_SESSIONS.clear()
        karaoke_web.STUDIO_EXPORTS.clear()
        self.client = karaoke_web.app.test_client()

    def test_invalid_text_fields_are_rejected_before_backend_work(self) -> None:
        with patch.object(karaoke_web, "resolve_for_web") as lookup:
            for name in ("video", "artist", "title"):
                for value in (123, ["A"], {"value": "A"}):
                    payload = {"video": "video", "artist": "A", "title": "B", name: value}
                    self.assertEqual(self.client.post("/api/v1/studio-sessions", json=payload).status_code, 400)
            lookup.assert_not_called()
        for path in ("/api/studio/sync", "/api/studio/export"):
            self.assertEqual(self.client.post(path, json={"sessionId": 123}).status_code, 400)

    def test_invalid_subtitle_types_are_rejected_before_export(self) -> None:
        with patch.object(karaoke_web, "export_studio_clip") as export:
            for subtitle in ([], "wrong", {"font": []}, {"color": {}}):
                res = self.client.post("/api/v1/studio-sessions/id/exports", json={"subtitle": subtitle})
                self.assertEqual(res.status_code, 400)
            export.assert_not_called()

    def test_request_limit_returns_json_with_cors(self) -> None:
        origin = "https://karaoke.vercel.app"
        with patch.dict(karaoke_web.app.config, {"FRONTEND_ORIGINS": {origin}}), patch.object(karaoke_web, "resolve_for_web") as lookup:
            res = self.client.post("/api/v1/studio-sessions", json={"video": "x" * 65536}, headers={"Origin": origin})
            self.assertEqual(res.status_code, 413)
            self.assertEqual(self.envelope(res)["code"], "HX_BO_413")
            self.assertEqual(res.headers["Access-Control-Allow-Origin"], origin)
            lookup.assert_not_called()

    def test_internal_exception_details_stay_in_logs(self) -> None:
        with patch.object(karaoke_web, "resolve_for_web", side_effect=RuntimeError("private-path-marker")), patch.object(karaoke_web.app.logger, "exception") as log:
            res = self.client.get("/api/v1/songs?artist=A&title=B")
            self.assertEqual(res.status_code, 500)
            self.assertNotIn("private-path-marker", res.get_data(as_text=True))
            log.assert_called_once()

    def test_health_works_without_media_or_external_requests(self) -> None:
        res = self.client.get("/api/v1/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.envelope(res)["data"], {"status": "ok"})

    def test_cors_preflight_and_errors_for_exact_frontend_origins(self) -> None:
        origin = "https://karaoke.vercel.app"
        with patch.dict(karaoke_web.app.config, {"FRONTEND_ORIGINS": {origin}}):
            res = self.client.options("/api/v1/studio-sessions", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            })
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers["Access-Control-Allow-Origin"], origin)
            self.assertIn("Content-Type", res.headers["Access-Control-Allow-Headers"])
            res = self.client.get("/api/v1/songs", headers={"Origin": origin})
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.headers["Access-Control-Allow-Origin"], origin)
            self.assertIn("Origin", res.headers["Vary"])
            for untrusted in ["https://evil.vercel.app", origin + ".evil.com", "null"]:
                res = self.client.get("/api/v1/health", headers={"Origin": untrusted})
                self.assertNotIn("Access-Control-Allow-Origin", res.headers)

    def test_media_range_and_exports_survive_empty_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "clip.mp4"
            media.write_bytes(b"0123456789" * 100)
            with patch.object(karaoke_web.studio_store, "load_session", return_value={"videoPath": str(media)}):
                res = self.client.get("/api/v1/studio-sessions/id/video", headers={"Range": "bytes=100-199"})
                self.assertEqual(res.status_code, 206)
                self.assertEqual(res.headers["Content-Range"], "bytes 100-199/1000")
                self.assertEqual(res.data, b"0123456789" * 10)
                res.close()
            with patch.object(karaoke_web.studio_store, "load_export", return_value=media):
                res = self.client.get("/api/v1/studio-exports/id/file")
                self.assertEqual(res.status_code, 200)
                self.assertIn("attachment", res.headers["Content-Disposition"])
                res.close()

    def envelope(self, response):
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertIn("code", payload)
        self.assertIn("message", payload)
        self.assertIn("traceId", payload)
        self.assertIn("data", payload)
        self.assertEqual(payload["metadata"], {"page": 0, "size": 0, "elements": 0})
        return payload

    def test_index_and_static_served(self) -> None:
        for path in ("/", "/web/app.js"):
            with self.client.get(path) as res:
                self.assertEqual(res.status_code, 200)

    def test_openapi_served(self) -> None:
        res = self.client.get("/api/v1/docs/openapi.json")
        self.assertEqual(res.status_code, 200)
        spec = res.get_json()
        self.assertEqual(spec["openapi"], "3.0.3")
        self.assertIn("/songs", spec["paths"])
        self.assertIn("/studio-sessions", spec["paths"])

    def test_song_requires_params(self) -> None:
        res = self.client.get("/api/v1/songs")
        self.assertEqual(res.status_code, 400)
        payload = self.envelope(res)
        self.assertEqual(payload["code"], "HX_BO_400")

    def test_song_returns_payload(self) -> None:
        payload = {"title": "B", "artist": "A", "lines": [], "mode": "sincronizado"}
        with patch.object(karaoke_web, "resolve_for_web", return_value=payload):
            res = self.client.get("/api/v1/songs?artist=A&title=B", headers={"X-Trace-Id": "trace1234"})
        self.assertEqual(res.status_code, 200)
        body = self.envelope(res)
        self.assertEqual(body["code"], "HX_BO_001")
        self.assertEqual(body["traceId"], "trace1234")
        self.assertEqual(body["data"]["title"], "B")

    def test_cover_rejects_untrusted_host(self) -> None:
        res = self.client.get("/api/v1/covers?u=https://evil.example.com/x.jpg")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.envelope(res)["code"], "HX_BO_400")
        res2 = self.client.get("/api/v1/covers?u=http://127.0.0.1/secret")
        self.assertEqual(res2.status_code, 400)
        for host in ("evilapple.com", "evil-mzstatic.com"):
            self.assertEqual(self.client.get(f"/api/v1/covers?u=https://{host}/x.jpg").status_code, 400)

    def test_video_download_rejects_non_youtube_urls(self) -> None:
        for url in ("http://127.0.0.1/secret", "https://youtube.com.evil.com/video", "https://evil.example/video"):
            with self.assertRaisesRegex(engine.AudioPlaybackError, "URL HTTPS de YouTube"):
                karaoke_web.resolve_studio_video(url)

    def test_cover_allows_itunes_host(self) -> None:
        with patch("urllib.request.urlopen") as fake:
            fake.return_value.__enter__.return_value.read.return_value = b"img"
            fake.return_value.__enter__.return_value.headers = {"Content-Type": "image/jpeg"}
            res = self.client.get("/api/v1/covers?u=https://is1-ssl.mzstatic.com/a/1000x1000bb.jpg")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "image/jpeg")

    def test_song_404_when_not_found(self) -> None:
        with patch.object(karaoke_web, "resolve_for_web", side_effect=engine.LyricsLookupError("nope")):
            res = self.client.get("/api/v1/songs?artist=A&title=B")
        self.assertEqual(res.status_code, 404)
        payload = self.envelope(res)
        self.assertEqual(payload["code"], "HX_BO_404")
        self.assertIn("nope", payload["message"])

    def test_studio_prepare_requires_payload(self) -> None:
        res = self.client.post("/api/v1/studio-sessions", json={})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.envelope(res)["code"], "HX_BO_400")

    def test_studio_prepare_returns_session(self) -> None:
        song = {"title": "B", "artist": "A", "lines": [{"time": 0.0, "text": "hola"}]}
        video = {"title": "Video", "duration": 180.0}
        with patch.object(karaoke_web, "resolve_for_web", return_value=song), \
                patch.object(karaoke_web, "resolve_studio_video", return_value=(Path("video.mp4"), video)):
            res = self.client.post(
                "/api/v1/studio-sessions",
                json={"video": "video oficial", "artist": "A", "title": "B"},
            )
        self.assertEqual(res.status_code, 201)
        body = self.envelope(res)
        self.assertEqual(body["code"], "HX_BO_002")
        data = body["data"]
        self.assertIn("sessionId", data)
        self.assertIn("/api/v1/studio-sessions/", data["videoUrl"])

    def test_studio_export_returns_download_url(self) -> None:
        with patch.object(karaoke_web, "export_studio_clip", return_value=("abc123", Path("clip.mp4"))):
            res = self.client.post("/api/v1/studio-sessions/session/exports", json={})
        self.assertEqual(res.status_code, 201)
        body = self.envelope(res)
        self.assertEqual(body["code"], "HX_BO_004")
        self.assertEqual(body["data"]["downloadUrl"], "/api/v1/studio-exports/abc123/file")

    def test_studio_sync_returns_offset(self) -> None:
        with patch.object(karaoke_web, "auto_sync_studio_audio", return_value={"offset": 12.4, "confidence": 0.87}):
            res = self.client.post("/api/v1/studio-sessions/session/sync", json={})
        self.assertEqual(res.status_code, 200)
        body = self.envelope(res)
        self.assertEqual(body["code"], "HX_BO_003")
        self.assertEqual(body["data"]["offset"], 12.4)

    def test_studio_sync_requires_session(self) -> None:
        res = self.client.post("/api/studio/sync", json={})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.envelope(res)["code"], "HX_BO_400")


if __name__ == "__main__":
    unittest.main()
