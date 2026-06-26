#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import sys
import textwrap
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


APP_NAME = "Terminal Karaoke"
USER_AGENT = "terminal-karaoke/1.0 (+https://lrclib.net)"
DEFAULT_EMOJIS = ["🎵", "🎶", "✨", "🌟", "🎤", "🪩", "💫", "🔥"]
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LRC_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".karaoke_cache.json")
AUDIO_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".audio_cache")
ELLIPSIS = "…"
ASCII_FIGLET_FONT = "standard"
ASCII_REVEAL_PORTION = 0.4
ASCII_ART_HEIGHT = 5
ASCII_FONT: dict[str, tuple[str, ...]] = {
    "A": (" ### ", "#   #", "#####", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#### ", "#   #", "#### "),
    "C": (" ####", "#    ", "#    ", "#    ", " ####"),
    "D": ("#### ", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#### ", "#    ", "#####"),
    "F": ("#####", "#    ", "#### ", "#    ", "#    "),
    "G": (" ####", "#    ", "#  ##", "#   #", " ####"),
    "H": ("#   #", "#   #", "#####", "#   #", "#   #"),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "#####"),
    "J": ("#####", "   # ", "   # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "###  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#### ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "# # #", "#  ##", " ####"),
    "R": ("#### ", "#   #", "#### ", "#  # ", "#   #"),
    "S": (" ####", "#    ", " ### ", "    #", "#### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "# # #", "## ##", "#   #"),
    "X": ("#   #", " # # ", "  #  ", " # # ", "#   #"),
    "Y": ("#   #", " # # ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "   # ", "  #  ", " #   ", "#####"),
    "0": (" ### ", "#  ##", "# # #", "##  #", " ### "),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", "#####"),
    "2": (" ### ", "#   #", "   # ", "  #  ", "#####"),
    "3": ("#### ", "    #", " ### ", "    #", "#### "),
    "4": ("#   #", "#   #", "#####", "    #", "    #"),
    "5": ("#####", "#    ", "#### ", "    #", "#### "),
    "6": (" ####", "#    ", "#### ", "#   #", " ### "),
    "7": ("#####", "   # ", "  #  ", " #   ", "#    "),
    "8": (" ### ", "#   #", " ### ", "#   #", " ### "),
    "9": (" ### ", "#   #", " ####", "    #", "#### "),
    " ": ("   ", "   ", "   ", "   ", "   "),
    "!": ("  #  ", "  #  ", "  #  ", "     ", "  #  "),
    "?": (" ### ", "#   #", "   # ", "     ", "  #  "),
    ".": ("     ", "     ", "     ", "     ", "  #  "),
    ",": ("     ", "     ", "     ", "  #  ", " #   "),
    "'": ("  #  ", "  #  ", "     ", "     ", "     "),
    "-": ("     ", "     ", "#####", "     ", "     "),
    "/": ("    #", "   # ", "  #  ", " #   ", "#    "),
    "&": (" ##  ", "#  # ", " ##  ", "#  # ", " ## #"),
}
ASCII_FALLBACK_GLYPH = (" ### ", "#   #", "   # ", "     ", "  #  ")
EMOJI_RULES = [
    ({"amor", "love", "heart", "corazon", "kiss", "beso"}, ["❤️", "💘", "🥰"]),
    ({"baila", "dance", "dancing", "party", "fiesta", "club"}, ["💃", "🕺", "🎉"]),
    ({"sad", "cry", "llorar", "tears", "alone", "sola", "solo"}, ["😢", "💧", "🌧️"]),
    ({"fire", "burn", "calor", "fuego", "flame"}, ["🔥", "⚡", "🧨"]),
    ({"night", "moon", "luna", "stars", "star", "cielo"}, ["🌙", "🌌", "⭐"]),
    ({"sun", "sol", "shine", "bright", "light", "luz"}, ["☀️", "✨", "🌞"]),
    ({"road", "car", "drive", "viaje", "correr", "run"}, ["🚗", "🛣️", "💨"]),
    ({"dream", "sueño", "fly", "volar", "sky"}, ["🪽", "🌠", "☁️"]),
]

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import yt_dlp
except ImportError:  # pragma: no cover
    yt_dlp = None

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover
    imageio_ffmpeg = None

try:
    import pyfiglet
except ImportError:  # pragma: no cover
    pyfiglet = None

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None


class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


@dataclass
class TrackInfo:
    artist: str
    title: str
    album: str = ""
    duration: Optional[float] = None


@dataclass
class LyricLine:
    timestamp: float
    text: str


@dataclass
class RenderState:
    previous_line_count: int = 0


@dataclass
class AudioOptions:
    enabled: bool = False
    local_file: Optional[str] = None
    volume: float = 0.75


class LyricsLookupError(RuntimeError):
    pass


class AudioPlaybackError(RuntimeError):
    pass


def enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.SetConsoleOutputCP(65001)
    kernel32.SetConsoleCP(65001)
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def char_display_width(char: str) -> int:
    codepoint = ord(char)
    if unicodedata.combining(char) or codepoint in {0x200D, 0xFE0E, 0xFE0F}:
        return 0
    if (
        0x1F300 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or unicodedata.east_asian_width(char) in {"W", "F"}
    ):
        return 2
    return 1


def visible_len(value: str) -> int:
    return sum(char_display_width(char) for char in strip_ansi(value))


def trim_to_width(value: str, width: int) -> str:
    if width <= 0:
        return ""
    result: list[str] = []
    current_width = 0
    for char in value:
        char_width = char_display_width(char)
        if current_width + char_width > width:
            break
        result.append(char)
        current_width += char_width
    return "".join(result)


def center_text(value: str, width: int) -> str:
    padding = max(0, (width - visible_len(value)) // 2)
    return " " * padding + value


def fit_line(value: str, width: int) -> str:
    plain = strip_ansi(value)
    if visible_len(plain) <= width:
        return value
    if width <= 1:
        return trim_to_width(plain, width)
    trimmed = trim_to_width(plain, max(1, width - char_display_width(ELLIPSIS)))
    return trimmed + ELLIPSIS


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.casefold()


def ascii_safe_text(value: str) -> str:
    replacements = {
        "¿": "",
        "¡": "",
        "…": "...",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    cleaned = "".join(replacements.get(char, char) for char in without_marks)
    ascii_only = "".join(char if 32 <= ord(char) <= 126 else " " for char in cleaned)
    return re.sub(r"\s+", " ", ascii_only).strip() or "*"


def ascii_glyph(char: str) -> tuple[str, ...]:
    replacements = {"¿": "?", "¡": "!", "…": ".", "–": "-", "—": "-"}
    normalized = replacements.get(char, normalize_text(char).upper())
    if not normalized or normalized.isspace():
        return ASCII_FONT[" "]
    return ASCII_FONT.get(normalized[0], ASCII_FALLBACK_GLYPH)


def pad_ascii_rows(rows: list[str]) -> list[str]:
    max_width = max((len(row) for row in rows), default=0)
    return [row.ljust(max_width) for row in rows]


def build_ascii_block(text: str, width: Optional[int] = None) -> list[str]:
    safe_text = ascii_safe_text(text)
    if pyfiglet is not None:
        try:
            rendered = pyfiglet.figlet_format(
                safe_text,
                font=ASCII_FIGLET_FONT,
                width=max(24, width or 80),
            )
            return pad_ascii_rows([row.rstrip() for row in rendered.rstrip("\n").splitlines()])
        except Exception:  # pragma: no cover
            pass

    rows = [""] * ASCII_ART_HEIGHT
    for char in safe_text:
        glyph = ascii_glyph(char)
        for row_index, row in enumerate(glyph):
            rows[row_index] += row + " "
    return pad_ascii_rows([row.rstrip() for row in rows])


def reveal_ascii_block(rows: list[str], progress: float) -> list[str]:
    progress = min(1.0, max(0.0, progress))
    if progress == 0.0:
        visible_rows = 0
    elif progress >= 1.0:
        visible_rows = len(rows)
    else:
        visible_rows = max(1, int(len(rows) * progress))
    revealed_rows: list[str] = []
    for row_index, row in enumerate(rows):
        revealed_rows.append(row if row_index < visible_rows else " " * len(row))
    return revealed_rows


def slugify_filename(value: str) -> str:
    cleaned = normalize_text(value)
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned or "audio"


def format_seconds(value: float) -> str:
    total_seconds = max(0, int(value))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def api_get(endpoint: str, params: dict[str, str]) -> dict | list:
    query = urllib.parse.urlencode(params)
    url = f"https://lrclib.net{endpoint}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def load_cache() -> dict[str, dict]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache: dict[str, dict]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def track_cache_key(artist: str, title: str) -> str:
    return f"{normalize_text(artist)}::{normalize_text(title)}"


def cache_result(track: TrackInfo, synced: str, plain: str) -> None:
    cache = load_cache()
    cache[track_cache_key(track.artist, track.title)] = {
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "duration": track.duration,
        "syncedLyrics": synced,
        "plainLyrics": plain,
    }
    save_cache(cache)


def cached_track(artist: str, title: str) -> Optional[tuple[TrackInfo, str, str]]:
    payload = load_cache().get(track_cache_key(artist, title))
    if not payload:
        return None
    return (
        TrackInfo(
            artist=payload.get("artist", artist),
            title=payload.get("title", title),
            album=payload.get("album", ""),
            duration=float(payload["duration"]) if payload.get("duration") else None,
        ),
        payload.get("syncedLyrics", ""),
        payload.get("plainLyrics", ""),
    )


def result_to_track(result: dict, fallback_artist: str, fallback_title: str) -> tuple[TrackInfo, str, str]:
    track = TrackInfo(
        artist=result.get("artistName", fallback_artist),
        title=result.get("trackName", fallback_title),
        album=result.get("albumName", ""),
        duration=float(result["duration"]) if result.get("duration") else None,
    )
    synced = result.get("syncedLyrics") or ""
    plain = result.get("plainLyrics") or ""
    cache_result(track, synced, plain)
    return track, synced, plain


def score_candidate(candidate: dict, artist: str, title: str) -> tuple[int, int]:
    wanted_artist = normalize_text(artist)
    wanted_title = normalize_text(title)
    found_artist = normalize_text(candidate.get("artistName", ""))
    found_title = normalize_text(candidate.get("trackName", ""))
    score = 0
    if found_artist == wanted_artist:
        score += 7
    elif wanted_artist and wanted_artist in found_artist:
        score += 3
    if found_title == wanted_title:
        score += 9
    elif wanted_title and wanted_title in found_title:
        score += 4
    if candidate.get("syncedLyrics"):
        score += 2
    if candidate.get("plainLyrics"):
        score += 1
    name_delta = abs(len(found_title) - len(wanted_title))
    return score, -name_delta


def search_track(artist: str, title: str) -> tuple[TrackInfo, str, str]:
    cached = cached_track(artist, title)
    if cached and (cached[1] or cached[2]):
        return cached

    errors: List[str] = []
    try:
        result = api_get("/api/get", {"artist_name": artist, "track_name": title})
        if isinstance(result, dict):
            synced = result.get("syncedLyrics") or ""
            plain = result.get("plainLyrics") or ""
            if synced or plain:
                return result_to_track(result, artist, title)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            errors.append(f"HTTP {exc.code}")
    except urllib.error.URLError as exc:
        errors.append(str(exc.reason))

    try:
        results = api_get("/api/search", {"artist_name": artist, "track_name": title})
    except urllib.error.URLError as exc:
        errors.append(str(exc.reason))
        raise LyricsLookupError(
            "No pude conectarme a LRCLIB para descargar la letra."
        ) from exc
    except urllib.error.HTTPError as exc:
        errors.append(f"HTTP {exc.code}")
        raise LyricsLookupError(
            "El servicio de letras respondió con error mientras buscaba la canción."
        ) from exc

    if not isinstance(results, list) or not results:
        details = f" Detalle: {', '.join(errors)}." if errors else ""
        raise LyricsLookupError(
            f"No encontré coincidencias para '{title}' de '{artist}'.{details}"
        )

    best = sorted(results, key=lambda item: score_candidate(item, artist, title), reverse=True)[0]
    synced = best.get("syncedLyrics") or ""
    plain = best.get("plainLyrics") or ""
    if not synced and not plain:
        raise LyricsLookupError("Encontré la canción, pero no trae letra disponible.")
    return result_to_track(best, artist, title)


def parse_lrc(raw_lyrics: str) -> list[LyricLine]:
    parsed: list[LyricLine] = []
    for raw_line in raw_lyrics.splitlines():
        matches = list(LRC_TIMESTAMP_RE.finditer(raw_line))
        if not matches:
            continue
        text = LRC_TIMESTAMP_RE.sub("", raw_line).strip() or "♪"
        for match in matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction = match.group(3) or "0"
            if len(fraction) == 1:
                millis = int(fraction) * 100
            elif len(fraction) == 2:
                millis = int(fraction) * 10
            else:
                millis = int(fraction[:3])
            timestamp = minutes * 60 + seconds + (millis / 1000)
            parsed.append(LyricLine(timestamp=timestamp, text=text))
    return sorted(parsed, key=lambda line: line.timestamp)


def estimate_timed_lyrics(raw_lyrics: str) -> list[LyricLine]:
    lines = [line.strip() for line in raw_lyrics.splitlines() if line.strip()]
    if not lines:
        return []

    parsed: list[LyricLine] = []
    cursor = 0.0
    for line in lines:
        parsed.append(LyricLine(timestamp=cursor, text=line))
        word_count = max(1, len(re.findall(r"[\w']+", line)))
        punctuation_bonus = 0.5 if any(mark in line for mark in ",.;:!?") else 0.0
        cursor += min(6.5, max(1.8, word_count * 0.42 + punctuation_bonus))
    return parsed


def timeline_from_text(raw_lyrics: str) -> tuple[list[LyricLine], str]:
    parsed_lrc = parse_lrc(raw_lyrics)
    if parsed_lrc:
        return parsed_lrc, "manual sincronizado"
    return estimate_timed_lyrics(raw_lyrics), "manual estimado"


def prompt_multiline_lyrics() -> str:
    print()
    print("No logré descargar la letra automáticamente.")
    print("Pégala manualmente y escribe FIN en una línea aparte para comenzar.")
    buffer: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "FIN":
            break
        buffer.append(line.rstrip("\n"))
    return "\n".join(buffer).strip()


def build_emoji_pack(text: str, index: int) -> str:
    normalized = normalize_text(text)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    found: list[str] = []
    for keywords, emojis in EMOJI_RULES:
        if tokens & keywords:
            found.extend(emojis[:2])
    if not found:
        found = [DEFAULT_EMOJIS[index % len(DEFAULT_EMOJIS)]]
    unique = []
    for emoji in found:
        if emoji not in unique:
            unique.append(emoji)
    return " ".join(unique[:2])


def wrap_line(line: str, width: int) -> list[str]:
    wrapped = textwrap.wrap(
        line,
        width=max(10, width),
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped or [""]


def ascii_art_lines(line: str, width: int, progress: float) -> list[str]:
    if pyfiglet is not None:
        return reveal_ascii_block(build_ascii_block(line, width), progress)

    max_chars = max(1, min(22, max(1, width - 2) // 5))
    chunks = textwrap.wrap(
        ascii_safe_text(line),
        width=max_chars,
        break_long_words=False,
        break_on_hyphens=False,
    )[:2]
    art_lines: list[str] = []
    for chunk_index, chunk in enumerate(chunks or ["*"]):
        if chunk_index:
            art_lines.append("")
        art_lines.extend(reveal_ascii_block(build_ascii_block(chunk), progress))
    return art_lines


def progress_bar(progress: float, width: int = 24) -> str:
    progress = min(1.0, max(0.0, progress))
    filled = int(progress * width)
    return f"[{'█' * filled}{'·' * (width - filled)}]"


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


def move_cursor_home() -> None:
    print("\033[H", end="")


def move_cursor_to(row: int, column: int = 1) -> None:
    print(f"\033[{row};{column}H", end="")


@contextmanager
def terminal_session() -> Iterable[None]:
    enable_windows_ansi()
    print("\033[?1049h\033[?25l", end="")
    clear_screen()
    try:
        yield
    finally:
        print(f"{Style.RESET}\033[?25h\033[?1049l", end="", flush=True)


def configure_console_streams() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except ValueError:
                pass


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[S/n]" if default else "[s/N]"
    while True:
        value = input(f"{prompt} {suffix}: ").strip().lower()
        if not value:
            return default
        if value in {"s", "si", "sí", "y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Responde con s o n.")


def ensure_audio_cache_dir() -> None:
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)


def audio_cache_path(artist: str, title: str) -> str:
    key = hashlib.sha1(f"{normalize_text(artist)}::{normalize_text(title)}".encode("utf-8")).hexdigest()[:10]
    base = f"{slugify_filename(artist)}-{slugify_filename(title)}-{key}"
    return os.path.join(AUDIO_CACHE_DIR, f"{base}.mp3")


def download_audio_track(artist: str, title: str) -> str:
    if yt_dlp is None or imageio_ffmpeg is None:
        raise AudioPlaybackError(
            "Falta soporte de descarga de audio. Instala `yt-dlp` e `imageio-ffmpeg`."
        )

    ensure_audio_cache_dir()
    target_mp3 = audio_cache_path(artist, title)
    if os.path.exists(target_mp3):
        return target_mp3

    output_template = str(Path(target_mp3).with_suffix(".%(ext)s"))
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    query = f"ytsearch1:{artist} {title} audio"
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio[acodec*=mp4a]/bestaudio/best",
        "default_search": "ytsearch1",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": output_template,
        "ffmpeg_location": ffmpeg_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([query])
    except Exception as exc:  # pragma: no cover
        raise AudioPlaybackError(f"No pude descargar el audio para '{title}' de '{artist}': {exc}") from exc

    if not os.path.exists(target_mp3):
        raise AudioPlaybackError("La descarga terminó, pero no encontré el archivo MP3 final.")
    return target_mp3


class PygameAudioPlayer:
    def __init__(self, audio_path: str, volume: float = 0.75) -> None:
        self.audio_path = audio_path
        self.volume = max(0.0, min(1.0, volume))
        self._initialized_here = False

    def start(self) -> None:
        if pygame is None:
            raise AudioPlaybackError("Falta soporte de reproducción. Instala `pygame`.")
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                self._initialized_here = True
            pygame.mixer.music.load(self.audio_path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
        except Exception as exc:  # pragma: no cover
            raise AudioPlaybackError(f"No pude reproducir el audio descargado: {exc}") from exc

    def stop(self) -> None:
        if pygame is None or not pygame.mixer.get_init():
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass
        if self._initialized_here:
            try:
                pygame.mixer.quit()
            except Exception:
                pass


def build_frame_lines(
    track: TrackInfo,
    lines: list[LyricLine],
    index: int,
    elapsed: float,
    mode: str,
    next_timestamp: float,
    ascii_lyrics: bool = False,
) -> tuple[int, list[str]]:
    width = shutil.get_terminal_size((96, 30)).columns
    frame_lines: list[str] = []

    title = f"{Style.BOLD}{Style.CYAN}🎧 {track.title} - {track.artist}{Style.RESET}"
    subtitle_bits = [f"Modo: {mode}", f"Tiempo: {format_seconds(elapsed)}"]
    if ascii_lyrics:
        subtitle_bits.append("Visual: ASCII")
    if track.album:
        subtitle_bits.append(f"Álbum: {track.album}")
    subtitle = f"{Style.GRAY}{'   |   '.join(subtitle_bits)}{Style.RESET}"
    frame_lines.append(center_text(fit_line(title, width), width))
    frame_lines.append(center_text(fit_line(subtitle, width), width))
    frame_lines.append(center_text(f"{Style.GRAY}{'─' * min(width - 4, 72)}{Style.RESET}", width))
    frame_lines.append("")

    prev_line = lines[index - 1].text if index > 0 else ""
    current_line = lines[index].text
    next_line = lines[index + 1].text if index + 1 < len(lines) else ""

    for line in wrap_line(prev_line, width - 12)[:2]:
        muted = f"{Style.DIM}{Style.WHITE}{line}{Style.RESET}"
        frame_lines.append(center_text(fit_line(muted, width), width))

    if prev_line:
        frame_lines.append("")

    current_start = lines[index].timestamp
    span = max(0.1, next_timestamp - current_start)
    progress = (elapsed - current_start) / span

    if ascii_lyrics:
        ascii_progress = min(1.0, max(0.0, progress / ASCII_REVEAL_PORTION))
        for art_line in ascii_art_lines(current_line, width - 4, ascii_progress):
            highlighted = f"{Style.BOLD}{Style.YELLOW}{art_line}{Style.RESET}"
            frame_lines.append(center_text(fit_line(highlighted, width), width))
        caption = f"{Style.DIM}{Style.YELLOW}{current_line}{Style.RESET}"
        frame_lines.append(center_text(fit_line(caption, width - 4), width))
    else:
        emoji_pack = build_emoji_pack(current_line, index)
        current_wrapped = wrap_line(current_line, width - 16)[:3]
        for wrapped in current_wrapped:
            highlighted = f"{Style.BOLD}{Style.YELLOW}{emoji_pack}  {wrapped}  {emoji_pack}{Style.RESET}"
            frame_lines.append(center_text(fit_line(highlighted, width), width))

    frame_lines.append("")

    for line in wrap_line(next_line, width - 12)[:2]:
        muted = f"{Style.GRAY}{line}{Style.RESET}"
        frame_lines.append(center_text(fit_line(muted, width), width))

    frame_lines.append("")
    bar = f"{Style.MAGENTA}{progress_bar(progress)}{Style.RESET}"
    frame_lines.append(center_text(f"{bar}  {format_seconds(next_timestamp)}", width))
    frame_lines.append("")
    footer = (
        f"{Style.BLUE}Ctrl+C para salir{Style.RESET}  "
        f"{Style.GRAY}|{Style.RESET}  "
        f"{Style.GREEN}Total líneas: {len(lines)}{Style.RESET}"
    )
    frame_lines.append(center_text(fit_line(footer, width), width))
    return width, frame_lines


def render_frame(
    track: TrackInfo,
    lines: list[LyricLine],
    index: int,
    elapsed: float,
    mode: str,
    next_timestamp: float,
    render_state: RenderState,
    ascii_lyrics: bool = False,
) -> None:
    _, frame_lines = build_frame_lines(track, lines, index, elapsed, mode, next_timestamp, ascii_lyrics)
    move_cursor_home()
    for row, line in enumerate(frame_lines, start=1):
        move_cursor_to(row)
        sys.stdout.write("\033[2K")
        sys.stdout.write(line)

    for row in range(len(frame_lines) + 1, render_state.previous_line_count + 1):
        move_cursor_to(row)
        sys.stdout.write("\033[2K")

    move_cursor_to(max(1, len(frame_lines)))
    sys.stdout.write("\033[J")
    sys.stdout.flush()
    render_state.previous_line_count = len(frame_lines)


def prepare_audio_player(track: TrackInfo, audio_options: AudioOptions) -> Optional[PygameAudioPlayer]:
    if not audio_options.enabled and not audio_options.local_file:
        return None

    if audio_options.local_file:
        if not os.path.exists(audio_options.local_file):
            raise AudioPlaybackError(f"No encontré el archivo de audio: {audio_options.local_file}")
        return PygameAudioPlayer(audio_options.local_file, audio_options.volume)

    audio_path = download_audio_track(track.artist, track.title)
    return PygameAudioPlayer(audio_path, audio_options.volume)


def play_karaoke(
    track: TrackInfo,
    lines: list[LyricLine],
    mode: str,
    audio_player: Optional[PygameAudioPlayer] = None,
    ascii_lyrics: bool = False,
) -> None:
    if not lines:
        raise LyricsLookupError("La letra está vacía y no puedo reproducirla.")

    with terminal_session():
        if audio_player is not None:
            audio_player.start()
        start = time.perf_counter()
        render_state = RenderState()
        index = 0
        try:
            while index < len(lines):
                current = lines[index]
                next_timestamp = (
                    lines[index + 1].timestamp if index + 1 < len(lines) else current.timestamp + 4.0
                )
                while True:
                    elapsed = time.perf_counter() - start
                    if elapsed >= current.timestamp:
                        break
                    render_frame(track, lines, index, elapsed, mode, next_timestamp, render_state, ascii_lyrics)
                    time.sleep(min(0.05, max(0.01, current.timestamp - elapsed)))

                while True:
                    elapsed = time.perf_counter() - start
                    render_frame(track, lines, index, elapsed, mode, next_timestamp, render_state, ascii_lyrics)
                    if elapsed >= next_timestamp or index == len(lines) - 1:
                        break
                    time.sleep(0.06)
                index += 1
        finally:
            if audio_player is not None:
                audio_player.stop()

        clear_screen()
        end_message = f"{Style.BOLD}{Style.GREEN}✨ Fin de la reproducción ✨{Style.RESET}"
        credits = f"{Style.CYAN}{track.title} - {track.artist}{Style.RESET}"
        print("\n" * 4)
        print(center_text(end_message, shutil.get_terminal_size((96, 30)).columns))
        print(center_text(credits, shutil.get_terminal_size((96, 30)).columns))
        print("\n")
        time.sleep(1.5)


def demo_track() -> tuple[TrackInfo, list[LyricLine], str]:
    track = TrackInfo(artist="Codex & You", title="Terminal Dream", album="Demo Mode", duration=14.0)
    demo_lyrics = """
[00:00.00] Luces en consola, empieza la función
[00:02.40] Cada línea cae siguiendo el corazón
[00:05.20] Brilla la pantalla, vibra la canción
[00:08.30] Entre emojis late fuerte esta sesión
[00:11.20] Terminal karaoke, pura conexión
""".strip()
    return track, parse_lrc(demo_lyrics), "demo sincronizado"


def ask_non_empty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Necesito un valor para continuar.")


def resolve_lyrics(
    artist: str,
    title: str,
    manual_lyrics: Optional[str] = None,
) -> tuple[TrackInfo, list[LyricLine], str]:
    try:
        track, synced, plain = search_track(artist, title)
    except LyricsLookupError as exc:
        if manual_lyrics:
            parsed, mode = timeline_from_text(manual_lyrics)
            if not parsed:
                raise LyricsLookupError("La letra manual está vacía.") from exc
            return TrackInfo(artist=artist, title=title), parsed, mode
        pasted = prompt_multiline_lyrics()
        if pasted:
            parsed, mode = timeline_from_text(pasted)
            if parsed:
                return TrackInfo(artist=artist, title=title), parsed, mode
        raise LyricsLookupError(str(exc)) from exc

    if synced:
        parsed = parse_lrc(synced)
        if parsed:
            return track, parsed, "sincronizado"

    if plain:
        estimated = estimate_timed_lyrics(plain)
        if estimated:
            return track, estimated, "estimado"

    if manual_lyrics:
        parsed, mode = timeline_from_text(manual_lyrics)
        if parsed:
            return TrackInfo(artist=artist, title=title), parsed, mode
    raise LyricsLookupError("No encontré una letra utilizable para esa canción.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce letras sincronizadas en terminal con una vibra karaoke.",
    )
    parser.add_argument("--artist", help="Nombre del cantante o banda.")
    parser.add_argument("--song", help="Nombre de la canción.")
    parser.add_argument("--manual-lyrics", help="Ruta a un archivo .txt con la letra manual.")
    parser.add_argument(
        "--with-audio",
        action="store_true",
        help="Intenta bajar el audio y reproducirlo junto al karaoke.",
    )
    parser.add_argument(
        "--audio-file",
        help="Ruta a un archivo de audio local para reproducirlo junto a la letra.",
    )
    parser.add_argument(
        "--audio-volume",
        type=float,
        default=0.75,
        help="Volumen del audio entre 0.0 y 1.0. Default: 0.75.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Lanza una demo local para probar la animación sin internet.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Abre la interfaz visual (carátula, mini-player y letra) en el navegador.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Puerto para la interfaz visual web. Default: 8765.",
    )
    return parser


def load_manual_lyrics(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def print_banner() -> None:
    width = shutil.get_terminal_size((96, 30)).columns
    title = f"{Style.BOLD}{Style.MAGENTA}♪ {APP_NAME} ♪{Style.RESET}"
    subtitle = f"{Style.GRAY}Letras sincronizadas, animación y emojis directo en tu consola{Style.RESET}"
    print()
    print(center_text(title, width))
    print(center_text(subtitle, width))
    print()


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    configure_console_streams()

    if args.web:
        try:
            import karaoke_web
        except ImportError as exc:
            print(
                f"{Style.YELLOW}Falta Flask para la interfaz web. Instala con: pip install flask{Style.RESET}",
                file=sys.stderr,
            )
            return 1
        karaoke_web.launch(port=args.port, open_browser=True)
        return 0

    try:
        if args.demo:
            track, lines, mode = demo_track()
            ascii_lyrics = ask_yes_no("🔤 ¿Quieres que la letra se dibuje en ASCII?", False)
            audio_options = AudioOptions(
                enabled=args.with_audio,
                local_file=args.audio_file,
                volume=args.audio_volume,
            )
        else:
            print_banner()
            artist = args.artist or ask_non_empty("🎙️  Cantante o banda: ")
            song = args.song or ask_non_empty("🎼  Canción: ")
            manual_lyrics = load_manual_lyrics(args.manual_lyrics)
            audio_enabled = args.with_audio
            if not args.audio_file and not args.with_audio:
                audio_enabled = ask_yes_no("🎧 ¿Quieres intentar bajar y reproducir el audio también?", False)
            ascii_lyrics = ask_yes_no("🔤 ¿Quieres que la letra se dibuje en ASCII?", False)
            audio_options = AudioOptions(
                enabled=audio_enabled,
                local_file=args.audio_file,
                volume=args.audio_volume,
            )
            print()
            print(f"{Style.CYAN}Buscando letra para {song} - {artist}...{Style.RESET}")
            track, lines, mode = resolve_lyrics(artist, song, manual_lyrics)

        audio_player = None
        if audio_options.enabled or audio_options.local_file:
            print(f"{Style.CYAN}Preparando audio...{Style.RESET}")
            audio_player = prepare_audio_player(track, audio_options)

        play_karaoke(track, lines, mode, audio_player, ascii_lyrics)
        return 0
    except KeyboardInterrupt:
        print(f"\n{Style.GRAY}Reproducción cancelada por el usuario.{Style.RESET}")
        return 130
    except FileNotFoundError as exc:
        print(f"{Style.YELLOW}No pude abrir el archivo de letra manual: {exc}{Style.RESET}", file=sys.stderr)
        return 1
    except LyricsLookupError as exc:
        print(f"{Style.YELLOW}{exc}{Style.RESET}", file=sys.stderr)
        return 1
    except AudioPlaybackError as exc:
        print(f"{Style.YELLOW}{exc}{Style.RESET}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"{Style.YELLOW}Ocurrió un error inesperado: {exc}{Style.RESET}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
