import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // 优先使用进程环境变量；避免本地 Vite/esbuild 在 Windows 上向上扫描用户目录。
  const envDir = process.env.VITE_ENV_DIR || __dirname
  const env = loadEnv(mode, envDir)

  const apiBaseUrl = process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL || '/api'
  const backendPort = process.env.BACKEND_PORT || env.BACKEND_PORT || '8483'
  const proxyTarget = apiBaseUrl.startsWith('/')
    ? `http://127.0.0.1:${backendPort}`
    : apiBaseUrl
  const port = parseInt(process.env.VITE_FRONTEND_PORT || env.VITE_FRONTEND_PORT || '3015', 10)

  return {
    base: './',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            // Keep React in its own eagerly needed chunk. A manual Markdown
            // chunk must not absorb React and pull the entire parser into boot.
            if (/\/node_modules\/(react|react-dom|scheduler|react-router|react-router-dom)\//.test(id)) return 'vendor'
          },
        },
      },
    },
    server: {
      host: '0.0.0.0',
      port: port,
      allowedHosts: true, // 允许任意域名访问
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: path => path.replace(/^\/api/, '/api'),
        },
        '/static': {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: path => path.replace(/^\/static/, '/static'),
        },
        '/uploads': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
