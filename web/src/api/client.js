const API_BASE = "/api/v1";

async function readJson(response) {
  try {
    return await response.json();
  } catch (_err) {
    return null;
  }
}

export async function apiJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(payload?.message || payload?.error || "No pude completar la solicitud.");
  }
  return payload?.data ?? payload ?? {};
}

export function songAudioUrl(artist, title) {
  const query = new URLSearchParams({ artist, title });
  return `${API_BASE}/songs/audio?${query.toString()}`;
}

export function coverProxyUrl(url) {
  return `${API_BASE}/covers?u=${encodeURIComponent(url)}`;
}

export function createStudioSession(payload) {
  return apiJson("/studio-sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function syncStudioSession(sessionId) {
  return apiJson(`/studio-sessions/${encodeURIComponent(sessionId)}/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function exportStudioSession(sessionId, payload) {
  return apiJson(`/studio-sessions/${encodeURIComponent(sessionId)}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function loadSong(artist, title) {
  const query = new URLSearchParams({ artist, title });
  return apiJson(`/songs?${query.toString()}`);
}

export function syncSongLyrics(payload) {
  return apiJson("/songs/lyrics-sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
