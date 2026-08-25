/**
 * frontend/api/proxy.js
 *
 * Server-side proxy for every /api/* call the SPA makes.
 *
 * WHY THIS EXISTS
 *   A static SPA cannot hold a secret — anything in the bundle is readable by
 *   anyone who opens devtools. So the browser is given no credentials and no
 *   knowledge of where the backend lives. It calls its own origin; this function
 *   adds the API key and forwards to Render.
 *
 *   Replaces the `/api/(.*)` rewrite that previously sat in vercel.json with the
 *   backend URL hardcoded in it and committed to the repo.
 *
 * WHY A STATIC FILENAME AND AN EXPLICIT REWRITE
 *   This file was `api/[...path].js` and every two-segment route 404'd at the
 *   edge — the function was built and aliased, but `/api/v1/health` never reached
 *   it while `/api/foo` did. `[...param]` catch-all syntax is a Next.js
 *   convention. This is a plain Vite SPA using Vercel's zero-config `api/`
 *   directory, which supports `[param]` but has no catch-all, so it read the name
 *   as a parameter literally called `...path` and compiled it to a single-segment
 *   matcher. Everything the app calls is mounted under `/api/v1` (see
 *   api/main.py), so every request missed by exactly one slash.
 *
 *   So routing is now explicit rather than inferred from a filename. vercel.json
 *   rewrites `/api/(.*)` here and carries the real path in `__aris_path`; the
 *   handler reads it, strips it, and forwards the rest. Rewrites run only after
 *   the filesystem check, so a direct hit on /api/proxy reaches this function
 *   with no `__aris_path` and falls back to its own pathname.
 *
 *   That explanation lives here because vercel.json cannot hold it: JSON has no
 *   comments, and Vercel validates the file against a strict schema that rejects
 *   unknown keys such as "comment".
 *
 * WHY EDGE RUNTIME, NOT NODE
 *   Node serverless functions on Vercel Hobby buffer the whole response and cap
 *   it at 4.5 MB. /api/v1/documents/{id}/stream serves regulatory PDFs that
 *   routinely exceed that, so a Node function would truncate them. Edge streams
 *   the body through without buffering.
 *
 * REQUIRED VERCEL ENVIRONMENT VARIABLES (both server-side only — no VITE_
 * prefix, so Vite can never inline them into the client bundle):
 *   ARIS_API_ORIGIN  e.g. https://aris-maqr.onrender.com
 *   ARIS_API_KEY     must match the backend's ARIS_API_KEY
 */

export const config = { runtime: 'edge' };

// Hop-by-hop and platform headers that must not be forwarded upstream.
const STRIP_REQUEST_HEADERS = new Set([
  'host',
  'connection',
  'keep-alive',
  'transfer-encoding',
  'upgrade',
  'proxy-authorization',
  'proxy-authenticate',
  'te',
  'trailer',
  'content-length', // recomputed by fetch
  // Never let a client set its own key and have it reach the backend.
  'x-api-key',
]);

const STRIP_RESPONSE_HEADERS = new Set([
  'connection',
  'keep-alive',
  'transfer-encoding',
  'upgrade',
  'content-encoding', // fetch has already decoded the body
  'content-length',
]);

// Query parameter vercel.json uses to hand this function the path it should
// forward. Internal to the rewrite — never reaches the browser, and stripped
// below before anything is sent upstream.
const ROUTE_PARAM = '__aris_path';

export default async function handler(request) {
  const origin = process.env.ARIS_API_ORIGIN;
  const apiKey = process.env.ARIS_API_KEY;

  if (!origin || !apiKey) {
    // Fail closed and say only that it is misconfigured — the message reaches
    // the public internet, so it names nothing.
    console.error(
      'Proxy misconfigured: ARIS_API_ORIGIN and ARIS_API_KEY must both be set.'
    );
    return jsonError(503, 'Service is not configured.');
  }

  const incoming = new URL(request.url);

  // The rewrite puts the caller's real path in __aris_path, because after the
  // rewrite incoming.pathname is always "/api/proxy". Fall back to the actual
  // pathname so a direct request to /api/proxy still behaves sanely — it proxies
  // "/api/proxy" upstream and gets the backend's own 404, rather than silently
  // forwarding some other path.
  const params = new URLSearchParams(incoming.search);
  const routed = params.get(ROUTE_PARAM);
  params.delete(ROUTE_PARAM);

  const pathname = routed || incoming.pathname;
  const search   = params.toString();

  // Rebuild the target URL against the backend origin, preserving path and query.
  // Constructing from the origin (rather than string concatenation) means a
  // crafted path cannot redirect the request somewhere else. new URL also
  // normalises `..` before the checks below, so traversal cannot escape /api/.
  let target;
  try {
    target = new URL(pathname + (search ? `?${search}` : ''), origin);
  } catch {
    return jsonError(400, 'Bad request.');
  }

  // Defence in depth: only ever proxy the API surface.
  if (!target.pathname.startsWith('/api/')) {
    return jsonError(404, 'Not found.');
  }
  if (target.origin !== new URL(origin).origin) {
    return jsonError(400, 'Bad request.');
  }

  const headers = new Headers();
  for (const [name, value] of request.headers) {
    if (!STRIP_REQUEST_HEADERS.has(name.toLowerCase())) {
      headers.set(name, value);
    }
  }
  headers.set('X-API-Key', apiKey);

  const hasBody = !['GET', 'HEAD'].includes(request.method);

  let upstream;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by the Fetch spec when streaming a request body.
      ...(hasBody ? { duplex: 'half' } : {}),
      redirect: 'manual',
    });
  } catch (err) {
    console.error('Upstream fetch failed:', err);
    return jsonError(502, 'Upstream request failed.');
  }

  const responseHeaders = new Headers();
  for (const [name, value] of upstream.headers) {
    if (!STRIP_RESPONSE_HEADERS.has(name.toLowerCase())) {
      responseHeaders.set(name, value);
    }
  }

  // Body is passed through as a stream, so large PDFs are never buffered.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

function jsonError(status, detail) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
