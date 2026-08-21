/**
 * frontend/src/lib/api.js
 *
 * The single place the browser talks to the backend.
 *
 * Every request goes to a same-origin relative path, deliberately. In production
 * Vercel rewrites /api/* into the Edge function in frontend/api/[...path].js,
 * which attaches X-API-Key server-side; in development vite.config.js's proxy
 * does the same. Either way the API key and the backend's real origin never enter
 * the browser bundle — so nothing here may be handed an absolute backend URL.
 */
import axios from 'axios';

export const API_BASE = '/api/v1';

export const api = axios.create({ baseURL: API_BASE });

/**
 * URL that streams a document's PDF back through the API.
 *
 * Use this instead of building a public Backblaze URL: the bucket is private, so
 * a direct link 403s. The API holds the credentials and presigns on demand.
 */
export function documentStreamUrl(docId) {
  return `${API_BASE}/documents/${encodeURIComponent(docId)}/stream`;
}

/**
 * Resolve a form's presigned download URL and open it in a new tab.
 *
 * Throws on failure so each caller can surface the error in its own idiom. This
 * lived only inside FormsPage, so the identical FormCard rendered by a chat answer
 * had no handler at all and threw a TypeError on click.
 */
export async function downloadForm(formId) {
  const res = await api.get(`/forms/${encodeURIComponent(formId)}/download`);
  const url = res.data?.download_url;
  if (!url) throw new Error('Response contained no download_url');

  // noopener/noreferrer: the presigned URL opens a page that must not get a
  // handle on this window via window.opener.
  window.open(url, '_blank', 'noopener,noreferrer');
  return url;
}
