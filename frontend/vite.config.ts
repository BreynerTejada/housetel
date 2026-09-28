import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// In Docker the backend is reachable as http://backend:8000 (docker-compose sets VITE_PROXY_TARGET);
// on the host it is published on port 8010.
const target = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8010'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: {
    host: true,
    port: 5173,
    proxy: {
      // changeOrigin stays false so Django sees the browser Host and the CSRF Origin check passes.
      '/api': { target, changeOrigin: false },
      '/media': { target, changeOrigin: false },
      // Django's static files: the offline Swagger UI of /api/docs/ (drf-spectacular-sidecar, P1).
      '/static': { target, changeOrigin: false },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        // React core changes rarely: its own long-cached chunk, downloaded in parallel with the app.
        codeSplitting: {
          groups: [{ name: 'react-vendor', test: /node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/ }],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    globals: true,
    // Longer than Testing Library's asyncUtilTimeout (8 s, see src/test/setup.ts) so a failing
    // `findBy*` reports its own error instead of a generic timeout.
    testTimeout: 15_000,
    // Dates are business dates in Colombia; pin the zone so date tests are deterministic.
    env: { TZ: 'America/Bogota' },
  },
})
