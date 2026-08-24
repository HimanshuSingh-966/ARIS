import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode, command }) => {
  // Loaded with an empty prefix so config code can read unprefixed vars like
  // ARIS_API_KEY. This runs in Node at build/serve time only — `envPrefix` below
  // is what governs what reaches the browser bundle, and it does not include
  // these. Nothing read here is inlined into client code.
  const env = loadEnv(mode, '../', '')
  const apiKey = env.ARIS_API_KEY || process.env.ARIS_API_KEY

  // Inside a container, `localhost` is the container itself, so the default only
  // works for a dev server running on the host. docker-compose sets this to
  // http://api:8000, the backend's service name on the compose network.
  const apiTarget =
    env.ARIS_API_PROXY_TARGET || process.env.ARIS_API_PROXY_TARGET || 'http://localhost:8000'

  // Bind mounts do not forward inotify events from a Windows/macOS host into a
  // container, so the watcher has to poll or HMR quietly stops firing. Off by
  // default: polling wakes the CPU constantly and is pure waste on a native run.
  const usePolling = /^(1|true)$/i.test(
    env.CHOKIDAR_USEPOLLING || process.env.CHOKIDAR_USEPOLLING || ''
  )

  // Only meaningful for `vite dev` (command === 'serve'), which is the sole
  // consumer of apiKey — the proxy below exists only in the dev server. During
  // `vite build` there is no proxy, the key is legitimately absent (production
  // holds it in Vercel's env, where the Edge function reads it), and firing this
  // in CI trains people to ignore a warning that does mean something locally.
  if (!apiKey && command === 'serve') {
    console.warn(
      '\n[vite] ARIS_API_KEY is not set, so the dev proxy cannot authenticate.\n' +
      '       The backend fails closed and will answer 401/503. Add ARIS_API_KEY\n' +
      '       to the root .env (same value as the backend).\n'
    )
  }

  return {
    plugins: [react()],
    envDir: '../', // Load .env from repo root

    // Only VITE_-prefixed vars reach the client. SUPABASE_URL and
    // SUPABASE_ANON_KEY were previously listed here; nothing referenced them, but
    // the entry was an open invitation to inline database credentials into a
    // public bundle. The browser has no direct database or backend access now —
    // it talks only to same-origin /api/*, proxied server-side.
    envPrefix: ['VITE_'],

    server: {
      host: '0.0.0.0',
      allowedHosts: true,
      port: 3000,
      ...(usePolling ? { watch: { usePolling: true, interval: 300 } } : {}),
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // Mirrors what the Vercel Edge function does in production, so the
          // backend can require the key unconditionally instead of skipping auth
          // whenever the variable happens to be missing.
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              if (apiKey) proxyReq.setHeader('X-API-Key', apiKey)
            })
          },
        },
      },
    },
  }
})
