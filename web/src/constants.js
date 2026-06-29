export const SUGGESTIONS = [
  { artist: "Coldplay", title: "Yellow" },
  { artist: "Bad Bunny", title: "Tití Me Preguntó" },
  { artist: "The Weeknd", title: "Blinding Lights" },
  { artist: "Enjambre", title: "Dulce Soledad" },
];

export const DEFAULT_PALETTE = ["#3a3a44", "#20202a", "#4a4458"];

export const LYRIC_FONTS = [
  { name: "Inter", stack: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  { name: "Poppins", stack: '"Poppins", sans-serif' },
  { name: "Playfair", stack: '"Playfair Display", Georgia, serif' },
  { name: "Caveat", stack: '"Caveat", "Comic Sans MS", cursive' },
];

export const STUDIO_FONT_STACKS = {
  Inter: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  Poppins: '"Poppins", sans-serif',
  Playfair: '"Playfair Display", Georgia, serif',
  Caveat: '"Caveat", "Comic Sans MS", cursive',
  Arial: "Arial, Helvetica, sans-serif",
};

export const INITIAL_STUDIO = {
  sessionId: "",
  lines: [],
  duration: 0,
  maxClipSeconds: 58,
  lyricMode: "",
  clipStart: 0,
  clipLength: 58,
  format: "vertical",
  font: "Inter",
  position: "bottom",
  style: "boxed",
  color: "white",
  size: 58,
  offset: 0,
  prepared: false,
  exporting: false,
  syncing: false,
};

export function formatTime(seconds) {
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const minutes = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
