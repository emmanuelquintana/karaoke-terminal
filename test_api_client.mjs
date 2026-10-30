import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const source = await readFile(new URL("./web/src/api/client.js", import.meta.url), "utf8");

async function client(origin) {
  const code = source.replace("import.meta.env", JSON.stringify({ VITE_API_ORIGIN: origin }));
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
}

test("local and remote URLs include the correct backend and encoded queries", async () => {
  for (const origin of ["", "https://api.example.com///"]) {
    const api = await client(origin);
    const base = origin.replace(/\/+$/, "");
    assert.equal(api.apiUrl("/api/v1/studio-sessions/abc/video"), `${base}/api/v1/studio-sessions/abc/video`);
    assert.equal(api.apiUrl("/api/v1/studio-exports/abc/file"), `${base}/api/v1/studio-exports/abc/file`);
    assert.equal(api.apiUrl(undefined), "");
    assert.equal(api.songAudioUrl("A & B", "Canción"), `${base}/api/v1/songs/audio?artist=A+%26+B&title=Canci%C3%B3n`);
    assert.equal(api.coverProxyUrl("https://is1.mzstatic.com/a.jpg"), `${base}/api/v1/covers?u=https%3A%2F%2Fis1.mzstatic.com%2Fa.jpg`);
  }
});

test("all JSON requests use the remote backend, including studio actions", async (t) => {
  const api = await client("https://api.example.com");
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push({ url, options });
    return new Response(JSON.stringify({ data: { ok: true } }), { status: 200 });
  });
  assert.deepEqual(await api.loadSong("A", "B"), { ok: true });
  await api.createStudioSession({ video: "video", artist: "A", title: "B" });
  await api.syncStudioSession("a/b");
  await api.exportStudioSession("a/b", { length: 10 });
  assert.deepEqual(requests.map(({ url }) => url), [
    "https://api.example.com/api/v1/songs?artist=A&title=B",
    "https://api.example.com/api/v1/studio-sessions",
    "https://api.example.com/api/v1/studio-sessions/a%2Fb/sync",
    "https://api.example.com/api/v1/studio-sessions/a%2Fb/exports",
  ]);
  assert.equal(requests[1].options.method, "POST");
  assert.deepEqual(JSON.parse(requests[3].options.body), { length: 10 });
});

test("HTML responses and backend failures display errors", async (t) => {
  const api = await client("");
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response("<html>SPA fallback</html>"));
  await assert.rejects(api.loadSong("A", "B"), /no devolvió JSON/);
  fetch.mock.mockImplementation(async () => new Response(JSON.stringify({ message: "Servidor ocupado" }), { status: 503 }));
  await assert.rejects(api.loadSong("A", "B"), /Servidor ocupado/);
});

test("network errors are readable and intentional cancellation remains an AbortError", async (t) => {
  const api = await client("https://api.example.com");
  const fetch = t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(api.loadSong("A", "B"), /No pude conectar con el servidor/);
  const abort = new DOMException("Cancelado", "AbortError");
  fetch.mock.mockImplementation(async () => { throw abort; });
  await assert.rejects(api.loadSong("A", "B"), (error) => error === abort);
});
