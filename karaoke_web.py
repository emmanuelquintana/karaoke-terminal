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
import difflib
import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from array import array
from pathlib import Path
from typing import Optional

from flask import Flask, Response, g, jsonify, request, send_file, send_from_directory

import karaoke_terminal as engine

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web"
FRONTEND_DIST_DIR = STATIC_DIR / "dist"
STUDIO_CACHE_DIR = BASE_DIR / ".studio_cache"
ITUNES_ENDPOINT = "https://itunes.apple.com/search"
API_SERVICE = "HX"
API_MODULE = "BO"
DEFAULT_METADATA = {"page": 0, "size": 0, "elements": 0}
ERROR_API_CODES = {400, 404, 409, 500}
MAX_STUDIO_CLIP_SECONDS = 58.0
MIN_STUDIO_SYNC_OFFSET = -60.0
MAX_STUDIO_SYNC_OFFSET = 180.0

STUDIO_SESSIONS: dict[str, dict] = {}
STUDIO_EXPORTS: dict[str, Path] = {}
FRONTEND_BUILD_CHECKED = False

app = Flask(__name__, static_folder=None)


@app.before_request
def _assign_trace_id() -> None:
    g.trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]


def _api_code(value: int | str) -> str:
    if isinstance(value, int):
        return f"{API_SERVICE}_{API_MODULE}_{value:03d}"
    raw = str(value).strip()
    if raw.startswith(f"{API_SERVICE}_{API_MODULE}_"):
        return raw
    return f"{API_SERVICE}_{API_MODULE}_{raw}"


def _api_metadata(metadata: Optional[dict] = None) -> dict:
    merged = dict(DEFAULT_METADATA)
    if metadata:
        merged.update(metadata)
    return merged


def _api_error_code(status: int) -> int:
    return status if status in ERROR_API_CODES else 500


def api_success(
    data: Optional[dict | list] = None,
    *,
    message: str = "OK",
    code: int | str = 1,
    status: int = 200,
    metadata: Optional[dict] = None,
) -> Response:
    return jsonify(
        {
            "code": _api_code(code),
            "message": message,
            "traceId": getattr(g, "trace_id", uuid.uuid4().hex[:16]),
            "data": data if data is not None else {},
            "metadata": _api_metadata(metadata),
        }
    ), status


def api_error(
    message: str,
    *,
    status: int = 500,
    data: Optional[dict | list] = None,
    metadata: Optional[dict] = None,
) -> Response:
    return api_success(
        data=data if data is not None else {},
        message=message,
        code=_api_error_code(status),
        status=status,
        metadata=metadata,
    )


@app.errorhandler(404)
def _not_found(_exc) -> Response:
    if request.path.startswith("/api/"):
        return api_error("Recurso no encontrado.", status=404)
    ensure_frontend_build()
    if not (FRONTEND_DIST_DIR / "index.html").exists():
        return frontend_build_missing_response()
    static_root = _frontend_root()
    return _no_cache(send_from_directory(static_root, "index.html"))


@app.errorhandler(409)
def _conflict(exc) -> Response:
    return api_error(str(exc) or "Conflicto en la solicitud.", status=409)


@app.errorhandler(500)
def _internal_error(exc) -> Response:
    return api_error(f"Error no controlado({exc})", status=500)


def _frontend_root() -> Path:
    return FRONTEND_DIST_DIR if (FRONTEND_DIST_DIR / "index.html").exists() else STATIC_DIR


def _frontend_source_files() -> list[Path]:
    sources = [BASE_DIR / "package.json", BASE_DIR / "package-lock.json", BASE_DIR / "vite.config.js", STATIC_DIR / "index.html", STATIC_DIR / "style.css"]
    src_dir = STATIC_DIR / "src"
    if src_dir.exists():
        sources.extend(path for path in src_dir.rglob("*") if path.is_file())
    return [path for path in sources if path.exists()]


def _frontend_build_is_current() -> bool:
    index_path = FRONTEND_DIST_DIR / "index.html"
    if not index_path.exists():
        return False
    dist_mtime = index_path.stat().st_mtime
    return all(path.stat().st_mtime <= dist_mtime for path in _frontend_source_files())


def ensure_frontend_build() -> None:
    global FRONTEND_BUILD_CHECKED
    if FRONTEND_BUILD_CHECKED and (FRONTEND_DIST_DIR / "index.html").exists():
        return
    FRONTEND_BUILD_CHECKED = True
    if _frontend_build_is_current():
        return
    if not (BASE_DIR / "package.json").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        return
    try:
        if not (BASE_DIR / "node_modules").exists():
            subprocess.run([npm, "install"], cwd=BASE_DIR, capture_output=True, text=True, timeout=180)
        subprocess.run([npm, "run", "build"], cwd=BASE_DIR, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return


def frontend_build_missing_response() -> Response:
    return Response(
        """<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Frontend no compilado</title></head>
<body style="font-family: system-ui, sans-serif; background:#08080b; color:#f5f5f7; display:grid; min-height:100vh; place-items:center; margin:0;">
  <main style="max-width: 640px; padding: 32px; line-height:1.5;">
    <h1>Frontend React no compilado</h1>
    <p>Ejecuta <code>npm install</code> y <code>npm run build</code>, o usa <code>./serve_public.ps1</code> para compilar antes de abrir el túnel.</p>
  </main>
</body>
</html>""",
        status=503,
        mimetype="text/html",
    )


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _song_payload(artist: str, title: str) -> tuple[dict, int]:
    if not artist or not title:
        return {"error": "Faltan 'artist' y 'title'."}, 400
    try:
        return resolve_for_web(artist, title), 200
    except engine.LyricsLookupError as exc:
        return {"error": str(exc)}, 404
    except Exception as exc:  # pragma: no cover
        return {"error": f"Error no controlado({exc})"}, 500


def _prepare_studio_payload(payload: dict) -> tuple[dict, int]:
    video_ref = (payload.get("video") or "").strip()
    artist = (payload.get("artist") or "").strip()
    title = (payload.get("title") or "").strip()
    if not video_ref or not artist or not title:
        return {"error": "Faltan video, artista o canción."}, 400

    try:
        song = resolve_for_web(artist, title)
        video_path, video_meta = resolve_studio_video(video_ref)
    except engine.LyricsLookupError as exc:
        return {"error": str(exc)}, 404
    except engine.AudioPlaybackError as exc:
        return {"error": str(exc)}, 503
    except Exception as exc:  # pragma: no cover
        return {"error": f"No pude preparar el estudio: {exc}"}, 500

    session_id = uuid.uuid4().hex[:12]
    STUDIO_SESSIONS[session_id] = {
        "videoPath": str(video_path),
        "video": video_meta,
        "song": song,
        "createdAt": time.time(),
    }
    return {
        "sessionId": session_id,
        "videoUrl": f"/api/v1/studio-sessions/{session_id}/video",
        "legacyVideoUrl": f"/api/studio/video/{session_id}",
        "maxClipSeconds": MAX_STUDIO_CLIP_SECONDS,
        "video": video_meta,
        "song": song,
    }, 201


def _sync_studio_payload(session_id: str) -> tuple[dict, int]:
    if not session_id:
        return {"error": "Falta la sesión del estudio."}, 400
    try:
        return auto_sync_studio_audio(session_id), 200
    except (KeyError, FileNotFoundError) as exc:
        return {"error": str(exc)}, 404
    except engine.AudioPlaybackError as exc:
        return {"error": str(exc)}, 503
    except subprocess.TimeoutExpired:
        return {"error": "La sincronización tardó demasiado y se canceló."}, 504
    except Exception as exc:  # pragma: no cover
        return {"error": f"No pude sincronizar el audio: {exc}"}, 500


def _export_studio_payload(session_id: str, payload: dict) -> tuple[dict, int]:
    if not session_id:
        return {"error": "Falta la sesión del estudio."}, 400
    try:
        export_id, out_path = export_studio_clip(session_id, payload)
    except (KeyError, FileNotFoundError) as exc:
        return {"error": str(exc)}, 404
    except engine.AudioPlaybackError as exc:
        return {"error": str(exc)}, 503
    except subprocess.TimeoutExpired:
        return {"error": "La exportación tardó demasiado y se canceló."}, 504
    except Exception as exc:  # pragma: no cover
        return {"error": f"No pude exportar el clip: {exc}"}, 500
    return {
        "exportId": export_id,
        "downloadUrl": f"/api/v1/studio-exports/{export_id}/file",
        "legacyDownloadUrl": f"/api/studio/download/{export_id}",
        "filename": out_path.name,
    }, 201


def _openapi_spec() -> dict:
    envelope_schema = {
        "type": "object",
        "required": ["code", "message", "traceId", "data", "metadata"],
        "properties": {
            "code": {"type": "string", "example": "HX_BO_001"},
            "message": {"type": "string", "example": "OK"},
            "traceId": {"type": "string", "example": "c49c5368e1c7a6b5"},
            "data": {"type": "object"},
            "metadata": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "example": 0},
                    "size": {"type": "integer", "example": 0},
                    "elements": {"type": "integer", "example": 0},
                },
            },
        },
    }
    return {
        "openapi": "3.0.3",
        "info": {"title": "Terminal Karaoke API", "version": "1.0.0"},
        "servers": [{"url": "/api/v1"}],
        "components": {"schemas": {"ApiEnvelope": envelope_schema}},
        "paths": {
            "/songs": {
                "get": {
                    "summary": "Resuelve letra, portada y metadatos de una canción",
                    "parameters": [
                        {"name": "artist", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "title", "in": "query", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Canción resuelta", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiEnvelope"}}}}},
                }
            },
            "/songs/audio": {
                "get": {
                    "summary": "Stream de audio de una canción",
                    "parameters": [
                        {"name": "artist", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "title", "in": "query", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Audio MP3", "content": {"audio/mpeg": {}}}},
                }
            },
            "/covers": {
                "get": {
                    "summary": "Proxy seguro de portada",
                    "parameters": [{"name": "u", "in": "query", "required": True, "schema": {"type": "string", "format": "uri"}}],
                    "responses": {"200": {"description": "Imagen de portada"}},
                }
            },
            "/studio-sessions": {
                "post": {
                    "summary": "Crea una sesión de estudio",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object", "required": ["video", "artist", "title"]}}},
                    },
                    "responses": {"201": {"description": "Sesión creada", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiEnvelope"}}}}},
                }
            },
            "/studio-sessions/{sessionId}/video": {
                "get": {
                    "summary": "Video local de la sesión",
                    "parameters": [{"name": "sessionId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Video MP4", "content": {"video/mp4": {}}}},
                }
            },
            "/studio-sessions/{sessionId}/sync": {
                "post": {
                    "summary": "Sincroniza letra con audio/ASR",
                    "parameters": [{"name": "sessionId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Sincronización aplicada", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiEnvelope"}}}}},
                }
            },
            "/studio-sessions/{sessionId}/exports": {
                "post": {
                    "summary": "Exporta un clip MP4 con subtítulos quemados",
                    "parameters": [{"name": "sessionId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"201": {"description": "Export creado", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiEnvelope"}}}}},
                }
            },
            "/studio-exports/{exportId}/file": {
                "get": {
                    "summary": "Descarga un export MP4",
                    "parameters": [{"name": "exportId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "Archivo MP4", "content": {"video/mp4": {}}}},
                }
            },
        },
    }


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
        estimated = estimate_plain_lyrics_for_web(plain, track.duration)
        if estimated:
            return track, estimated, "estimado"
    raise engine.LyricsLookupError("No encontré una letra utilizable para esa canción.")


# --------------------------------------------------------------------------- #
# Estudio TikTok (video + subtítulos quemados)
# --------------------------------------------------------------------------- #
def ensure_studio_cache_dir() -> None:
    STUDIO_CACHE_DIR.mkdir(exist_ok=True)


def estimated_plain_lead_in(duration: Optional[float], line_count: int) -> float:
    if not duration or duration <= 45 or line_count <= 0:
        return 0.0
    if line_count <= 10:
        ratio = 0.12
    elif line_count <= 24:
        ratio = 0.09
    else:
        ratio = 0.07
    return round(_bounded(duration * ratio, 6.0, 24.0), 2)


def estimate_plain_lyrics_for_web(raw_lyrics: str, duration: Optional[float]) -> list[engine.LyricLine]:
    estimated = engine.estimate_timed_lyrics(raw_lyrics)
    if not estimated or not duration or duration <= 45:
        return estimated

    lead_in = estimated_plain_lead_in(duration, len(estimated))
    if lead_in <= 0:
        return estimated

    # La letra plana no trae timestamps reales. No conviene estirarla para llenar
    # toda la canción: si el proveedor omite repeticiones, cada línea queda viva
    # demasiado tiempo. Tampoco debe ir a velocidad de lectura pura, porque el
    # canto suele respirar más. Usamos un factor moderado según densidad de líneas.
    density = len(estimated) / max(1.0, duration)
    if density < 0.085:
        pace_scale = 1.62
    elif density < 0.13:
        pace_scale = 1.45
    elif density < 0.18:
        pace_scale = 1.25
    else:
        pace_scale = 1.08
    return [
        engine.LyricLine(timestamp=round(lead_in + line.timestamp * pace_scale, 3), text=line.text)
        for line in estimated
    ]


def _studio_key(value: str) -> str:
    return hashlib.sha1(value.strip().casefold().encode("utf-8")).hexdigest()[:16]


def _looks_like_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value.strip(), flags=re.IGNORECASE))


def _ffmpeg_exe() -> str:
    if engine.imageio_ffmpeg is None:
        raise engine.AudioPlaybackError(
            "Falta FFmpeg para preparar videos. Instala `imageio-ffmpeg`."
        )
    return engine.imageio_ffmpeg.get_ffmpeg_exe()


def _find_downloaded_studio_video(key: str) -> Optional[Path]:
    candidates = [
        path for path in STUDIO_CACHE_DIR.glob(f"video-{key}.*")
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _convert_video_to_mp4(source: Path, target: Path) -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if result.returncode != 0:
        raise engine.AudioPlaybackError(
            "FFmpeg no pudo convertir el video descargado a MP4."
        )


def resolve_studio_video(video_ref: str) -> tuple[Path, dict]:
    """Busca/descarga un video y devuelve el archivo local MP4 con metadatos."""
    if engine.yt_dlp is None:
        raise engine.AudioPlaybackError(
            "Falta yt-dlp para buscar y descargar videos. Instala `yt-dlp`."
        )

    ensure_studio_cache_dir()
    key = _studio_key(video_ref)
    target_mp4 = STUDIO_CACHE_DIR / f"video-{key}.mp4"
    meta_path = STUDIO_CACHE_DIR / f"video-{key}.json"
    if target_mp4.exists() and meta_path.exists():
        try:
            return target_mp4, json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    lookup = video_ref.strip() if _looks_like_url(video_ref) else f"ytsearch1:{video_ref.strip()}"
    output_template = str(STUDIO_CACHE_DIR / f"video-{key}.%(ext)s")
    options = {
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]/best",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "ffmpeg_location": _ffmpeg_exe(),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with engine.yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(lookup, download=True)
    except Exception as exc:  # pragma: no cover
        raise engine.AudioPlaybackError(f"No pude preparar ese video: {exc}") from exc

    if isinstance(info, dict) and info.get("entries"):
        entries = [entry for entry in info.get("entries") or [] if entry]
        info = entries[0] if entries else info

    downloaded = _find_downloaded_studio_video(key)
    if downloaded is None:
        raise engine.AudioPlaybackError("La descarga terminó, pero no encontré el video final.")
    if downloaded.resolve() != target_mp4.resolve():
        if target_mp4.exists():
            target_mp4.unlink()
        if downloaded.suffix.lower() == ".mp4":
            downloaded.replace(target_mp4)
        else:
            _convert_video_to_mp4(downloaded, target_mp4)

    meta = {
        "title": (info or {}).get("title") or "Video seleccionado",
        "duration": (info or {}).get("duration"),
        "webpageUrl": (info or {}).get("webpage_url") or (info or {}).get("original_url") or video_ref,
        "thumbnail": (info or {}).get("thumbnail"),
        "uploader": (info or {}).get("uploader") or "",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_mp4, meta


def _extract_sync_pcm(source: Path, target: Path, seconds: float) -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "8000",
        "-t",
        f"{seconds:.1f}",
        "-f",
        "s16le",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        raise engine.AudioPlaybackError("No pude leer el audio del video para sincronizar.")


def _read_pcm_samples(path: Path) -> array:
    samples = array("h")
    with path.open("rb") as handle:
        samples.frombytes(handle.read())
    if samples.itemsize != 2:
        raise engine.AudioPlaybackError("El audio convertido no tiene el formato esperado.")
    if samples and samples[0] > 32767:  # pragma: no cover - depende de la plataforma
        samples.byteswap()
    return samples


def _audio_energy_signature(path: Path, window: int = 1024, hop: int = 512) -> tuple[list[float], float]:
    samples = _read_pcm_samples(path)
    if len(samples) < window * 4:
        raise engine.AudioPlaybackError("El audio es demasiado corto para sincronizar.")

    envelope: list[float] = []
    for start in range(0, len(samples) - window, hop):
        total = 0
        for sample in samples[start:start + window]:
            total += sample * sample
        rms = math.sqrt(total / window)
        envelope.append(math.log1p(rms))

    if len(envelope) < 12:
        raise engine.AudioPlaybackError("No hay suficiente audio útil para sincronizar.")

    smoothed: list[float] = []
    for i in range(len(envelope)):
        left = envelope[i - 1] if i else envelope[i]
        right = envelope[i + 1] if i + 1 < len(envelope) else envelope[i]
        smoothed.append((left + envelope[i] + right) / 3.0)

    # Los cambios de energía sobreviven mejor a compresión, volumen distinto y masters
    # ligeramente diferentes que la energía absoluta.
    deltas = [smoothed[i + 1] - smoothed[i] for i in range(len(smoothed) - 1)]
    return deltas, hop / 8000.0


def _window_correlation(reference: list[float], video: list[float], lag: int) -> tuple[float, int]:
    ref_start = max(0, -lag)
    video_start = max(0, lag)
    n = min(len(reference) - ref_start, len(video) - video_start)
    if n <= 0:
        return 0.0, 0

    xs = reference[ref_start:ref_start + n]
    ys = video[video_start:video_start + n]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for x, y in zip(xs, ys):
        dx = x - mean_x
        dy = y - mean_y
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy
    denom = math.sqrt(den_x * den_y)
    if denom <= 1e-9:
        return 0.0, n
    return num / denom, n


def find_audio_offset(
    reference: list[float],
    video: list[float],
    hop_seconds: float,
    *,
    min_offset: float = MIN_STUDIO_SYNC_OFFSET,
    max_offset: float = MAX_STUDIO_SYNC_OFFSET,
    min_overlap_seconds: float = 18.0,
) -> dict:
    """Encuentra cuánto debe desplazarse la letra: tiempo_video - tiempo_canción."""
    if not reference or not video:
        raise engine.AudioPlaybackError("No pude construir la huella de audio.")

    min_lag = int(min_offset / hop_seconds)
    max_lag = int(max_offset / hop_seconds)
    min_overlap = max(8, min(len(reference), int(min_overlap_seconds / hop_seconds)))
    best_score = -1.0
    best_lag = 0
    best_overlap = 0

    for lag in range(min_lag, max_lag + 1):
        score, overlap = _window_correlation(reference, video, lag)
        if overlap < min_overlap:
            continue
        # Favorece matches largos, pero sin castigar demasiado clips cortos.
        coverage = min(1.0, overlap / max(min_overlap, len(reference) * 0.65))
        weighted = score * (0.78 + 0.22 * coverage)
        if weighted > best_score:
            best_score = weighted
            best_lag = lag
            best_overlap = overlap

    if best_overlap < min_overlap:
        raise engine.AudioPlaybackError("No encontré suficiente audio comparable para sincronizar.")

    confidence = max(0.0, min(1.0, (best_score - 0.08) / 0.38))
    offset = round(best_lag * hop_seconds, 2)
    return {
        "offset": offset,
        "confidence": round(confidence, 3),
        "score": round(best_score, 3),
        "overlapSeconds": round(best_overlap * hop_seconds, 1),
    }


def first_singable_line_time(song: dict) -> float:
    for line in song.get("lines") or []:
        text = (line.get("text") or "").strip()
        if text and text != "♪":
            return _as_float(line.get("time"), 0.0)
    return 0.0


def estimated_lyric_correction(song: dict) -> float:
    mode = (song.get("mode") or "").casefold()
    if "estimado" not in mode:
        return 0.0
    lines = song.get("lines") or []
    lead_in = estimated_plain_lead_in(_as_float(song.get("duration"), 0.0), len(lines))
    first_line = first_singable_line_time(song)
    return round(max(0.0, lead_in - first_line), 2)


def _clean_caption_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[[^\]]+\]|\([^\)]*(?:música|music|aplausos|instrumental)[^\)]*\)", " ", value, flags=re.IGNORECASE)
    value = value.replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def _normalized_words(value: str) -> list[str]:
    normalized = engine.normalize_text(_clean_caption_text(value))
    return re.findall(r"[a-z0-9]+", normalized)


def _text_similarity(expected: str, actual: str) -> float:
    expected_words = _normalized_words(expected)
    actual_words = _normalized_words(actual)
    if not expected_words or not actual_words:
        return 0.0
    expected_norm = " ".join(expected_words)
    actual_norm = " ".join(actual_words)
    sequence_score = difflib.SequenceMatcher(None, expected_norm, actual_norm).ratio()
    expected_set = set(expected_words)
    actual_set = set(actual_words)
    overlap = len(expected_set & actual_set) / max(1, len(expected_set))
    ordered_hits = 0
    cursor = 0
    for word in expected_words:
        try:
            found = actual_words.index(word, cursor)
        except ValueError:
            continue
        ordered_hits += 1
        cursor = found + 1
    order_score = ordered_hits / max(1, len(expected_words))
    return max(sequence_score, overlap * 0.85 + order_score * 0.15)


def _word_similarity(expected: str, actual: str) -> float:
    if expected == actual:
        return 1.0
    if len(expected) < 4 or len(actual) < 4:
        return 0.0
    return difflib.SequenceMatcher(None, expected, actual).ratio()


def _ordered_word_hit_ratio(expected_words: list[str], actual_words: list[str]) -> float:
    if not expected_words or not actual_words:
        return 0.0
    hits = 0
    cursor = 0
    for expected in expected_words:
        found_index = -1
        for index in range(cursor, len(actual_words)):
            if _word_similarity(expected, actual_words[index]) >= 0.82:
                found_index = index
                break
        if found_index >= 0:
            hits += 1
            cursor = found_index + 1
    return hits / max(1, len(expected_words))


def _matched_word_bounds(expected_words: list[str], actual_words: list[str]) -> tuple[int, int]:
    matched: list[int] = []
    cursor = 0
    for expected in expected_words:
        found_index = -1
        for index in range(cursor, len(actual_words)):
            if _word_similarity(expected, actual_words[index]) >= 0.82:
                found_index = index
                break
        if found_index >= 0:
            matched.append(found_index)
            cursor = found_index + 1
    if len(matched) >= max(1, math.ceil(len(expected_words) * 0.34)):
        return matched[0], matched[-1]
    return 0, max(0, len(actual_words) - 1)


def _estimated_subtitle_duration(text: str) -> float:
    word_count = max(2, len(_normalized_words(text)))
    return _bounded(0.55 + word_count * 0.46, 1.2, 6.4)


def _timed_words_from_events(events: list[dict]) -> list[dict]:
    timed_words: list[dict] = []
    for event in events:
        for word in event.get("words") or []:
            raw = _clean_caption_text(str(word.get("word") or word.get("text") or ""))
            normalized = _normalized_words(raw)
            if not normalized:
                continue
            start = _as_float(word.get("start"), _as_float(event.get("start"), 0.0))
            end = _as_float(word.get("end"), start + 0.28)
            if end <= start:
                end = start + 0.28
            timed_words.append(
                {
                    "word": raw,
                    "norm": normalized[0],
                    "start": start,
                    "end": end,
                    "probability": _bounded(_as_float(word.get("probability"), 0.72), 0.0, 1.0),
                }
            )
    timed_words.sort(key=lambda item: (item["start"], item["end"]))
    return timed_words


def _best_word_alignment_for_line(
    line: dict,
    timed_words: list[dict],
    cursor: int,
    max_start_time: Optional[float] = None,
) -> Optional[dict]:
    expected_words = _normalized_words(line["text"])
    if not expected_words:
        return None

    expected_count = len(expected_words)
    min_span = max(1, int(expected_count * 0.55))
    max_span = min(24, max(expected_count + 5, int(expected_count * 1.75) + 1))
    scan_start = max(0, cursor - 2)
    scan_limit = min(len(timed_words), cursor + max(42, expected_count * 9))
    best: Optional[dict] = None

    for start_index in range(scan_start, scan_limit):
        if max_start_time is not None and timed_words[start_index]["start"] > max_start_time:
            break
        max_candidate_span = min(max_span, len(timed_words) - start_index)
        for span in range(min_span, max_candidate_span + 1):
            end_index = start_index + span
            window = timed_words[start_index:end_index]
            if not window:
                continue
            window_duration = window[-1]["end"] - window[0]["start"]
            if window_duration > max(10.5, expected_count * 1.35):
                break
            actual_words = [item["norm"] for item in window]
            actual_text = " ".join(item["word"] for item in window)
            text_score = _text_similarity(line["text"], actual_text)
            hit_ratio = _ordered_word_hit_ratio(expected_words, actual_words)
            span_fit = min(1.0, expected_count / max(1, len(actual_words)))
            avg_probability = sum(item["probability"] for item in window) / max(1, len(window))
            distance_penalty = max(0, start_index - cursor) * 0.012
            score = text_score * 0.62 + hit_ratio * 0.3 + span_fit * 0.05 + avg_probability * 0.03
            score -= distance_penalty
            if best is None or score > best["score"]:
                first_bound, last_bound = _matched_word_bounds(expected_words, actual_words)
                first_word = window[first_bound]
                last_word = window[last_bound]
                best = {
                    "score": score,
                    "hitRatio": hit_ratio,
                    "start": first_word["start"],
                    "end": last_word["end"],
                    "nextCursor": start_index + last_bound + 1,
                }

    if not best or best["score"] < 0.47 or best["hitRatio"] < 0.38:
        return None
    return best


def _fill_word_alignment_gaps(matches: list[Optional[dict]], lyric_lines: list[dict]) -> list[dict]:
    filled: list[dict] = []
    matched_indices = [index for index, match in enumerate(matches) if match]
    if not matched_indices:
        return []

    for index, line in enumerate(lyric_lines):
        match = matches[index]
        if match:
            filled.append(
                {
                    "time": round(match["start"], 3),
                    "end": round(max(match["start"] + 0.6, match["end"] + 0.28), 3),
                    "text": line["text"],
                }
            )
            continue

        previous_anchor = next((anchor for anchor in reversed(matched_indices) if anchor < index), None)
        next_anchor = next((anchor for anchor in matched_indices if anchor > index), None)
        duration = _estimated_subtitle_duration(line["text"])
        if previous_anchor is not None and next_anchor is not None:
            prev_match = matches[previous_anchor] or {}
            next_match = matches[next_anchor] or {}
            left = _as_float(prev_match.get("end"), 0.0) + 0.35
            right = max(left + 0.8, _as_float(next_match.get("start"), left + duration) - 0.35)
            source_left = lyric_lines[previous_anchor]["time"]
            source_right = lyric_lines[next_anchor]["time"]
            ratio = 0.5 if source_right <= source_left else (line["time"] - source_left) / (source_right - source_left)
            start = left + _bounded(ratio, 0.05, 0.95) * (right - left)
        elif previous_anchor is not None:
            prev_match = matches[previous_anchor] or {}
            source_delta = max(1.4, line["time"] - lyric_lines[previous_anchor]["time"])
            start = _as_float(prev_match.get("end"), 0.0) + min(source_delta, 5.5)
        else:
            next_match = matches[next_anchor] or {}
            source_delta = max(1.4, lyric_lines[next_anchor]["time"] - line["time"])
            start = max(0.0, _as_float(next_match.get("start"), duration) - min(source_delta, 5.5))
        filled.append({"time": round(start, 3), "end": round(start + duration, 3), "text": line["text"]})

    for index, line in enumerate(filled):
        if index + 1 >= len(filled):
            continue
        next_start = filled[index + 1]["time"]
        if line.get("end", line["time"]) > next_start - 0.08:
            line["end"] = round(max(line["time"] + 0.55, next_start - 0.08), 3)
    return filled


def align_lyrics_to_word_events(lyric_lines: list[dict], events: list[dict]) -> tuple[list[dict], float]:
    timed_words = _timed_words_from_events(events)
    if len(timed_words) < 4:
        return [], 0.0

    cursor = 0
    scores: list[float] = []
    matches: list[Optional[dict]] = []
    for line_index, line in enumerate(lyric_lines):
        match = _best_word_alignment_for_line(line, timed_words, cursor)
        matches.append(match)
        if match:
            cursor = max(cursor + 1, int(match["nextCursor"]))
            scores.append(_bounded(match["score"], 0.0, 1.0))

    matched_ratio = len(scores) / max(1, len(lyric_lines))
    if matched_ratio < 0.34:
        return [], 0.0
    aligned = _fill_word_alignment_gaps(matches, lyric_lines)
    if not aligned:
        return [], 0.0
    confidence = (sum(scores) / len(scores)) * min(1.0, matched_ratio * 1.45)
    return aligned, round(confidence, 3)


def _caption_url_from_tracks(tracks: list[dict]) -> Optional[str]:
    if not tracks:
        return None
    for ext in ("json3", "srv3", "vtt", "ttml"):
        for track in tracks:
            if track.get("ext") == ext and track.get("url"):
                return track["url"]
    for track in tracks:
        if track.get("url"):
            return track["url"]
    return None


def _caption_track_url(video_url: str) -> Optional[str]:
    if engine.yt_dlp is None or not video_url:
        return None
    options = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    try:
        with engine.yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(video_url, download=False)
    except Exception:
        return None

    preferred_langs = ("es", "es-419", "es-MX", "en")
    for bucket_name in ("subtitles", "automatic_captions"):
        bucket = info.get(bucket_name) or {}
        for lang in preferred_langs:
            url = _caption_url_from_tracks(bucket.get(lang) or [])
            if url:
                return url
        for tracks in bucket.values():
            url = _caption_url_from_tracks(tracks or [])
            if url:
                return url
    return None


def _fetch_caption_payload(url: str) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": engine.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        if engine.yt_dlp is None:
            return None
        try:
            with engine.yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as downloader:
                return downloader.urlopen(url).read().decode("utf-8", errors="replace")
        except Exception:
            return None


def _parse_json3_captions(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    events: list[dict] = []
    for event in payload.get("events") or []:
        text = _clean_caption_text("".join(seg.get("utf8", "") for seg in event.get("segs") or []))
        if not text:
            continue
        start = _as_float(event.get("tStartMs"), 0.0) / 1000.0
        duration = _as_float(event.get("dDurationMs"), 1800.0) / 1000.0
        events.append({"start": start, "end": start + max(0.3, duration), "text": text})
    return events


def _parse_vtt_timestamp(value: str) -> Optional[float]:
    match = re.match(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})", value.strip())
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int(match.group(4))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def _parse_vtt_captions(raw: str) -> list[dict]:
    events: list[dict] = []
    chunks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), -1)
        if timing_index < 0:
            continue
        left, right = lines[timing_index].split("-->", 1)
        start = _parse_vtt_timestamp(left)
        end = _parse_vtt_timestamp(right.split()[0])
        text = _clean_caption_text(" ".join(lines[timing_index + 1:]))
        if start is None or end is None or not text:
            continue
        events.append({"start": start, "end": max(start + 0.3, end), "text": text})
    return events


def fetch_video_caption_events(video_url: str) -> list[dict]:
    url = _caption_track_url(video_url)
    if not url:
        return []
    raw = _fetch_caption_payload(url)
    if not raw:
        return []
    raw_start = raw.lstrip()[:1]
    if raw_start == "{":
        return _parse_json3_captions(raw)
    return _parse_vtt_captions(raw)


def align_lyrics_to_timed_text(lines: list[dict], events: list[dict]) -> tuple[list[dict], float]:
    lyric_lines = [
        {"time": _as_float(line.get("time"), 0.0), "text": (line.get("text") or "").strip()}
        for line in lines
        if (line.get("text") or "").strip() and (line.get("text") or "").strip() != "♪"
    ]
    if not lyric_lines or not events:
        return [], 0.0

    word_aligned, word_confidence = align_lyrics_to_word_events(lyric_lines, events)
    if word_confidence >= 0.4:
        return word_aligned, word_confidence

    distributed, distributed_confidence = distribute_lyrics_over_segments(lyric_lines, events)
    if distributed_confidence >= 0.42:
        return distributed, distributed_confidence

    aligned: list[dict] = []
    search_index = 0
    scores: list[float] = []
    natural_deltas = [
        max(1.4, lyric_lines[i + 1]["time"] - lyric_lines[i]["time"])
        for i in range(len(lyric_lines) - 1)
    ]
    fallback_time = lyric_lines[0]["time"]

    for i, line in enumerate(lyric_lines):
        best_score = 0.0
        best_start = None
        best_end = None
        best_index = search_index
        best_span = 99
        limit = min(len(events), search_index + 38)
        for event_index in range(search_index, limit):
            combined = ""
            combined_end = events[event_index]["end"]
            for span in range(1, 5):
                if event_index + span > len(events):
                    break
                selected = events[event_index:event_index + span]
                combined = " ".join(event["text"] for event in selected)
                combined_end = selected[-1]["end"]
                if combined_end - selected[0]["start"] > 10.0:
                    break
                score = _text_similarity(line["text"], combined)
                if score > best_score + 0.03 or (abs(score - best_score) <= 0.03 and span < best_span):
                    best_score = score
                    best_start = selected[0]["start"]
                    best_end = combined_end
                    best_index = event_index + span - 1
                    best_span = span

        if best_start is not None and best_score >= 0.42:
            timestamp = best_start
            line_end = max(timestamp + 0.6, _as_float(best_end, timestamp + _estimated_subtitle_duration(line["text"])))
            search_index = min(len(events) - 1, best_index + 1)
            scores.append(best_score)
            fallback_time = timestamp
        else:
            if aligned:
                delta = natural_deltas[i - 1] if i - 1 < len(natural_deltas) else 2.8
                fallback_time = aligned[-1].get("end", aligned[-1]["time"]) + min(delta, 4.8)
            timestamp = fallback_time
            line_end = timestamp + _estimated_subtitle_duration(line["text"])
        aligned.append({"time": round(timestamp, 3), "end": round(line_end, 3), "text": line["text"]})

    confidence = sum(scores) / len(scores) if scores else 0.0
    matched_ratio = len(scores) / max(1, len(lyric_lines))
    return aligned, round(confidence * min(1.0, matched_ratio * 1.8), 3)


def distribute_lyrics_over_segments(lyric_lines: list[dict], events: list[dict]) -> tuple[list[dict], float]:
    aligned: list[dict] = []
    cursor = 0
    scores: list[float] = []
    first_expected = lyric_lines[0]["time"] if lyric_lines else 0.0

    for event in events:
        if cursor >= len(lyric_lines):
            break
        event_text = event.get("text") or ""
        if not event_text:
            continue

        best_count = 0
        best_score = 0.0
        max_count = min(6, len(lyric_lines) - cursor)
        event_words = set(_normalized_words(event_text))
        for count in range(1, max_count + 1):
            combined = " ".join(line["text"] for line in lyric_lines[cursor:cursor + count])
            combined_words = set(_normalized_words(combined))
            event_coverage = len(combined_words & event_words) / max(1, len(event_words))
            score = _text_similarity(combined, event_text) * 0.72 + event_coverage * 0.28
            if score > best_score:
                best_score = score
                best_count = count

        if best_count <= 0 or best_score < 0.36:
            continue

        start = _as_float(event.get("start"), 0.0)
        end = max(start + 0.8, _as_float(event.get("end"), start + 2.8))
        if not aligned and start < first_expected * 0.55:
            start = first_expected
        if aligned:
            start = max(start, aligned[-1].get("end", aligned[-1]["time"]) + 0.35)
        if end <= start:
            end = start + max(1.4, best_count * 2.4)

        selected = lyric_lines[cursor:cursor + best_count]
        natural_total = sum(_estimated_subtitle_duration(line["text"]) for line in selected)
        previous_end = aligned[-1].get("end", aligned[-1]["time"]) if aligned else None
        has_leading_gap = previous_end is not None and start - previous_end > 5.0
        if has_leading_gap and end - start > natural_total + 4.0:
            start = max(start, end - natural_total)
        if best_count == 1:
            offsets = [0.0]
        else:
            weights = []
            for line in selected:
                word_count = max(2, len(_normalized_words(line["text"])))
                weights.append(word_count)
            total = sum(weights)
            usable = max(1.0, end - start)
            offsets = []
            acc = 0.0
            for index, weight in enumerate(weights):
                offsets.append(acc)
                acc += usable * (weight / total)

        line_starts = [start + offset for offset in offsets]
        for index, (line, line_start) in enumerate(zip(selected, line_starts)):
            estimated_end = line_start + _estimated_subtitle_duration(line["text"])
            next_start = line_starts[index + 1] if index + 1 < len(line_starts) else None
            if next_start is not None:
                line_end = min(estimated_end, next_start - 0.08)
            else:
                line_end = min(estimated_end, end)
            line_end = max(line_start + 0.6, line_end)
            aligned.append({"time": round(line_start, 3), "end": round(line_end, 3), "text": line["text"]})
        scores.append(best_score)
        cursor += best_count

    if not aligned:
        return [], 0.0

    # Completa cualquier línea que no haya encontrado match con el ritmo estimado
    # original, manteniendo continuidad desde la última línea alineada.
    while cursor < len(lyric_lines):
        previous = aligned[-1]["time"] if aligned else lyric_lines[cursor]["time"]
        if cursor > 0:
            delta = max(1.6, lyric_lines[cursor]["time"] - lyric_lines[cursor - 1]["time"])
        else:
            delta = 2.8
        timestamp = previous + min(delta, 5.2)
        aligned.append(
            {
                "time": round(timestamp, 3),
                "end": round(timestamp + _estimated_subtitle_duration(lyric_lines[cursor]["text"]), 3),
                "text": lyric_lines[cursor]["text"],
            }
        )
        cursor += 1

    coverage = len(scores) / max(1, len(events))
    line_coverage = min(1.0, len(scores) * 2.0 / max(1, len(lyric_lines)))
    confidence = (sum(scores) / len(scores)) * min(1.0, max(coverage, line_coverage))
    return aligned, round(confidence, 3)


def transcribe_video_audio_events(video_path: Path) -> list[dict]:
    """ASR local opcional. Se usa si existe faster-whisper/openai-whisper instalado."""
    sync_id = uuid.uuid4().hex[:10]
    wav_path = STUDIO_CACHE_DIR / f"asr-{sync_id}.wav"
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(video_path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-t",
        "210",
        str(wav_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0 or not wav_path.exists():
            return []
        # "base" es rápido, pero en canciones con mezcla completa tiende a fallar.
        # "small" es un punto razonable entre precisión para voz cantada y costo CPU.
        model_name = "small"
        try:
            from faster_whisper import WhisperModel  # type: ignore

            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            segments, _ = model.transcribe(
                str(wav_path),
                language="es",
                vad_filter=False,
                word_timestamps=True,
                condition_on_previous_text=False,
            )
            events: list[dict] = []
            for segment in segments:
                text = _clean_caption_text(segment.text)
                if not text:
                    continue
                words: list[dict] = []
                for word in getattr(segment, "words", None) or []:
                    word_text = _clean_caption_text(getattr(word, "word", ""))
                    if not word_text:
                        continue
                    start = float(getattr(word, "start", segment.start))
                    end = float(getattr(word, "end", start + 0.28))
                    words.append(
                        {
                            "start": start,
                            "end": max(start + 0.08, end),
                            "word": word_text,
                            "probability": float(getattr(word, "probability", 0.72)),
                        }
                    )
                events.append({"start": float(segment.start), "end": float(segment.end), "text": text, "words": words})
            return events
        except ImportError:
            pass

        try:
            import whisper  # type: ignore

            model = whisper.load_model(model_name)
            try:
                payload = model.transcribe(str(wav_path), language="es", fp16=False, word_timestamps=True)
            except TypeError:
                payload = model.transcribe(str(wav_path), language="es", fp16=False)
            return [
                {
                    "start": _as_float(segment.get("start"), 0.0),
                    "end": _as_float(segment.get("end"), 0.0),
                    "text": _clean_caption_text(segment.get("text") or ""),
                    "words": [
                        {
                            "start": _as_float(word.get("start"), _as_float(segment.get("start"), 0.0)),
                            "end": _as_float(word.get("end"), _as_float(segment.get("start"), 0.0) + 0.28),
                            "word": _clean_caption_text(word.get("word") or ""),
                            "probability": _as_float(word.get("probability"), 0.72),
                        }
                        for word in segment.get("words") or []
                        if _clean_caption_text(word.get("word") or "")
                    ],
                }
                for segment in payload.get("segments") or []
                if _clean_caption_text(segment.get("text") or "")
            ]
        except ImportError:
            return []
    except Exception:
        return []
    finally:
        try:
            wav_path.unlink()
        except FileNotFoundError:
            pass


def auto_sync_studio_audio(session_id: str) -> dict:
    session = _studio_session(session_id)
    song = session["song"]
    artist = (song.get("artist") or "").strip()
    title = (song.get("title") or "").strip()
    if not artist or not title:
        raise engine.AudioPlaybackError("La sesión no tiene artista y canción para sincronizar.")

    reference_audio = Path(engine.download_audio_track(artist, title))
    video_path = Path(session["videoPath"])
    sync_id = uuid.uuid4().hex[:10]
    ref_pcm = STUDIO_CACHE_DIR / f"sync-ref-{sync_id}.pcm"
    video_pcm = STUDIO_CACHE_DIR / f"sync-video-{sync_id}.pcm"
    try:
        _extract_sync_pcm(reference_audio, ref_pcm, 95.0)
        _extract_sync_pcm(video_path, video_pcm, MAX_STUDIO_SYNC_OFFSET + 95.0)
        reference_sig, hop_seconds = _audio_energy_signature(ref_pcm)
        video_sig, video_hop_seconds = _audio_energy_signature(video_pcm)
        if abs(hop_seconds - video_hop_seconds) > 0.0001:
            raise engine.AudioPlaybackError("No pude comparar las dos huellas de audio.")
        result = find_audio_offset(reference_sig, video_sig, hop_seconds)
    finally:
        for path in (ref_pcm, video_pcm):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    if result["confidence"] < 0.24:
        raise engine.AudioPlaybackError(
            "No encontré una coincidencia clara entre el audio del video y la canción."
        )
    audio_offset = result["offset"]
    lyric_correction = estimated_lyric_correction(song)
    result["audioOffset"] = audio_offset
    result["lyricCorrection"] = lyric_correction
    result["lyricMode"] = song.get("mode") or ""
    if lyric_correction:
        result["offset"] = round(audio_offset + lyric_correction, 2)
    result["timelineSource"] = "audio"
    result["timelineConfidence"] = result["confidence"]

    if "estimado" in (song.get("mode") or "").casefold():
        aligned_lines: list[dict] = []
        alignment_confidence = 0.0
        source = ""
        caption_events = fetch_video_caption_events(session.get("video", {}).get("webpageUrl") or "")
        if caption_events:
            aligned_lines, alignment_confidence = align_lyrics_to_timed_text(song.get("lines") or [], caption_events)
            source = "captions"
        if alignment_confidence < 0.38:
            asr_events = transcribe_video_audio_events(video_path)
            if asr_events:
                asr_lines, asr_confidence = align_lyrics_to_timed_text(song.get("lines") or [], asr_events)
                if asr_confidence > alignment_confidence:
                    aligned_lines = asr_lines
                    alignment_confidence = asr_confidence
                    source = "asr-local"
        if aligned_lines and alignment_confidence >= 0.38:
            song["lines"] = aligned_lines
            song["mode"] = "estimado sincronizado"
            result["lines"] = aligned_lines
            result["offset"] = 0.0
            result["lyricCorrection"] = 0.0
            result["timelineSource"] = source
            result["timelineConfidence"] = alignment_confidence
            result["lyricMode"] = song["mode"]

    result["firstCaptionAt"] = round(first_singable_line_time(song) + result["offset"], 2)
    return result


def _studio_session(session_id: str) -> dict:
    session = STUDIO_SESSIONS.get(session_id)
    if not session:
        raise KeyError("La sesión de estudio expiró. Prepara el video otra vez.")
    video_path = Path(session["videoPath"])
    if not video_path.exists():
        raise FileNotFoundError("El video de la sesión ya no está en caché.")
    return session


def _as_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def _bounded(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    centis = int(round(seconds * 100))
    total_seconds, centiseconds = divmod(centis, 100)
    minutes_total, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}.{centiseconds:02d}"


def _ass_text(value: str) -> str:
    cleaned = (value or "").replace("\\", "\\\\")
    cleaned = cleaned.replace("{", "\\{").replace("}", "\\}")
    return cleaned.replace("\n", "\\N")


def _ffmpeg_filter_path(path: Path) -> str:
    # FFmpeg filter paths need forward slashes and an escaped drive colon on Windows.
    value = path.resolve().as_posix()
    return value.replace(":", "\\:")


ASS_COLORS = {
    "white": "&H00FFFFFF",
    "warm": "&H006DE6FF",
    "rose": "&H006D4DFF",
}

ASS_FONTS = {
    "Inter": "Inter",
    "Poppins": "Poppins",
    "Playfair": "Playfair Display",
    "Caveat": "Caveat",
    "Arial": "Arial",
}

PNG_COLORS = {
    "white": (255, 255, 255, 255),
    "warm": (255, 230, 109, 255),
    "rose": (255, 107, 138, 255),
}


def subtitle_events_for_clip(lines: list[dict], *, start: float, length: float, offset: float) -> list[dict]:
    events: list[dict] = []
    clip_end = start + length
    for index, line in enumerate(lines):
        text = (line.get("text") or "").strip()
        if not text or text == "♪":
            continue
        line_start = _as_float(line.get("time"), 0.0) + offset
        if line.get("end") is not None:
            line_end = _as_float(line.get("end"), line_start + 3.0) + offset
        elif index + 1 < len(lines):
            line_end = _as_float(lines[index + 1].get("time"), line_start + 3.0) + offset
        else:
            line_end = line_start + 3.0
        if line_end <= start or line_start >= clip_end:
            continue
        event_start = _bounded(line_start - start, 0.0, length)
        event_end = _bounded(line_end - start, 0.0, length)
        if event_end - event_start < 0.35:
            event_end = _bounded(event_start + 1.2, 0.0, length)
        if event_end <= event_start:
            continue
        events.append({"start": event_start, "end": event_end, "text": text})
    return events


def _font_candidates(font: str) -> list[Path]:
    fonts_dir = Path("C:/Windows/Fonts")
    if font == "Playfair":
        return [fonts_dir / "georgiab.ttf", fonts_dir / "timesbd.ttf", fonts_dir / "arialbd.ttf"]
    if font == "Caveat":
        return [fonts_dir / "comicbd.ttf", fonts_dir / "segoeprb.ttf", fonts_dir / "arialbd.ttf"]
    if font == "Arial":
        return [fonts_dir / "arialbd.ttf", fonts_dir / "segoeuib.ttf"]
    return [fonts_dir / "segoeuib.ttf", fonts_dir / "arialbd.ttf"]


def _load_caption_font(font: str, size: int):
    from PIL import ImageFont

    for candidate in _font_candidates(font):
        try:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _text_width(draw, text: str, font, stroke_width: int = 0) -> int:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return max(0, bbox[2] - bbox[0])


def _text_height(draw, text: str, font, stroke_width: int = 0) -> int:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return max(0, bbox[3] - bbox[1])


def _text_bbox(draw, text: str, font, stroke_width: int = 0) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)


def _balanced_wrap_text(text: str, draw, font, max_width: int, stroke_width: int = 0) -> list[str]:
    words = text.split()
    if not words:
        return []
    if _text_width(draw, text, font, stroke_width) <= max_width:
        return [text]

    best_lines: list[str] = []
    best_score = float("inf")
    max_lines = min(4, len(words))
    for line_count in range(2, max_lines + 1):
        breaks: list[tuple[int, ...]] = []

        def collect(start: int, remaining: int, current: list[int]) -> None:
            if remaining == 1:
                breaks.append(tuple(current + [len(words)]))
                return
            for end in range(start + 1, len(words) - remaining + 2):
                collect(end, remaining - 1, current + [end])

        collect(0, line_count, [])
        for candidate_breaks in breaks:
            start_index = 0
            lines: list[str] = []
            widths: list[int] = []
            fits = True
            for end_index in candidate_breaks:
                line = " ".join(words[start_index:end_index])
                width = _text_width(draw, line, font, stroke_width)
                if width > max_width:
                    fits = False
                    break
                lines.append(line)
                widths.append(width)
                start_index = end_index
            if not fits:
                continue
            balance = max(widths) - min(widths)
            fill = max_width - max(widths)
            score = line_count * 120 + balance + fill * 0.18
            if score < best_score:
                best_score = score
                best_lines = lines
        if best_lines:
            return best_lines

    lines: list[str] = []
    current = ""
    for word in words:
        attempt = f"{current} {word}".strip()
        if current and _text_width(draw, attempt, font, stroke_width) > max_width:
            lines.append(current)
            current = word
        else:
            current = attempt
    if current:
        lines.append(current)
    return lines


def render_subtitle_overlay_png(
    *,
    path: Path,
    mask_path: Optional[Path] = None,
    text: str,
    width: int,
    height: int,
    layout: str,
    font: str,
    size: int,
    position: str,
    color: str,
    style: str,
    preview: Optional[dict] = None,
) -> None:
    from PIL import Image, ImageDraw, ImageFilter

    frame_width = _as_float((preview or {}).get("frameWidth"), 0.0)
    frame_height = _as_float((preview or {}).get("frameHeight"), 0.0)
    scale_x = width / frame_width if frame_width >= 180 else width / (384.0 if layout == "vertical" else 960.0)
    scale_y = height / frame_height if frame_height >= 180 else height / (682.667 if layout == "vertical" else 540.0)
    scale = min(scale_x, scale_y)

    font_size = scaled_subtitle_size(size, width, height, layout, preview)
    caption_width = _as_float((preview or {}).get("captionWidth"), 0.0)
    if caption_width > 0:
        box_width = int(round(caption_width * scale_x))
    else:
        margin_h, _ = scaled_subtitle_margins(width=width, height=height, layout=layout, position=position, preview=preview)
        box_width = width - margin_h * 2
    box_width = int(_bounded(box_width, width * 0.42, width * 0.95))

    preview = preview or {}
    pad_left = int(round(_as_float(preview.get("paddingLeft"), 16.0) * scale_x))
    pad_right = int(round(_as_float(preview.get("paddingRight"), 16.0) * scale_x))
    pad_top = int(round(_as_float(preview.get("paddingTop"), 12.0) * scale_y))
    pad_bottom = int(round(_as_float(preview.get("paddingBottom"), 12.0) * scale_y))
    radius = int(round(_as_float(preview.get("borderRadius"), 18.0) * scale))
    border = max(1, int(round(_as_float(preview.get("borderWidth"), 1.0) * scale)))
    css_line_height = _as_float(preview.get("lineHeight"), size * 1.05)
    line_box_height = max(1, int(round(css_line_height * scale_y)))
    stroke_width = max(2, int(round(font_size * 0.055))) if style == "karaoke" else 0

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    mask_image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    mask_draw = ImageDraw.Draw(mask_image)
    caption_font = _load_caption_font(font, font_size)
    text_max_width = max(80, box_width - pad_left - pad_right - border * 2)
    wrapped = _balanced_wrap_text(text, draw, caption_font, text_max_width, stroke_width)
    text_block_height = line_box_height * max(1, len(wrapped))
    box_height = text_block_height + pad_top + pad_bottom + border * 2
    preview_height = _as_float(preview.get("captionHeight"), 0.0)
    preview_line_count = int(_as_float(preview.get("lineCount"), 0.0))
    if preview_height > 0 and preview_line_count == len(wrapped):
        box_height = int(round(preview_height * scale_y))
    box_x = int(round((width - box_width) / 2))
    if position == "top":
        _, margin_v = scaled_subtitle_margins(width=width, height=height, layout=layout, position=position, preview=preview)
        box_y = margin_v
    elif position == "middle":
        box_y = int(round((height - box_height) / 2))
    else:
        _, margin_v = scaled_subtitle_margins(width=width, height=height, layout=layout, position=position, preview=preview)
        box_y = height - margin_v - box_height
    box_y = int(_bounded(box_y, 0, max(0, height - box_height)))

    if style == "boxed":
        mask_draw.rounded_rectangle(
            [box_x, box_y, box_x + box_width, box_y + box_height],
            radius=radius,
            fill=255,
        )
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_width, box_y + box_height],
            radius=radius,
            fill=(8, 8, 12, 138),
            outline=(255, 255, 255, 46),
            width=border,
        )

    text_color = PNG_COLORS.get(color, PNG_COLORS["white"])
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    inner_height = max(1, box_height - pad_top - pad_bottom - border * 2)
    first_line_top = box_y + pad_top + border + max(0, (inner_height - text_block_height) // 2)
    for index, line in enumerate(wrapped):
        bbox = _text_bbox(draw, line, caption_font, stroke_width)
        line_width = max(0, bbox[2] - bbox[0])
        line_height = max(0, bbox[3] - bbox[1])
        line_top = first_line_top + index * line_box_height
        text_x = int(round(box_x + (box_width - line_width) / 2 - bbox[0]))
        text_y = int(round(line_top + (line_box_height - line_height) / 2 - bbox[1]))
        shadow_draw.text(
            (text_x, text_y + int(round(3 * scale_y))),
            line,
            font=caption_font,
            fill=(0, 0, 0, 190),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 190),
        )
    image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(2, int(round(18 * scale))))))

    for index, line in enumerate(wrapped):
        bbox = _text_bbox(draw, line, caption_font, stroke_width)
        line_width = max(0, bbox[2] - bbox[0])
        line_height = max(0, bbox[3] - bbox[1])
        line_top = first_line_top + index * line_box_height
        text_x = int(round(box_x + (box_width - line_width) / 2 - bbox[0]))
        text_y = int(round(line_top + (line_box_height - line_height) / 2 - bbox[1]))
        draw.text(
            (text_x, text_y),
            line,
            font=caption_font,
            fill=text_color,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 120),
        )
    path.parent.mkdir(exist_ok=True)
    image.save(path)
    if mask_path is not None:
        mask_path.parent.mkdir(exist_ok=True)
        mask_image.save(mask_path)


def render_subtitle_overlay_images(
    events: list[dict],
    *,
    export_id: str,
    width: int,
    height: int,
    layout: str,
    font: str,
    size: int,
    position: str,
    color: str,
    style: str,
    preview: Optional[dict],
) -> list[tuple[Path, Optional[Path], float, float]]:
    overlays: list[tuple[Path, Optional[Path], float, float]] = []
    for index, event in enumerate(events):
        image_path = STUDIO_CACHE_DIR / f"caption-{export_id}-{index:03d}.png"
        mask_path = STUDIO_CACHE_DIR / f"caption-mask-{export_id}-{index:03d}.png" if style == "boxed" else None
        render_subtitle_overlay_png(
            path=image_path,
            mask_path=mask_path,
            text=event["text"],
            width=width,
            height=height,
            layout=layout,
            font=font,
            size=size,
            position=position,
            color=color,
            style=style,
            preview=preview,
        )
        overlays.append((image_path, mask_path, _as_float(event["start"], 0.0), _as_float(event["end"], 0.0)))
    return overlays


def timeline_segments_for_export(events: list[dict], length: float) -> list[dict]:
    segments: list[dict] = []
    cursor = 0.0
    for event in sorted(events, key=lambda item: _as_float(item.get("start"), 0.0)):
        event_start = _bounded(_as_float(event.get("start"), 0.0), 0.0, length)
        event_end = _bounded(_as_float(event.get("end"), event_start), 0.0, length)
        if event_end - event_start <= 0.04:
            continue
        if event_start > cursor + 0.04:
            segments.append({"start": cursor, "end": event_start, "overlay": None})
        event_start = max(event_start, cursor)
        if event_end > event_start + 0.04:
            segments.append({"start": event_start, "end": event_end, "overlay": event})
            cursor = event_end
    if length > cursor + 0.04:
        segments.append({"start": cursor, "end": length, "overlay": None})
    return segments or [{"start": 0.0, "end": length, "overlay": None}]


def _ffmpeg_error_tail(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip().splitlines()
    return " ".join(detail[-18:]) if detail else ""


def _run_export_command(cmd: list[str], *, timeout: int = 300) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        tail = _ffmpeg_error_tail(result)
        raise engine.AudioPlaybackError(f"FFmpeg no pudo exportar el clip con subtítulos. {tail}".strip())


def scaled_subtitle_size(size: int, width: int, height: int, layout: str, preview: Optional[dict] = None) -> int:
    frame_width = _as_float((preview or {}).get("frameWidth"), 0.0)
    frame_height = _as_float((preview or {}).get("frameHeight"), 0.0)
    if frame_width >= 180 and frame_height >= 180:
        scale = min(width / frame_width, height / frame_height)
    else:
        reference_width = 384.0 if layout == "vertical" else 960.0
        scale = width / reference_width
    return int(round(_bounded(size * scale, 24, 260)))


def scaled_subtitle_margins(
    *,
    width: int,
    height: int,
    layout: str,
    position: str,
    preview: Optional[dict] = None,
) -> tuple[int, int]:
    frame_width = _as_float((preview or {}).get("frameWidth"), 0.0)
    frame_height = _as_float((preview or {}).get("frameHeight"), 0.0)
    scale_x = width / frame_width if frame_width >= 180 else width / (384.0 if layout == "vertical" else 960.0)
    scale_y = height / frame_height if frame_height >= 180 else height / (682.667 if layout == "vertical" else 540.0)

    caption_width = _as_float((preview or {}).get("captionWidth"), 0.0)
    if caption_width > 0 and frame_width > caption_width:
        margin_h = int(round(((frame_width - caption_width) / 2.0) * scale_x))
    else:
        margin_h = int(round(18 * scale_x))

    if position == "top":
        css_margin = _as_float((preview or {}).get("captionTop"), 0.0)
        if css_margin <= 0:
            css_margin = _bounded(frame_height * 0.08, 28.0, 84.0) if frame_height else 70.0
    elif position == "middle":
        css_margin = 0.0
    else:
        css_margin = _as_float((preview or {}).get("captionBottom"), 0.0)
        if css_margin <= 0:
            css_margin = _bounded(frame_height * 0.09, 34.0, 100.0) if frame_height else 62.0

    margin_v = int(round(css_margin * scale_y)) if position != "middle" else 0
    return max(20, margin_h), max(0, margin_v)


def build_ass_subtitles(
    lines: list[dict],
    *,
    start: float,
    length: float,
    offset: float,
    width: int,
    height: int,
    font: str,
    size: int,
    position: str,
    color: str,
    style: str,
    margin_h: Optional[int] = None,
    margin_v: Optional[int] = None,
) -> str:
    alignment = {"top": 8, "middle": 5, "bottom": 2}.get(position, 2)
    if margin_h is None:
        margin_h = 80
    if margin_v is None:
        margin_v = 130 if position == "top" else 80 if position == "middle" else 150
    font_name = ASS_FONTS.get(font, "Arial")
    primary = ASS_COLORS.get(color, ASS_COLORS["white"])
    border_style = 3 if style == "boxed" else 1
    if style == "boxed":
        outline = max(10, int(round(size * 0.2)))
    elif style == "minimal":
        outline = max(2, int(round(size * 0.035)))
    else:
        outline = max(4, int(round(size * 0.065)))
    shadow = 0 if style == "minimal" else max(1, int(round(size * 0.018)))
    back_colour = "&H760C0C08" if style == "boxed" else "&H00000000"
    outline_colour = "&HA0000000" if style == "minimal" else "&HCC000000"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{size},{primary},{primary},{outline_colour},{back_colour},1,0,0,0,100,100,0,0,{border_style},{outline},{shadow},{alignment},{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for event in subtitle_events_for_clip(lines, start=start, length=length, offset=offset):
        events.append(
            f"Dialogue: 0,{_ass_time(event['start'])},{_ass_time(event['end'])},Default,,0,0,0,,{_ass_text(event['text'])}"
        )
    return header + "\n".join(events) + "\n"


def export_studio_clip(session_id: str, options: dict) -> tuple[str, Path]:
    session = _studio_session(session_id)
    video_path = Path(session["videoPath"])
    lines = session["song"].get("lines") or []
    video_duration = _as_float(session["video"].get("duration"), 0.0)

    start = max(0.0, _as_float(options.get("start"), 0.0))
    length = _bounded(_as_float(options.get("length"), MAX_STUDIO_CLIP_SECONDS), 1.0, MAX_STUDIO_CLIP_SECONDS)
    if video_duration > 0:
        start = min(start, max(0.0, video_duration - 0.5))
        length = min(length, max(1.0, video_duration - start))

    layout = options.get("format") if options.get("format") in {"vertical", "horizontal"} else "vertical"
    width, height = (1080, 1920) if layout == "vertical" else (1920, 1080)
    subtitle = options.get("subtitle") if isinstance(options.get("subtitle"), dict) else {}
    size = int(_bounded(_as_float(subtitle.get("size"), 58), 24, 120))
    preview = subtitle.get("preview") if isinstance(subtitle.get("preview"), dict) else {}
    offset = _bounded(
        _as_float(subtitle.get("offset"), 0.0),
        MIN_STUDIO_SYNC_OFFSET,
        MAX_STUDIO_SYNC_OFFSET,
    )
    position = subtitle.get("position") if subtitle.get("position") in {"top", "middle", "bottom"} else "bottom"
    color = subtitle.get("color") if subtitle.get("color") in ASS_COLORS else "white"
    style = subtitle.get("style") if subtitle.get("style") in {"boxed", "karaoke", "minimal"} else "boxed"
    font = subtitle.get("font") if subtitle.get("font") in ASS_FONTS else "Inter"

    export_id = uuid.uuid4().hex[:12]
    out_path = STUDIO_CACHE_DIR / f"tiktok-studio-{export_id}.mp4"
    subtitle_events = subtitle_events_for_clip(lines, start=start, length=length, offset=offset)
    overlays = render_subtitle_overlay_images(
        subtitle_events,
        export_id=export_id,
        width=width,
        height=height,
        layout=layout,
        font=font,
        size=size,
        position=position,
        color=color,
        style=style,
        preview=preview,
    )

    overlay_by_window = {
        (round(event_start, 3), round(event_end, 3)): (overlay_path, mask_path)
        for overlay_path, mask_path, event_start, event_end in overlays
    }
    segments = timeline_segments_for_export(subtitle_events, length)
    segment_paths: list[Path] = []
    base_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,setpts=PTS-STARTPTS"
    )
    ffmpeg = _ffmpeg_exe()

    try:
        for index, segment in enumerate(segments):
            segment_start = _as_float(segment["start"], 0.0)
            segment_end = _as_float(segment["end"], segment_start)
            segment_length = max(0.05, segment_end - segment_start)
            segment_path = STUDIO_CACHE_DIR / f"segment-{export_id}-{index:03d}.mp4"
            segment_paths.append(segment_path)
            overlay_event = segment.get("overlay")
            overlay_path = None
            mask_path = None
            if isinstance(overlay_event, dict):
                key = (
                    round(_as_float(overlay_event.get("start"), 0.0), 3),
                    round(_as_float(overlay_event.get("end"), 0.0), 3),
                )
                overlay_pair = overlay_by_window.get(key)
                if overlay_pair:
                    overlay_path, mask_path = overlay_pair

            cmd = [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-threads",
                "2",
                "-filter_threads",
                "1",
                "-ss",
                f"{start + segment_start:.3f}",
                "-t",
                f"{segment_length:.3f}",
                "-i",
                str(video_path),
            ]
            if overlay_path:
                cmd.extend(["-loop", "1", "-t", f"{segment_length:.3f}", "-i", str(overlay_path)])
                if mask_path and mask_path.exists():
                    cmd.extend(["-loop", "1", "-t", f"{segment_length:.3f}", "-i", str(mask_path)])
                    blur_radius = max(4, int(round(10 * min(width / max(_as_float(preview.get("frameWidth"), 384.0), 1.0), height / max(_as_float(preview.get("frameHeight"), 682.667), 1.0)))))
                    filter_complex = (
                        f"[0:v]{base_filter},split=2[clean][blur_src];"
                        f"[blur_src]boxblur={blur_radius}:1[blurred];"
                        "[2:v]format=gray,setsar=1[mask];"
                        "[blurred][mask]alphamerge[blurred_box];"
                        "[clean][blurred_box]overlay=0:0:shortest=1[under];"
                        "[1:v]format=rgba,setpts=PTS-STARTPTS[ov];"
                        "[under][ov]overlay=0:0:shortest=1[v]"
                    )
                else:
                    filter_complex = (
                        f"[0:v]{base_filter}[base];"
                        "[1:v]format=rgba,setpts=PTS-STARTPTS[ov];"
                        "[base][ov]overlay=0:0:shortest=1[v]"
                    )
                cmd.extend(["-filter_complex", filter_complex, "-map", "[v]"])
            else:
                cmd.extend(["-vf", base_filter, "-map", "0:v:0"])
            cmd.extend([
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                str(segment_path),
            ])
            _run_export_command(cmd, timeout=180)
            if not segment_path.exists() or segment_path.stat().st_size == 0:
                raise engine.AudioPlaybackError("FFmpeg no generó un segmento del clip.")

        concat_path = STUDIO_CACHE_DIR / f"concat-{export_id}.txt"
        video_only_path = STUDIO_CACHE_DIR / f"video-only-{export_id}.mp4"
        concat_lines = [f"file '{path.resolve().as_posix()}'" for path in segment_paths]
        concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        _run_export_command([
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            str(video_only_path),
        ], timeout=180)
        if not video_only_path.exists() or video_only_path.stat().st_size == 0:
            raise engine.AudioPlaybackError("FFmpeg no pudo unir los segmentos del clip.")

        _run_export_command([
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_only_path),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{length:.3f}",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_path),
        ], timeout=180)
    except Exception:
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        raise
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise engine.AudioPlaybackError("FFmpeg terminó, pero no generó el MP4 final.")
    STUDIO_EXPORTS[export_id] = out_path
    return export_id, out_path


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #
def _no_cache(resp: Response) -> Response:
    # Evita que el navegador sirva una versión vieja del frontend tras un cambio.
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


@app.route("/")
def index() -> Response:
    ensure_frontend_build()
    if not (FRONTEND_DIST_DIR / "index.html").exists():
        return frontend_build_missing_response()
    return _no_cache(send_from_directory(_frontend_root(), "index.html"))


@app.route("/web/<path:filename>")
def static_files(filename: str) -> Response:
    ensure_frontend_build()
    static_root = _frontend_root()
    if (static_root / filename).exists():
        return _no_cache(send_from_directory(static_root, filename))
    return _no_cache(send_from_directory(STATIC_DIR, filename))


@app.route("/api/v1/docs/openapi.json")
def api_v1_openapi() -> Response:
    return jsonify(_openapi_spec())


@app.route("/api/v1/docs")
def api_v1_docs() -> Response:
    return Response(
        """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Terminal Karaoke API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>SwaggerUIBundle({ url: "/api/v1/docs/openapi.json", dom_id: "#swagger-ui" });</script>
</body>
</html>""",
        mimetype="text/html",
    )


@app.route("/api/v1/songs")
@app.route("/api/song")
def api_song() -> Response:
    artist = (request.args.get("artist") or "").strip()
    title = (request.args.get("title") or "").strip()
    payload, status = _song_payload(artist, title)
    if status >= 400:
        return api_error(payload.get("error", "No pude cargar la canción."), status=status)
    return api_success(payload, code=1, message="Canción resuelta.")


@app.route("/api/v1/covers")
@app.route("/api/cover")
def api_cover() -> Response:
    """Proxy de la carátula (mismo origen) para poder muestrear sus colores
    en un canvas sin problemas de CORS."""
    url = (request.args.get("u") or "").strip()
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    allowed = host.endswith("mzstatic.com") or host.endswith("apple.com")
    if parsed.scheme != "https" or not allowed:
        return api_error("URL de carátula no permitida.", status=400)
    req = urllib.request.Request(url, headers={"User-Agent": engine.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
    except (urllib.error.URLError, TimeoutError):
        return api_error("No pude descargar la carátula.", status=502)
    resp = Response(data, mimetype=content_type)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/api/v1/songs/audio")
@app.route("/api/audio")
def api_audio() -> Response:
    artist = (request.args.get("artist") or "").strip()
    title = (request.args.get("title") or "").strip()
    if not artist or not title:
        return api_error("Faltan 'artist' y 'title'.", status=400)
    try:
        path = engine.download_audio_track(artist, title)
    except engine.AudioPlaybackError as exc:
        return api_error(str(exc), status=503)
    except Exception as exc:  # pragma: no cover
        return api_error(f"No pude preparar el audio: {exc}", status=500)
    # conditional=True habilita peticiones Range para hacer seek en el <audio>.
    return send_file(path, mimetype="audio/mpeg", conditional=True)


@app.route("/api/v1/studio-sessions", methods=["POST"])
@app.route("/api/studio/prepare", methods=["POST"])
def api_studio_prepare() -> Response:
    payload, status = _prepare_studio_payload(_json_payload())
    if status >= 400:
        return api_error(payload.get("error", "No pude preparar el estudio."), status=status)
    return api_success(payload, code=2, status=status, message="Sesión de estudio creada.")


@app.route("/api/v1/studio-sessions/<session_id>/video")
@app.route("/api/studio/video/<session_id>")
def api_studio_video(session_id: str) -> Response:
    try:
        session = _studio_session(session_id)
    except (KeyError, FileNotFoundError) as exc:
        return api_error(str(exc), status=404)
    return send_file(Path(session["videoPath"]), mimetype="video/mp4", conditional=True)


@app.route("/api/v1/studio-sessions/<session_id>/sync", methods=["POST"])
@app.route("/api/studio/sync", methods=["POST"])
def api_studio_sync(session_id: str = "") -> Response:
    if not session_id:
        session_id = (_json_payload().get("sessionId") or "").strip()
    payload, status = _sync_studio_payload(session_id)
    if status >= 400:
        return api_error(payload.get("error", "No pude sincronizar el audio."), status=status)
    return api_success(payload, code=3, message="Sincronización aplicada.")


@app.route("/api/v1/studio-sessions/<session_id>/exports", methods=["POST"])
@app.route("/api/studio/export", methods=["POST"])
def api_studio_export(session_id: str = "") -> Response:
    payload = _json_payload()
    if not session_id:
        session_id = (payload.get("sessionId") or "").strip()
    result, status = _export_studio_payload(session_id, payload)
    if status >= 400:
        return api_error(result.get("error", "No pude exportar el clip."), status=status)
    return api_success(result, code=4, status=status, message="Export creado.")


@app.route("/api/v1/studio-exports/<export_id>/file")
@app.route("/api/studio/download/<export_id>")
def api_studio_download(export_id: str) -> Response:
    path = STUDIO_EXPORTS.get(export_id)
    if not path or not path.exists():
        return api_error("No encontré ese export. Vuelve a exportarlo.", status=404)
    return send_file(path, mimetype="video/mp4", as_attachment=True, download_name=path.name)


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
