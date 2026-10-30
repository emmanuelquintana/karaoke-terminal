const API_ORIGIN = (import.meta.env?.VITE_API_ORIGIN || "").trim().replace(/\/+$/, "");
const API_BASE = `${API_ORIGIN}/api/v1`;

export function apiUrl(path) {
  return path ? `${API_ORIGIN}${path}` : "";
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (_err) {
    return null;
  }
}

export async function apiJson(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("No pude conectar con el servidor. Revisa tu conexión o inténtalo de nuevo.");
  }
  const payload = await readJson(response);
  if (payload === null) {
    throw new Error("El servidor no devolvió JSON. Revisa la URL y la disponibilidad del backend.");
  }
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
