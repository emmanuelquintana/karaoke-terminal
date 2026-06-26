#!/usr/bin/env python3
"""Servidor web local para Terminal Karaoke.

Reutiliza el motor de ``karaoke_terminal`` (lrclib, descarga de audio con
yt-dlp, parseo de LRC) y le suma una interfaz visual estilo reproductor:
carátula, mini-player, letra sincronizada y fondo con blur.

Uso:
    python karaoke_web.py            # abre el navegador automáticamente
    python karaoke_web.py --no-open  # solo levanta el servidor
"""
from __future__ import annotations

import argparse
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

import karaoke_terminal as engine

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web"
ITUNES_ENDPOINT = "https://itunes.apple.com/search"

app = Flask(__name__, static_folder=None)


# --------------------------------------------------------------------------- #
# Carátula (iTunes Search API, sin API key)
# --------------------------------------------------------------------------- #
def _itunes_score(item: dict, artist: str, title: str) -> int:
    want_artist = engine.normalize_text(artist)
    want_title = engine.normalize_text(title)
    got_artist = engine.normalize_text(item.get("artistName", ""))
    got_title = engine.normalize_text(item.get("trackName", ""))
    score = 0
    if got_artist == want_artist:
        score += 6
    elif want_artist and want_artist in got_artist:
        score += 3
    if got_title == want_title:
        score += 8
    elif want_title and want_title in got_title:
        score += 4
    return score


def fetch_cover_art(artist: str, title: str, size: int = 1000) -> Optional[str]:
    """Devuelve la URL de la carátula en alta resolución o ``None``."""
    term = f"{artist} {title}".strip()
    if not term:
        return None
    query = urllib.parse.urlencode(
        {"term": term, "media": "music", "entity": "song", "limit": "8"}
    )
    url = f"{ITUNES_ENDPOINT}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": engine.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    results = payload.get("results") or []
    if not results:
        return None

    best = max(results, key=lambda item: _itunes_score(item, artist, title))
    artwork = best.get("artworkUrl100") or best.get("artworkUrl60")
    if not artwork:
        return None
    # iTunes entrega 100x100 por defecto; pedimos un tamaño mayor.
    return artwork.replace("100x100bb", f"{size}x{size}bb")


# --------------------------------------------------------------------------- #
# Resolución de letra "web-friendly" (sin prompts interactivos)
# --------------------------------------------------------------------------- #
def resolve_for_web(artist: str, title: str) -> dict:
    track, lines, mode = _resolve_lyrics_noninteractive(artist, title)
    payload_lines = [
        {"time": round(line.timestamp, 3), "text": line.text} for line in lines
    ]
    duration = track.duration
    if not duration and payload_lines:
        duration = payload_lines[-1]["time"] + 4.0

    cover = fetch_cover_art(track.artist, track.title)
    audio_available = engine.yt_dlp is not None and engine.imageio_ffmpeg is not None

    return {
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "duration": duration,
        "mode": mode,
        "cover": cover,
        "audioAvailable": audio_available,
        "lines": payload_lines,
    }


def _resolve_lyrics_noninteractive(artist: str, title: str):
    track, synced, plain = engine.search_track(artist, title)
    if synced:
        parsed = engine.parse_lrc(synced)
        if parsed:
            return track, parsed, "sincronizado"
    if plain:
        estimated = engine.estimate_timed_lyrics(plain)
        if estimated:
            return track, estimated, "estimado"
    raise engine.LyricsLookupError("No encontré una letra utilizable para esa canción.")


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #
def _no_cache(resp: Response) -> Response:
    # Evita que el navegador sirva una versión vieja del frontend tras un cambio.
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/")
def index() -> Response:
    return _no_cache(send_from_directory(STATIC_DIR, "index.html"))


@app.route("/web/<path:filename>")
def static_files(filename: str) -> Response:
    return _no_cache(send_from_directory(STATIC_DIR, filename))


@app.route("/api/song")
def api_song() -> Response:
    artist = (request.args.get("artist") or "").strip()
    title = (request.args.get("title") or "").strip()
    if not artist or not title:
        return jsonify({"error": "Faltan 'artist' y 'title'."}), 400
    try:
        return jsonify(resolve_for_web(artist, title))
    except engine.LyricsLookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Error inesperado: {exc}"}), 500


@app.route("/api/cover")
def api_cover() -> Response:
    """Proxy de la carátula (mismo origen) para poder muestrear sus colores
    en un canvas sin problemas de CORS."""
    url = (request.args.get("u") or "").strip()
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    allowed = host.endswith("mzstatic.com") or host.endswith("apple.com")
    if parsed.scheme != "https" or not allowed:
        return jsonify({"error": "URL de carátula no permitida."}), 400
    req = urllib.request.Request(url, headers={"User-Agent": engine.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
    except (urllib.error.URLError, TimeoutError):
        return jsonify({"error": "No pude descargar la carátula."}), 502
    resp = Response(data, mimetype=content_type)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/api/audio")
def api_audio() -> Response:
    artist = (request.args.get("artist") or "").strip()
    title = (request.args.get("title") or "").strip()
    if not artist or not title:
        return jsonify({"error": "Faltan 'artist' y 'title'."}), 400
    try:
        path = engine.download_audio_track(artist, title)
    except engine.AudioPlaybackError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"No pude preparar el audio: {exc}"}), 500
    # conditional=True habilita peticiones Range para hacer seek en el <audio>.
    return send_file(path, mimetype="audio/mpeg", conditional=True)


# --------------------------------------------------------------------------- #
# Arranque
# --------------------------------------------------------------------------- #
def launch(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    engine.configure_console_streams()
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"🎵 Terminal Karaoke — interfaz visual en {url}")
    print("   (Ctrl+C para detener)")
    app.run(host=host, port=port, debug=False, threaded=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Interfaz visual web de Terminal Karaoke.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="No abrir el navegador.")
    args = parser.parse_args()
    launch(host=args.host, port=args.port, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
