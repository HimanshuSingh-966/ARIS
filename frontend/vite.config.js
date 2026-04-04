import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  envDir: '../', // Load .env from pharma_rag root
  // CRITICAL SECURITY FIX: Only expose the URL and ANON_KEY safely to the client. The SERVICE_KEY remains hidden.
  envPrefix: ['VITE_', 'SUPABASE_URL', 'SUPABASE_ANON_KEY'],
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
