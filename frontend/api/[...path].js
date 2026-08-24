/**
 * frontend/api/[...path].js
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
 *   vercel.json now carries only the SPA fallback, whose source regex
 *   `/((?!api/).*)` uses a negative lookahead so that /api/* is NOT rewritten to
 *   index.html and reaches this function instead. That explanation lives here
 *   because vercel.json cannot hold it: JSON has no comments, and Vercel validates
 *   the file against a strict schema that rejects unknown keys such as "comment".
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

  // Rebuild the target URL against the backend origin, preserving path and query.
  // Constructing from the origin (rather than string concatenation) means a
  // crafted path cannot redirect the request somewhere else.
  let target;
  try {
    target = new URL(incoming.pathname + incoming.search, origin);
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
