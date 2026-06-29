import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { coverProxyUrl, createStudioSession, exportStudioSession, loadSong, songAudioUrl, syncStudioSession } from "./api/client.js";
import { DEFAULT_PALETTE, INITIAL_STUDIO, LYRIC_FONTS, clamp, formatTime } from "./constants.js";
import { SearchBar } from "./components/molecules/SearchBar.jsx";
import { KaraokePlayer } from "./components/organisms/KaraokePlayer.jsx";
import { StudioWorkspace } from "./components/organisms/StudioWorkspace.jsx";
import { Welcome } from "./components/organisms/Welcome.jsx";
import { Toast } from "./components/atoms/Toast.jsx";
import { StageTemplate } from "./components/templates/StageTemplate.jsx";

const INITIAL_STUDIO_FORM = {
  video: "",
  artist: "",
  title: "",
};

function applyPalette(palette) {
  const root = document.documentElement.style;
  root.setProperty("--c1", palette[0]);
  root.setProperty("--c2", palette[1]);
  root.setProperty("--c3", palette[2]);
}

function extractPalette(img) {
  try {
    const size = 36;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, size, size);
    const data = ctx.getImageData(0, 0, size, size).data;
    const buckets = new Map();

    for (let i = 0; i < data.length; i += 4) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const a = data[i + 3];
      if (a < 128) continue;
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const lum = (max + min) / 2;
      if (lum < 24 || lum > 238) continue;
      const sat = max === 0 ? 0 : (max - min) / max;
      const key = `${r >> 5},${g >> 5},${b >> 5}`;
      const cur = buckets.get(key) || { r: 0, g: 0, b: 0, n: 0, sat: 0 };
      cur.r += r;
      cur.g += g;
      cur.b += b;
      cur.n += 1;
      cur.sat += sat;
      buckets.set(key, cur);
    }

    if (!buckets.size) return null;
    const colors = [...buckets.values()].map((color) => ({
      r: Math.round(color.r / color.n),
      g: Math.round(color.g / color.n),
      b: Math.round(color.b / color.n),
      score: color.n * (1 + (color.sat / color.n) * 2.2),
    }));
    colors.sort((a, b) => b.score - a.score);
    const top = colors.slice(0, 3);
    while (top.length < 3) top.push(top[top.length - 1] || { r: 60, g: 60, b: 72 });
    return top.map((color) => `rgb(${color.r}, ${color.g}, ${color.b})`);
  } catch (_err) {
    return null;
  }
}

function activeLineIndex(lines, time) {
  let idx = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (Number(lines[i].time) <= time + 0.01) idx = i;
    else break;
  }
  return idx;
}

function normalizeStudio(next, durationOverride) {
  const duration = Number.isFinite(durationOverride) ? durationOverride : Number(next.duration || 0);
  const maxClipSeconds = Number(next.maxClipSeconds || 58);
  const lengthMin = duration > 0 && duration < 5 ? 1 : 5;
  const lengthMax = Math.max(1, Math.floor(Math.min(maxClipSeconds, duration || maxClipSeconds)));
  const clipLength = clamp(Number(next.clipLength || lengthMax), Math.min(lengthMin, lengthMax), lengthMax);
  const maxStart = duration > 0 ? Math.max(0, duration - clipLength) : 0;
  const clipStart = clamp(Number(next.clipStart || 0), 0, maxStart);

  return {
    ...next,
    duration,
    maxClipSeconds,
    clipLength,
    clipStart,
    size: Number(next.size || INITIAL_STUDIO.size),
    offset: Number(next.offset || 0),
  };
}

export function App() {
  const [mode, setMode] = useState("karaoke");
  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [karaokeReady, setKaraokeReady] = useState(false);
  const [song, setSong] = useState(null);
  const [lines, setLines] = useState([]);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [hasAudio, setHasAudio] = useState(false);
  const [audioNote, setAudioNote] = useState("");
  const [playingState, setPlayingState] = useState("paused");
  const [volume, setVolume] = useState(0.85);
  const [coverUrl, setCoverUrl] = useState("");
  const [coverReady, setCoverReady] = useState(false);
  const [backgroundUrl, setBackgroundUrl] = useState("");
  const [backgroundReady, setBackgroundReady] = useState(false);
  const [fontIndex, setFontIndex] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const [studioForm, setStudioForm] = useState(INITIAL_STUDIO_FORM);
  const [studio, setStudio] = useState(INITIAL_STUDIO);
  const [studioStatus, setStudioStatus] = useState("");
  const [studioSyncNote, setStudioSyncNote] = useState("Compara el audio del video contra la pista de la canción.");
  const [studioVideoTitle, setStudioVideoTitle] = useState("58s max");
  const [studioVideoSrc, setStudioVideoSrc] = useState("");
  const [studioCurrentTime, setStudioCurrentTime] = useState(0);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [preparingStudio, setPreparingStudio] = useState(false);

  const audioRef = useRef(null);
  const videoRef = useRef(null);
  const frameRef = useRef(null);
  const captionRef = useRef(null);
  const rafRef = useRef(null);
  const studioRafRef = useRef(null);
  const toastTimerRef = useRef(null);
  const manualStartRef = useRef(0);
  const manualOffsetRef = useRef(0);
  const intendPlayRef = useRef(false);
  const playingRef = useRef(false);
  const hasAudioRef = useRef(false);
  const durationRef = useRef(0);
  const linesRef = useRef([]);
  const studioRef = useRef(studio);
  const volumeRef = useRef(volume);
  const previousStudioClipStartRef = useRef(INITIAL_STUDIO.clipStart);

  const activeIndex = useMemo(() => activeLineIndex(lines, currentTime), [lines, currentTime]);

  useEffect(() => {
    document.body.dataset.mode = mode;
  }, [mode]);

  useEffect(() => {
    linesRef.current = lines;
  }, [lines]);

  useEffect(() => {
    durationRef.current = duration;
  }, [duration]);

  useEffect(() => {
    hasAudioRef.current = hasAudio;
  }, [hasAudio]);

  useEffect(() => {
    studioRef.current = studio;
  }, [studio]);

  const showToast = useCallback((message) => {
    setToastMessage(message);
    window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => setToastMessage(""), 3800);
  }, []);

  const setPlaybackUi = useCallback((nextState) => {
    playingRef.current = nextState === "playing";
    setPlayingState(nextState);
  }, []);

  const updateKaraokeTime = useCallback((time) => {
    const safe = clamp(Number(time) || 0, 0, Math.max(durationRef.current || 0, 0));
    setCurrentTime(safe);
  }, []);

  const karaokeTime = useCallback(() => {
    const audio = audioRef.current;
    if (hasAudioRef.current && audio) return audio.currentTime;
    if (!playingRef.current) return manualOffsetRef.current;
    return manualOffsetRef.current + (performance.now() - manualStartRef.current) / 1000;
  }, []);

  const stopKaraokeLoop = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  }, []);

  const startKaraokeLoop = useCallback(() => {
    stopKaraokeLoop();
    const tick = () => {
      updateKaraokeTime(karaokeTime());
      const audio = audioRef.current;
      const running = hasAudioRef.current ? Boolean(audio && !audio.paused) : playingRef.current;
      if (running) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        rafRef.current = null;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [karaokeTime, stopKaraokeLoop, updateKaraokeTime]);

  const stopPlayback = useCallback(() => {
    intendPlayRef.current = false;
    audioRef.current?.pause();
    setPlaybackUi("paused");
    stopKaraokeLoop();
  }, [setPlaybackUi, stopKaraokeLoop]);

  const playAudio = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    intendPlayRef.current = true;
    setPlaybackUi(audio.readyState >= 3 ? "playing" : "loading");
    audio.play().catch(() => {
      intendPlayRef.current = false;
      setPlaybackUi("paused");
      showToast("Pulsa play para empezar.");
    });
    startKaraokeLoop();
  }, [setPlaybackUi, showToast, startKaraokeLoop]);

  const startPlayback = useCallback(() => {
    if (hasAudioRef.current) {
      playAudio();
      return;
    }
    manualStartRef.current = performance.now();
    setPlaybackUi("playing");
    startKaraokeLoop();
  }, [playAudio, setPlaybackUi, startKaraokeLoop]);

  const seekTo = useCallback((time) => {
    const target = clamp(Number(time) || 0, 0, durationRef.current || 0);
    if (hasAudioRef.current && audioRef.current) {
      audioRef.current.currentTime = target;
    } else {
      manualOffsetRef.current = target;
      manualStartRef.current = performance.now();
    }
    updateKaraokeTime(target);
  }, [updateKaraokeTime]);

  const togglePlayback = useCallback(() => {
    const audio = audioRef.current;
    if (hasAudioRef.current && audio) {
      if (audio.paused) {
        playAudio();
      } else {
        intendPlayRef.current = false;
        audio.pause();
      }
      return;
    }

    if (playingRef.current) {
      manualOffsetRef.current = karaokeTime();
      setPlaybackUi("paused");
      stopKaraokeLoop();
    } else {
      manualStartRef.current = performance.now();
      setPlaybackUi("playing");
      startKaraokeLoop();
    }
  }, [karaokeTime, playAudio, setPlaybackUi, startKaraokeLoop, stopKaraokeLoop]);

  const stopStudioPreview = useCallback(() => {
    if (studioRafRef.current) cancelAnimationFrame(studioRafRef.current);
    studioRafRef.current = null;
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
    }
  }, []);

  const switchMode = useCallback((nextMode) => {
    setMode(nextMode);
    if (nextMode === "studio") {
      stopPlayback();
      setStudioForm((form) => ({
        ...form,
        artist: form.artist || artist,
        title: form.title || title,
      }));
    } else {
      stopStudioPreview();
    }
  }, [artist, stopPlayback, stopStudioPreview, title]);

  const applyLyricFont = useCallback((index) => {
    const normalized = ((index % LYRIC_FONTS.length) + LYRIC_FONTS.length) % LYRIC_FONTS.length;
    const font = LYRIC_FONTS[normalized];
    document.documentElement.style.setProperty("--lyric-font", font.stack);
    setFontIndex(normalized);
    try {
      localStorage.setItem("lyricFont", String(normalized));
    } catch (_err) {
      // localStorage can be unavailable in private contexts.
    }
  }, []);

  const setCover = useCallback((url) => {
    if (!url) {
      setCoverUrl("");
      setCoverReady(false);
      setBackgroundUrl("");
      setBackgroundReady(false);
      applyPalette(DEFAULT_PALETTE);
      return;
    }
    const proxied = coverProxyUrl(url);
    setCoverUrl(proxied);
    setCoverReady(false);
    setBackgroundReady(false);
  }, []);

  const handleCoverLoad = useCallback((event) => {
    setCoverReady(true);
    setBackgroundUrl(coverUrl);
    setBackgroundReady(true);
    applyPalette(extractPalette(event.currentTarget) || DEFAULT_PALETTE);
  }, [coverUrl]);

  const handleCoverError = useCallback(() => {
    setCoverReady(false);
    setBackgroundReady(false);
    applyPalette(DEFAULT_PALETTE);
  }, []);

  const handleLoadSong = useCallback(async (artistValue = artist, titleValue = title) => {
    const requestedArtist = artistValue.trim();
    const requestedTitle = titleValue.trim();
    if (!requestedArtist || !requestedTitle) {
      showToast("Escribe un artista y una canción.");
      return;
    }

    setLoading(true);
    stopPlayback();

    try {
      const data = await loadSong(requestedArtist, requestedTitle);
      const nextLines = Array.isArray(data.lines) ? data.lines : [];
      const nextDuration = Number(data.duration || (nextLines.length ? Number(nextLines[nextLines.length - 1].time) + 4 : 0));

      linesRef.current = nextLines;
      durationRef.current = nextDuration;
      manualOffsetRef.current = 0;
      manualStartRef.current = performance.now();
      setLines(nextLines);
      setDuration(nextDuration);
      setCurrentTime(0);
      setSong({
        title: data.title || requestedTitle,
        artist: data.artist || requestedArtist,
        mode: data.mode || "",
      });
      setCover(data.cover);

      if (data.audioAvailable && audioRef.current) {
        hasAudioRef.current = true;
        setHasAudio(true);
        setAudioNote("");
        audioRef.current.src = songAudioUrl(requestedArtist, requestedTitle);
        audioRef.current.load();
      } else {
        hasAudioRef.current = false;
        setHasAudio(false);
        setAudioNote("Audio no disponible (instala yt-dlp e imageio-ffmpeg). La letra avanza con el reloj.");
      }

      setKaraokeReady(true);
      setMode("karaoke");
      requestAnimationFrame(startPlayback);
    } catch (err) {
      showToast(err.message || "No se pudo cargar la canción.");
    } finally {
      setLoading(false);
    }
  }, [artist, setCover, showToast, startPlayback, stopPlayback, title]);

  const handleSuggestion = useCallback((suggestion) => {
    setArtist(suggestion.artist);
    setTitle(suggestion.title);
    handleLoadSong(suggestion.artist, suggestion.title);
  }, [handleLoadSong]);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {
        showToast("Tu navegador no permitió pantalla completa.");
      });
      return;
    }
    document.exitFullscreen?.();
  }, [showToast]);

  const studioDuration = useCallback((studioValue = studioRef.current) => {
    const video = videoRef.current;
    if (video && Number.isFinite(video.duration) && video.duration > 0) return video.duration;
    return Number(studioValue.duration || 0);
  }, []);

  const handleStudioChange = useCallback((nextStudio) => {
    setStudio((previous) => normalizeStudio({ ...previous, ...nextStudio }, studioDuration(nextStudio)));
    if (downloadUrl) setDownloadUrl("");
  }, [downloadUrl, studioDuration]);

  useEffect(() => {
    const video = videoRef.current;
    const changed = Math.abs(previousStudioClipStartRef.current - studio.clipStart) > 0.001;
    previousStudioClipStartRef.current = studio.clipStart;
    if (!video || !studio.prepared || !changed) return;
    stopStudioPreview();
    video.currentTime = studio.clipStart;
    setStudioCurrentTime(studio.clipStart);
  }, [stopStudioPreview, studio.clipStart, studio.prepared]);

  const startStudioPreviewLoop = useCallback(() => {
    if (studioRafRef.current) cancelAnimationFrame(studioRafRef.current);
    const tick = () => {
      const video = videoRef.current;
      const activeStudio = studioRef.current;
      if (!video) return;
      const clipEnd = activeStudio.clipStart + activeStudio.clipLength;
      if (video.currentTime >= clipEnd) {
        video.pause();
        video.currentTime = clipEnd;
        setStudioCurrentTime(clipEnd);
      } else {
        setStudioCurrentTime(video.currentTime);
      }
      if (!video.paused) {
        studioRafRef.current = requestAnimationFrame(tick);
      } else {
        studioRafRef.current = null;
      }
    };
    studioRafRef.current = requestAnimationFrame(tick);
  }, []);

  const handlePrepareStudio = useCallback(async () => {
    const video = studioForm.video.trim();
    const formArtist = studioForm.artist.trim();
    const formTitle = studioForm.title.trim();
    if (!video || !formArtist || !formTitle) {
      showToast("Completa video, artista y canción.");
      return;
    }

    setPreparingStudio(true);
    setStudioStatus("Preparando video");
    setStudioSyncNote("Compara el audio del video contra la pista de la canción.");
    setDownloadUrl("");
    stopStudioPreview();

    try {
      const data = await createStudioSession({ video, artist: formArtist, title: formTitle });
      const nextLines = Array.isArray(data.song?.lines) ? data.song.lines : [];
      const nextDuration = Number(data.video?.duration || data.song?.duration || 0);
      const maxClipSeconds = Number(data.maxClipSeconds || 58);
      const clipLength = Math.min(maxClipSeconds, Math.max(5, Math.floor(nextDuration || maxClipSeconds)));

      setStudioVideoSrc(data.videoUrl || "");
      setStudioVideoTitle(data.video?.title || "Video preparado");
      setStudioCurrentTime(0);
      setStudio(normalizeStudio({
        ...INITIAL_STUDIO,
        sessionId: data.sessionId || "",
        lines: nextLines,
        duration: nextDuration,
        maxClipSeconds,
        clipLength,
        lyricMode: data.song?.mode || "",
        prepared: true,
      }, nextDuration));
      setStudioStatus(`${data.song?.title || "Canción"} - ${data.song?.artist || "Artista"}`);
      setStudioSyncNote(data.song?.mode === "estimado"
        ? "Letra estimada: sincroniza audio y ajusta fino si hace falta."
        : "Compara el audio del video contra la pista de la canción.");
      if (data.song?.cover) setCover(data.song.cover);
    } catch (err) {
      setStudioStatus("No se pudo preparar");
      showToast(err.message || "No se pudo preparar el estudio.");
    } finally {
      setPreparingStudio(false);
    }
  }, [setCover, showToast, stopStudioPreview, studioForm.artist, studioForm.title, studioForm.video]);

  const handleStudioMetadata = useCallback(() => {
    const durationValue = studioDuration();
    if (durationValue > 0) {
      setStudio((previous) => normalizeStudio({ ...previous, duration: durationValue }, durationValue));
    }
  }, [studioDuration]);

  const handleStudioTimeUpdate = useCallback(() => {
    if (videoRef.current) {
      setStudioCurrentTime(videoRef.current.currentTime || 0);
    }
  }, []);

  const handlePreviewStudio = useCallback(() => {
    const video = videoRef.current;
    if (!studioRef.current.prepared || !video) return;
    video.currentTime = studioRef.current.clipStart;
    setStudioCurrentTime(studioRef.current.clipStart);
    video.play().then(startStudioPreviewLoop).catch(() => {
      showToast("Pulsa play dentro del video para previsualizar.");
    });
  }, [showToast, startStudioPreviewLoop]);

  const studioPreviewMetrics = useCallback(() => {
    const frame = frameRef.current;
    const caption = captionRef.current;
    if (!frame || !caption) return {};

    const frameRect = frame.getBoundingClientRect();
    const wasHidden = caption.hidden;
    const previousVisibility = caption.style.visibility;
    if (wasHidden) {
      caption.style.visibility = "hidden";
      caption.hidden = false;
    }
    const captionRect = caption.getBoundingClientRect();
    const computed = getComputedStyle(caption);
    if (wasHidden) {
      caption.hidden = true;
      caption.style.visibility = previousVisibility;
    }

    const px = (value) => {
      const parsed = parseFloat(value);
      return Number.isFinite(parsed) ? Math.round(parsed * 100) / 100 : 0;
    };
    const fontSize = px(computed.fontSize);
    const lineHeight = computed.lineHeight === "normal" ? fontSize * 1.05 : px(computed.lineHeight);
    const text = caption.textContent || "";
    const lineCount = Math.max(1, Math.round((captionRect.height - px(computed.paddingTop) - px(computed.paddingBottom)) / Math.max(1, lineHeight)));

    return {
      frameWidth: Math.round(frameRect.width * 100) / 100,
      frameHeight: Math.round(frameRect.height * 100) / 100,
      captionWidth: Math.round((captionRect.width || parseFloat(computed.width) || 0) * 100) / 100,
      captionHeight: Math.round((captionRect.height || parseFloat(computed.height) || 0) * 100) / 100,
      captionTop: Math.round((parseFloat(computed.top) || 0) * 100) / 100,
      captionBottom: Math.round((parseFloat(computed.bottom) || 0) * 100) / 100,
      paddingTop: px(computed.paddingTop),
      paddingRight: px(computed.paddingRight),
      paddingBottom: px(computed.paddingBottom),
      paddingLeft: px(computed.paddingLeft),
      borderRadius: px(computed.borderTopLeftRadius),
      borderWidth: px(computed.borderTopWidth),
      fontSize,
      fontWeight: computed.fontWeight,
      lineHeight,
      lineCount,
      sampleText: text,
    };
  }, []);

  const handleSyncStudio = useCallback(async () => {
    const activeStudio = studioRef.current;
    if (!activeStudio.prepared || !activeStudio.sessionId) {
      showToast("Prepara el estudio antes de sincronizar.");
      return;
    }

    setStudio((previous) => ({ ...previous, syncing: true }));
    setStudioStatus("Analizando audio");
    setStudioSyncNote("Comparando la pista contra el audio del video.");

    try {
      const data = await syncStudioSession(activeStudio.sessionId);
      const offset = Number(data.offset || 0);
      const durationValue = studioDuration();
      setStudio((previous) => {
        const next = {
          ...previous,
          offset,
          lines: Array.isArray(data.lines) && data.lines.length ? data.lines : previous.lines,
          lyricMode: data.lyricMode || previous.lyricMode,
          syncing: false,
        };
        if (durationValue > 0 && offset > 0) {
          next.clipStart = clamp(offset, 0, Math.max(0, durationValue - previous.clipLength));
        }
        return normalizeStudio(next, durationValue || next.duration);
      });

      const timelinePct = Math.round(Number(data.timelineConfidence ?? data.confidence ?? 0) * 100);
      const audioOffset = Number(data.audioOffset ?? offset);
      const lyricCorrection = Number(data.lyricCorrection || 0);
      const firstCaptionAt = Number(data.firstCaptionAt || 0);
      const sourceLabel = {
        captions: "captions",
        "asr-local": "ASR local",
        audio: "audio",
      }[data.timelineSource] || data.timelineSource || "audio";
      const correctionText = lyricCorrection > 0 ? ` · inicio letra +${lyricCorrection.toFixed(1)}s` : "";
      const firstLineText = data.lyricMode === "estimado" && firstCaptionAt > 0 ? ` · primera línea ${formatTime(firstCaptionAt)}` : "";
      setStudioStatus("Sync aplicado");
      setStudioSyncNote(`${sourceLabel}: ${timelinePct}% · desfase ${offset.toFixed(1)}s · audio ${audioOffset.toFixed(1)}s${correctionText}${firstLineText}`);
      showToast("Letra sincronizada con el audio del video.");
    } catch (err) {
      setStudio((previous) => ({ ...previous, syncing: false }));
      setStudioStatus("Sync falló");
      setStudioSyncNote("No hubo coincidencia clara. Ajusta el desfase manualmente.");
      showToast(err.message || "No se pudo sincronizar el audio.");
    }
  }, [showToast, studioDuration]);

  const handleExportStudio = useCallback(async () => {
    const activeStudio = normalizeStudio(studioRef.current, studioDuration());
    if (!activeStudio.prepared || !activeStudio.sessionId) {
      showToast("Prepara un video antes de exportar.");
      return;
    }

    setStudio((previous) => ({ ...normalizeStudio(previous, studioDuration()), exporting: true }));
    setStudioStatus("Exportando MP4");
    setDownloadUrl("");

    try {
      const data = await exportStudioSession(activeStudio.sessionId, {
        start: activeStudio.clipStart,
        length: activeStudio.clipLength,
        format: activeStudio.format,
        subtitle: {
          font: activeStudio.font,
          position: activeStudio.position,
          style: activeStudio.style,
          color: activeStudio.color,
          size: activeStudio.size,
          offset: activeStudio.offset,
          preview: studioPreviewMetrics(),
        },
      });
      setDownloadUrl(data.downloadUrl || "");
      setStudioStatus("Export listo");
      showToast("MP4 listo para descargar.");
    } catch (err) {
      setStudioStatus("Export falló");
      showToast(err.message || "No se pudo exportar el clip.");
    } finally {
      setStudio((previous) => ({ ...previous, exporting: false }));
    }
  }, [showToast, studioDuration, studioPreviewMetrics]);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "auto";
    audio.volume = volumeRef.current;
    audioRef.current = audio;

    const onAudioPlay = () => {
      if (audio.readyState < 3) setPlaybackUi("loading");
    };
    const onAudioPlaying = () => {
      setPlaybackUi("playing");
      startKaraokeLoop();
    };
    const onAudioWaiting = () => {
      if (intendPlayRef.current) setPlaybackUi("loading");
    };
    const onAudioCanPlay = () => {
      if (intendPlayRef.current && audio.paused) audio.play().catch(() => {});
    };
    const onAudioPause = () => {
      if (intendPlayRef.current && audio.readyState < 3) return;
      setPlaybackUi("paused");
    };
    const onAudioLoadedMetadata = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        durationRef.current = audio.duration;
        setDuration(audio.duration);
      }
    };
    const onAudioEnded = () => {
      intendPlayRef.current = false;
      setPlaybackUi("paused");
    };
    const onAudioError = () => {
      if (hasAudioRef.current) {
        showToast("No pude reproducir el audio; la letra avanza con el reloj.");
        hasAudioRef.current = false;
        setHasAudio(false);
        setAudioNote("Audio no disponible. La letra avanza con el reloj.");
      }
    };

    audio.addEventListener("play", onAudioPlay);
    audio.addEventListener("playing", onAudioPlaying);
    audio.addEventListener("waiting", onAudioWaiting);
    audio.addEventListener("canplay", onAudioCanPlay);
    audio.addEventListener("pause", onAudioPause);
    audio.addEventListener("loadedmetadata", onAudioLoadedMetadata);
    audio.addEventListener("ended", onAudioEnded);
    audio.addEventListener("error", onAudioError);

    return () => {
      audio.pause();
      audio.removeEventListener("play", onAudioPlay);
      audio.removeEventListener("playing", onAudioPlaying);
      audio.removeEventListener("waiting", onAudioWaiting);
      audio.removeEventListener("canplay", onAudioCanPlay);
      audio.removeEventListener("pause", onAudioPause);
      audio.removeEventListener("loadedmetadata", onAudioLoadedMetadata);
      audio.removeEventListener("ended", onAudioEnded);
      audio.removeEventListener("error", onAudioError);
      audioRef.current = null;
    };
  }, [setPlaybackUi, showToast, startKaraokeLoop]);

  useEffect(() => {
    volumeRef.current = volume;
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  useEffect(() => {
    let saved = Number.NaN;
    try {
      saved = parseInt(localStorage.getItem("lyricFont"), 10);
    } catch (_err) {
      saved = Number.NaN;
    }
    applyLyricFont(Number.isNaN(saved) ? 0 : saved);
  }, [applyLyricFont]);

  useEffect(() => {
    const onFullscreenChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
      if (mode === "studio") {
        if (event.code === "Escape") switchMode("karaoke");
        return;
      }
      if (event.code === "Space") {
        event.preventDefault();
        togglePlayback();
      }
      if (event.code === "ArrowRight") seekTo(karaokeTime() + 5);
      if (event.code === "ArrowLeft") seekTo(karaokeTime() - 5);
      if (event.code === "KeyF") toggleFullscreen();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [karaokeTime, mode, seekTo, switchMode, toggleFullscreen, togglePlayback]);

  useEffect(() => () => {
    window.clearTimeout(toastTimerRef.current);
    stopKaraokeLoop();
    if (studioRafRef.current) cancelAnimationFrame(studioRafRef.current);
  }, [stopKaraokeLoop]);

  return (
    <StageTemplate imageUrl={backgroundUrl} imageReady={backgroundReady}>
      <SearchBar
        mode={mode}
        onModeChange={switchMode}
        artist={artist}
        title={title}
        onArtistChange={setArtist}
        onTitleChange={setTitle}
        onLoad={() => handleLoadSong()}
        loading={loading}
        fontIndex={fontIndex}
        onFontChange={applyLyricFont}
        fullscreen={fullscreen}
        onFullscreen={toggleFullscreen}
      />
      {mode === "karaoke" && !karaokeReady ? <Welcome onSuggestion={handleSuggestion} /> : null}
      <KaraokePlayer
        hidden={mode !== "karaoke" || !karaokeReady}
        song={song}
        lines={lines}
        activeIndex={activeIndex}
        coverUrl={coverUrl}
        coverReady={coverReady}
        audioNote={audioNote}
        currentTime={currentTime}
        duration={duration}
        playingState={playingState}
        volume={volume}
        onLineClick={seekTo}
        onSeek={seekTo}
        onToggle={togglePlayback}
        onBack={() => seekTo(karaokeTime() - 5)}
        onForward={() => seekTo(karaokeTime() + 5)}
        onVolumeChange={setVolume}
        onCoverLoad={handleCoverLoad}
        onCoverError={handleCoverError}
      />
      <StudioWorkspace
        hidden={mode !== "studio"}
        form={studioForm}
        preparing={preparingStudio}
        studio={studio}
        status={studioStatus}
        syncNote={studioSyncNote}
        videoTitle={studioVideoTitle}
        videoSrc={studioVideoSrc}
        currentTime={studioCurrentTime}
        downloadUrl={downloadUrl}
        videoRef={videoRef}
        frameRef={frameRef}
        captionRef={captionRef}
        onFormChange={setStudioForm}
        onPrepare={handlePrepareStudio}
        onStudioChange={handleStudioChange}
        onSync={handleSyncStudio}
        onPreview={handlePreviewStudio}
        onExport={handleExportStudio}
        onVideoMetadata={handleStudioMetadata}
        onVideoTimeUpdate={handleStudioTimeUpdate}
        onVideoPlay={startStudioPreviewLoop}
        onVideoPause={handleStudioTimeUpdate}
      />
      <Toast message={toastMessage} />
    </StageTemplate>
  );
}
