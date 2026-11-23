import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The UI calls the API through /api, which the dev server proxies to FastAPI.
// This avoids CORS problems whichever host name the UI is opened with.
// Override the target with FIRESIM_API (e.g. FIRESIM_API=http://127.0.0.1:9000 npm run dev).
const apiTarget = process.env.FIRESIM_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1200,
  },
})
