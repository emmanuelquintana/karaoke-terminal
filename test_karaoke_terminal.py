import io
import os
import tempfile
import unittest
from unittest.mock import patch

from karaoke_terminal import (
    AudioOptions,
    AudioPlaybackError,
    RenderState,
    TrackInfo,
    audio_cache_path,
    build_emoji_pack,
    estimate_timed_lyrics,
    fit_line,
    parse_lrc,
    prepare_audio_player,
    render_frame,
    slugify_filename,
    timeline_from_text,
    LyricLine,
    visible_len,
)


class KaraokeTerminalTests(unittest.TestCase):
    def test_parse_lrc_supports_centiseconds(self) -> None:
        lines = parse_lrc("[00:01.25]hola\n[00:03.00]mundo")
        self.assertEqual(len(lines), 2)
        self.assertAlmostEqual(lines[0].timestamp, 1.25, places=2)
        self.assertEqual(lines[1].text, "mundo")

    def test_estimate_timed_lyrics_builds_monotonic_timeline(self) -> None:
        lines = estimate_timed_lyrics("uno dos\n\nesta es otra linea")
        self.assertEqual(len(lines), 2)
        self.assertGreater(lines[1].timestamp, lines[0].timestamp)

    def test_emoji_pack_uses_keyword_rules(self) -> None:
        emojis = build_emoji_pack("love in the night", 0)
        self.assertIn("❤️", emojis)

    def test_timeline_from_text_uses_lrc_when_available(self) -> None:
        lines, mode = timeline_from_text("[00:01.00]hola")
        self.assertEqual(mode, "manual sincronizado")
        self.assertEqual(lines[0].text, "hola")

    def test_render_frame_updates_in_place_without_full_clear(self) -> None:
        buffer = io.StringIO()
        track = TrackInfo(artist="Test", title="Song")
        lines = [LyricLine(0.0, "hola"), LyricLine(2.0, "mundo")]
        with patch("sys.stdout", buffer):
            render_frame(track, lines, 0, 0.5, "sincronizado", 2.0, RenderState())
        output = buffer.getvalue()
        self.assertIn("\033[H", output)
        self.assertNotIn("\033[2J", output)

    def test_visible_length_counts_emoji_as_double_width(self) -> None:
        self.assertEqual(visible_len("🎵a"), 3)

    def test_fit_line_truncates_wide_text_safely(self) -> None:
        self.assertEqual(fit_line("🎵abcd", 4), "🎵a…")

    def test_slugify_filename_normalizes_text(self) -> None:
        self.assertEqual(slugify_filename("Enjambre / Dulce Soledad"), "enjambre-dulce-soledad")

    def test_audio_cache_path_ends_as_mp3(self) -> None:
        path = audio_cache_path("Enjambre", "Dulce Soledad")
        self.assertTrue(path.endswith(".mp3"))

    def test_prepare_audio_player_uses_local_file_when_present(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
            temp_path = handle.name
        try:
            player = prepare_audio_player(
                TrackInfo(artist="A", title="B"),
                AudioOptions(enabled=False, local_file=temp_path, volume=0.5),
            )
            self.assertIsNotNone(player)
            self.assertEqual(player.audio_path, temp_path)
        finally:
            os.remove(temp_path)

    def test_prepare_audio_player_fails_for_missing_local_file(self) -> None:
        with self.assertRaises(AudioPlaybackError):
            prepare_audio_player(
                TrackInfo(artist="A", title="B"),
                AudioOptions(enabled=False, local_file="C:/no/existe.mp3"),
            )


if __name__ == "__main__":
    unittest.main()
