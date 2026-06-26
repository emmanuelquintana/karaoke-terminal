"use strict";

const $ = (id) => document.getElementById(id);

const el = {
  bgImage: $("bgImage"),
  searchbar: $("searchbar"),
  artist: $("artist"),
  title: $("title"),
  loadBtn: $("loadBtn"),
  loadLabel: document.querySelector(".load-label"),
  spinner: document.querySelector(".spinner"),
  fsBtn: $("fsBtn"),
  icFsOpen: document.querySelector(".ic-fs-open"),
  icFsClose: document.querySelector(".ic-fs-close"),
  fontBtn: $("fontBtn"),
  fontMenu: $("fontMenu"),
  fontCurrent: $("fontCurrent"),
  fontPicker: $("fontPicker"),
  welcome: $("welcome"),
  suggestions: $("suggestions"),
  player: $("player"),
  cover: $("cover"),
  coverFallback: $("coverFallback"),
  songTitle: $("songTitle"),
  songArtist: $("songArtist"),
  songMode: $("songMode"),
  curTime: $("curTime"),
  durTime: $("durTime"),
  track: $("track"),
  trackFill: $("trackFill"),
  trackKnob: $("trackKnob"),
  playBtn: $("playBtn"),
  icPlay: document.querySelector(".ic-play"),
  icPause: document.querySelector(".ic-pause"),
  icLoading: document.querySelector(".ic-loading"),
  backBtn: $("backBtn"),
  fwdBtn: $("fwdBtn"),
  volume: $("volume"),
  audioNote: $("audioNote"),
  lyrics: $("lyrics"),
  toast: $("toast"),
};

const SUGGESTIONS = [
  { artist: "Coldplay", title: "Yellow" },
  { artist: "Bad Bunny", title: "Tití Me Preguntó" },
  { artist: "The Weeknd", title: "Blinding Lights" },
  { artist: "Enjambre", title: "Dulce Soledad" },
];

const state = {
  lines: [],
  lineEls: [],
  duration: 0,
  activeIndex: -1,
  hasAudio: false,
  playing: false,
  // reloj manual (cuando no hay audio)
  manualStart: 0,
  manualOffset: 0,
  rafId: null,
  seeking: false,
  intendPlay: false, // el usuario quiere reproducir (aunque el audio aún bufferee)
};

const audio = new Audio();
audio.preload = "auto";
audio.volume = parseFloat(el.volume.value);

// --------------------------------------------------------------------------- //
// Utilidades
// --------------------------------------------------------------------------- //
const fmt = (s) => {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};

let toastTimer = null;
function toast(msg) {
  el.toast.textContent = msg;
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.toast.hidden = true), 3800);
}

// --------------------------------------------------------------------------- //
// Sugerencias de bienvenida
// --------------------------------------------------------------------------- //
SUGGESTIONS.forEach((s) => {
  const chip = document.createElement("button");
  chip.className = "chip";
  chip.textContent = `${s.artist} — ${s.title}`;
  chip.onclick = () => {
    el.artist.value = s.artist;
    el.title.value = s.title;
    loadSong();
  };
  el.suggestions.appendChild(chip);
});

// --------------------------------------------------------------------------- //
// Carga de canción
// --------------------------------------------------------------------------- //
async function loadSong() {
  const artist = el.artist.value.trim();
  const title = el.title.value.trim();
  if (!artist || !title) {
    toast("Escribe un artista y una canción.");
    return;
  }

  setLoading(true);
  stopPlayback();

  try {
    const res = await fetch(`/api/song?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "No se pudo cargar la canción.");
    renderSong(data, artist, title);
  } catch (err) {
    toast(err.message);
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  el.loadBtn.disabled = on;
  el.loadLabel.hidden = on;
  el.spinner.hidden = !on;
}

function renderSong(data, artist, title) {
  state.lines = data.lines || [];
  state.duration = data.duration || (state.lines.length ? state.lines[state.lines.length - 1].time + 4 : 0);
  state.activeIndex = -1;

  // Metadatos
  el.songTitle.textContent = data.title || title;
  el.songArtist.textContent = data.artist || artist;
  el.songMode.textContent = data.mode || "";
  el.durTime.textContent = fmt(state.duration);
  el.curTime.textContent = "0:00";
  setProgress(0);

  // Carátula + fondo
  setCover(data.cover);

  // Letra
  buildLyrics();

  // Audio
  state.hasAudio = false;
  el.audioNote.hidden = true;
  if (data.audioAvailable) {
    state.hasAudio = true;
    audio.src = `/api/audio?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}`;
    audio.load();
  } else {
    el.audioNote.hidden = false;
    el.audioNote.textContent = "Audio no disponible (instala yt-dlp e imageio-ffmpeg). La letra avanza con el reloj.";
  }

  // Mostrar reproductor
  el.welcome.hidden = true;
  el.player.hidden = false;

  // Autoplay
  startPlayback();
}

function setCover(url) {
  if (!url) {
    el.cover.removeAttribute("src");
    el.cover.classList.remove("ready");
    el.coverFallback.style.display = "flex";
    el.bgImage.classList.remove("ready");
    applyPalette(DEFAULT_PALETTE);
    return;
  }
  // Servimos la carátula desde nuestro proxy (mismo origen) para poder
  // muestrear sus colores en un canvas sin que se "manche" por CORS.
  const proxied = `/api/cover?u=${encodeURIComponent(url)}`;
  el.cover.classList.remove("ready");
  el.cover.crossOrigin = "anonymous";
  el.cover.onload = () => {
    el.cover.classList.add("ready");
    el.coverFallback.style.display = "none";
    el.bgImage.style.backgroundImage = `url("${proxied}")`;
    el.bgImage.classList.add("ready");
    applyPalette(extractPalette(el.cover) || DEFAULT_PALETTE);
  };
  el.cover.onerror = () => {
    el.coverFallback.style.display = "flex";
    el.bgImage.classList.remove("ready");
    applyPalette(DEFAULT_PALETTE);
  };
  el.cover.src = proxied;
}

// ---- Paleta de color extraída de la portada -------------------------------
const DEFAULT_PALETTE = ["#3a3a44", "#20202a", "#4a4458"];

function extractPalette(img) {
  try {
    const N = 36;
    const canvas = document.createElement("canvas");
    canvas.width = N; canvas.height = N;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0, N, N);
    const data = ctx.getImageData(0, 0, N, N).data;

    const buckets = new Map();
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
      if (a < 128) continue;
      const max = Math.max(r, g, b), min = Math.min(r, g, b);
      const lum = (max + min) / 2;
      if (lum < 24 || lum > 238) continue; // descarta casi-negro/blanco
      const sat = max === 0 ? 0 : (max - min) / max;
      const key = `${r >> 5},${g >> 5},${b >> 5}`;
      const cur = buckets.get(key) || { r: 0, g: 0, b: 0, n: 0, sat: 0 };
      cur.r += r; cur.g += g; cur.b += b; cur.n += 1; cur.sat += sat;
      buckets.set(key, cur);
    }
    if (buckets.size === 0) return null;

    const colors = [...buckets.values()].map((c) => ({
      r: Math.round(c.r / c.n), g: Math.round(c.g / c.n), b: Math.round(c.b / c.n),
      score: c.n * (1 + (c.sat / c.n) * 2.2),
    }));
    colors.sort((a, b) => b.score - a.score);
    const top = colors.slice(0, 3);
    while (top.length < 3) top.push(top[top.length - 1] || { r: 60, g: 60, b: 72 });
    return top.map((c) => `rgb(${c.r}, ${c.g}, ${c.b})`);
  } catch (e) {
    return null; // canvas manchado u otro problema
  }
}

function applyPalette(palette) {
  const root = document.documentElement.style;
  root.setProperty("--c1", palette[0]);
  root.setProperty("--c2", palette[1]);
  root.setProperty("--c3", palette[2]);
}

function buildLyrics() {
  el.lyrics.innerHTML = "";
  state.lineEls = state.lines.map((line, i) => {
    const div = document.createElement("div");
    div.className = "line far";
    if (line.text === "♪" || line.text === "") div.classList.add("instrumental");
    div.textContent = line.text || "♪";
    div.onclick = () => seekTo(line.time);
    el.lyrics.appendChild(div);
    return div;
  });
  if (state.lineEls.length === 0) {
    const empty = document.createElement("div");
    empty.className = "line";
    empty.textContent = "Sin letra disponible.";
    el.lyrics.appendChild(empty);
  }
}

// --------------------------------------------------------------------------- //
// Reloj / posición
// --------------------------------------------------------------------------- //
function currentTime() {
  if (state.hasAudio) return audio.currentTime;
  if (!state.playing) return state.manualOffset;
  return state.manualOffset + (performance.now() - state.manualStart) / 1000;
}

function playAudio() {
  // Feedback inmediato: si aún no se puede reproducir (el audio se descarga
  // en el servidor la primera vez), mostramos el spinner.
  state.intendPlay = true;
  setPlayingUI(audio.readyState >= 3 ? "playing" : "loading");
  audio.play().catch(() => {
    state.intendPlay = false;
    setPlayingUI("paused");
    toast("Pulsa play para empezar ▶");
  });
  loop();
}

function startPlayback() {
  if (state.hasAudio) {
    playAudio();
  } else {
    state.manualStart = performance.now();
    setPlayingUI("playing");
    loop();
  }
}

function stopPlayback() {
  state.intendPlay = false;
  if (state.hasAudio) audio.pause();
  setPlayingUI("paused");
  if (state.rafId) cancelAnimationFrame(state.rafId);
  state.rafId = null;
}

function togglePlay() {
  if (state.hasAudio) {
    if (audio.paused) playAudio();
    else { state.intendPlay = false; audio.pause(); }
    return;
  }
  if (state.playing) {
    state.manualOffset = currentTime();
    setPlayingUI("paused");
  } else {
    state.manualStart = performance.now();
    setPlayingUI("playing");
    loop();
  }
}

function seekTo(t) {
  t = Math.max(0, Math.min(t, state.duration));
  if (state.hasAudio) {
    audio.currentTime = t;
  } else {
    state.manualOffset = t;
    state.manualStart = performance.now();
  }
  update(t);
}

// Oculta/muestra elementos. OJO: en elementos SVG la propiedad .hidden de JS
// NO refleja al atributo, así que el CSS [hidden] no aplica. Hay que togglear
// el atributo a mano.
function setHidden(node, hidden) {
  if (hidden) node.setAttribute("hidden", "");
  else node.removeAttribute("hidden");
}

// mode: "playing" | "paused" | "loading"
function setPlayingUI(mode) {
  state.playing = mode === "playing";
  setHidden(el.icPlay, mode !== "paused");
  setHidden(el.icPause, mode !== "playing");
  setHidden(el.icLoading, mode !== "loading");
}

// --------------------------------------------------------------------------- //
// Loop de render
// --------------------------------------------------------------------------- //
function loop() {
  if (state.rafId) cancelAnimationFrame(state.rafId);
  const tick = () => {
    update(currentTime());
    const running = state.hasAudio ? !audio.paused : state.playing;
    if (running) {
      state.rafId = requestAnimationFrame(tick);
    } else {
      state.rafId = null;
    }
  };
  state.rafId = requestAnimationFrame(tick);
}

function update(t) {
  // Barra de progreso
  if (!state.seeking) setProgress(state.duration ? t / state.duration : 0);
  el.curTime.textContent = fmt(t);

  // Línea activa
  let idx = -1;
  for (let i = 0; i < state.lines.length; i++) {
    if (state.lines[i].time <= t + 0.01) idx = i; else break;
  }
  if (idx !== state.activeIndex) {
    setActiveLine(idx);
    state.activeIndex = idx;
  }
}

function setProgress(ratio) {
  ratio = Math.max(0, Math.min(1, ratio));
  const pct = (ratio * 100).toFixed(3) + "%";
  el.trackFill.style.width = pct;
  el.trackKnob.style.left = pct;
}

function setActiveLine(idx) {
  state.lineEls.forEach((node, i) => {
    node.classList.remove("active", "past", "near", "far");
    const d = i - idx;
    if (d === 0) node.classList.add("active");
    else if (d < 0) node.classList.add("past");
    else if (d <= 2) node.classList.add("near");
    else node.classList.add("far");
  });
  scrollActiveIntoView(idx, "smooth");
}

// Centra la línea activa en el panel. Se recalcula también al redimensionar
// la ventana (por eso "solo se veía bien al ajustar"): ahora el layout se
// reajusta solo.
function scrollActiveIntoView(idx, behavior) {
  const pane = el.lyrics;
  const active = state.lineEls[idx];
  if (active) {
    const target = active.offsetTop - pane.clientHeight * 0.42 + active.clientHeight / 2;
    pane.scrollTo({ top: Math.max(0, target), behavior: behavior || "auto" });
  } else {
    pane.scrollTo({ top: 0, behavior: behavior || "auto" });
  }
}

let resizeRaf = null;
window.addEventListener("resize", () => {
  if (resizeRaf) cancelAnimationFrame(resizeRaf);
  resizeRaf = requestAnimationFrame(() => scrollActiveIntoView(state.activeIndex, "auto"));
});

// --------------------------------------------------------------------------- //
// Eventos
// --------------------------------------------------------------------------- //
el.loadBtn.onclick = loadSong;
[el.artist, el.title].forEach((input) =>
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadSong();
  })
);

el.playBtn.onclick = togglePlay;
el.backBtn.onclick = () => seekTo(currentTime() - 5);
el.fwdBtn.onclick = () => seekTo(currentTime() + 5);
el.volume.oninput = () => (audio.volume = parseFloat(el.volume.value));

// Pantalla completa
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    (document.documentElement.requestFullscreen?.() || Promise.reject()).catch(() =>
      toast("Tu navegador no permitió pantalla completa.")
    );
  } else {
    document.exitFullscreen?.();
  }
}
el.fsBtn.onclick = toggleFullscreen;

// Selector de fuente para la letra. Vive en la barra superior (visible también
// en la pantalla de inicio), se aplica a la letra y al preview, y se recuerda.
const LYRIC_FONTS = [
  { name: "Inter", stack: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  { name: "Poppins", stack: '"Poppins", sans-serif' },
  { name: "Playfair", stack: '"Playfair Display", Georgia, serif' },
  { name: "Caveat", stack: '"Caveat", "Comic Sans MS", cursive' },
];
let fontIndex = 0;

// Construye el menú: cada opción se ve EN su propia fuente para que se entienda.
LYRIC_FONTS.forEach((font, i) => {
  const opt = document.createElement("button");
  opt.className = "font-option";
  opt.style.fontFamily = font.stack;
  opt.innerHTML = `<span>${font.name}</span><span class="tick">✓</span>`;
  opt.onclick = () => { applyLyricFont(i); closeFontMenu(); };
  el.fontMenu.appendChild(opt);
});

function applyLyricFont(i) {
  fontIndex = ((i % LYRIC_FONTS.length) + LYRIC_FONTS.length) % LYRIC_FONTS.length;
  const font = LYRIC_FONTS[fontIndex];
  document.documentElement.style.setProperty("--lyric-font", font.stack);
  el.fontCurrent.textContent = font.name;
  [...el.fontMenu.children].forEach((node, idx) =>
    node.classList.toggle("active", idx === fontIndex)
  );
  try { localStorage.setItem("lyricFont", String(fontIndex)); } catch (e) {}
}

function openFontMenu() {
  el.fontMenu.hidden = false;
  el.fontBtn.setAttribute("aria-expanded", "true");
}
function closeFontMenu() {
  el.fontMenu.hidden = true;
  el.fontBtn.setAttribute("aria-expanded", "false");
}
el.fontBtn.onclick = (e) => {
  e.stopPropagation();
  if (el.fontMenu.hidden) openFontMenu(); else closeFontMenu();
};
document.addEventListener("click", (e) => {
  if (!el.fontPicker.contains(e.target)) closeFontMenu();
});

(() => {
  let saved = NaN;
  try { saved = parseInt(localStorage.getItem("lyricFont"), 10); } catch (e) {}
  applyLyricFont(isNaN(saved) ? 0 : saved);
})();

document.addEventListener("fullscreenchange", () => {
  const full = !!document.fullscreenElement;
  setHidden(el.icFsOpen, full);
  setHidden(el.icFsClose, !full);
});

// Seek arrastrando la barra
function seekFromEvent(e) {
  const rect = el.track.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  setProgress(ratio);
  return ratio * state.duration;
}
el.track.addEventListener("pointerdown", (e) => {
  state.seeking = true;
  el.track.setPointerCapture(e.pointerId);
  setProgress(seekFromEvent(e) / state.duration);
});
el.track.addEventListener("pointermove", (e) => {
  if (state.seeking) setProgress(seekFromEvent(e) / state.duration);
});
el.track.addEventListener("pointerup", (e) => {
  if (!state.seeking) return;
  state.seeking = false;
  seekTo(seekFromEvent(e));
});

// Audio nativo
const onAudioPlay = () => { setPlayingUI("playing"); loop(); };
audio.addEventListener("play", () => { if (audio.readyState < 3) setPlayingUI("loading"); });
audio.addEventListener("playing", onAudioPlay);
audio.addEventListener("waiting", () => { if (state.intendPlay) setPlayingUI("loading"); });
audio.addEventListener("canplay", () => { if (state.intendPlay && audio.paused) audio.play().catch(() => {}); });
audio.addEventListener("pause", () => { if (state.intendPlay && audio.readyState < 3) return; setPlayingUI("paused"); });
audio.addEventListener("loadedmetadata", () => {
  if (isFinite(audio.duration) && audio.duration > 0) {
    state.duration = audio.duration;
    el.durTime.textContent = fmt(state.duration);
  }
});
audio.addEventListener("ended", () => { state.intendPlay = false; setPlayingUI("paused"); });
audio.addEventListener("error", () => {
  if (state.hasAudio) {
    toast("No pude reproducir el audio; la letra avanza con el reloj.");
    state.hasAudio = false;
    el.audioNote.hidden = false;
    el.audioNote.textContent = "Audio no disponible. La letra avanza con el reloj.";
  }
});

// Atajos de teclado
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") { e.preventDefault(); togglePlay(); }
  if (e.code === "ArrowRight") seekTo(currentTime() + 5);
  if (e.code === "ArrowLeft") seekTo(currentTime() - 5);
  if (e.code === "KeyF") toggleFullscreen();
  if (e.code === "Escape") closeFontMenu();
});

// Foco inicial
el.artist.focus();
