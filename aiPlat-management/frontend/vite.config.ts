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
      '/api/core/diagnostics/doctor': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace('/api/core/diagnostics/doctor', '/api/diagnostics/doctor'),
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
        // SSE: disable buffering so EventSource sees text/event-stream promptly
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            const ct = String(proxyRes.headers['content-type'] || '')
            if (ct.includes('text/event-stream') || String(proxyRes.headers['transfer-encoding'] || '').includes('chunked')) {
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
              // Ensure browser EventSource accepts the stream (some proxies strip charset)
              if (!ct.includes('text/event-stream')) {
                proxyRes.headers['content-type'] = 'text/event-stream; charset=utf-8'
              }
            }
          })
        },
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
