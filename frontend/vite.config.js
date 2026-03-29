import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  envDir: '../',
  envPrefix: ['VITE_', 'SUPABASE_URL', 'SUPABASE_ANON_KEY'],
  server: {
    port: 3000,
    host: true,
    allowedHosts: [
      "3000-01jqdrc9t24f6t44n70vh9wsf8.cloudspaces.litng.ai"
    ],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})