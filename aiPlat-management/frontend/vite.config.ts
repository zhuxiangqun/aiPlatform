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
      '/api/core/wiki': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/diagnostics': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/kb-eval': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/workflow': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/packages': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/skill-packs': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/workspace/mcp': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/workspace/skills/installer': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/prompts': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core/observation': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/core': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/platform': {
        target: 'http://localhost:8003',
        changeOrigin: true,
        timeout: 600000,
      },
      '/api/onboarding': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/policies': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api/pentest': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // P1-11: app 服务（8004）——前端走相对路径 /app 由 proxy 转发，消除硬编码
      '/app': {
        target: 'http://localhost:8004',
        changeOrigin: true,
        timeout: 600000,
      },
      '/ws': {
        target: 'http://localhost:8002',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
