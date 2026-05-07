import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/infra': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/api/dashboard': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/alerting': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/diagnostics': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/monitoring': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/core': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/platform': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        timeout: 600000,
      },
      '/api/app': {
        target: 'http://localhost:8004',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
