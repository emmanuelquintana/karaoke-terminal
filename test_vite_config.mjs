import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveConfig } from "vite";

async function config(mode, origin, vercel) {
  const previous = { VITE_API_ORIGIN: process.env.VITE_API_ORIGIN, VERCEL: process.env.VERCEL };
  process.env.VITE_API_ORIGIN = origin;
  if (vercel === undefined) delete process.env.VERCEL;
  else process.env.VERCEL = vercel;
  try {
    return await resolveConfig({ mode, logLevel: "silent" }, "build");
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test("Vercel uses root assets even without exposed system environment variables", async () => {
  const resolved = await config("vercel", "https://api.example.com");
  assert.equal(resolved.base, "/");
  assert.equal(resolved.env.VITE_API_ORIGIN, "https://api.example.com");
});

test("Vercel rejects a missing backend instead of publishing a broken API", async () => {
  await assert.rejects(config("vercel", ""), /Configura VITE_API_ORIGIN/);
});

test("Vercel rejects mixed content, paths and credentials in the backend origin", async () => {
  for (const origin of ["http://api.example.com", "https://api.example.com/api/v1", "https://user:secret@api.example.com", "https://api.example.com?key=secret", "https://api.example.com?", "https://api.example.com#"]) {
    await assert.rejects(config("vercel", origin), /VITE_API_ORIGIN/);
  }
});

test("local Flask builds retain their web path and relative API", async () => {
  const resolved = await config("production", "");
  assert.equal(resolved.base, "/web/");
});

test("existing VERCEL=1 build calls remain compatible", async () => {
  const resolved = await config("production", "https://api.example.com", "1");
  assert.equal(resolved.base, "/");
});

test("origin typos explain the required format and trailing slashes are normalized", async () => {
  await assert.rejects(config("vercel", "api.example.com"), /VITE_API_ORIGIN debe ser un origen/);
  const resolved = await config("vercel", " https://api.example.com/// ");
  assert.equal(resolved.base, "/");
});
