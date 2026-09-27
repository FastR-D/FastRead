import { defineConfig, loadEnv, type Plugin, type ViteDevServer } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import http from 'node:http'
import type { IncomingMessage, ServerResponse } from 'http'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'

function cookieList(header: string | string[] | undefined): string[] {
  if (!header) return []
  return Array.isArray(header) ? header : [header]
}

function hasSessionCookie(cookies: string[]): boolean {
  return cookies.some((item) => /(^|,\s*)fastread_session=/.test(item))
}

function exchangeResearchTicket(backendOrigin: string, ticket: string): Promise<{ status: number; cookies: string[] }> {
  return new Promise((resolve, reject) => {
    const target = new URL('/api/auth/research', backendOrigin)
    const body = Buffer.from(JSON.stringify({ ticket }))
    const req = http.request(
      {
        hostname: target.hostname,
        port: target.port || 80,
        path: target.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': body.length,
        },
      },
      (incoming) => {
        const cookies = cookieList(incoming.headers['set-cookie'])
        incoming.resume()
        incoming.on('end', () => {
          resolve({ status: incoming.statusCode || 0, cookies })
        })
      },
    )
    req.setTimeout(5000, () => {
      req.destroy(new Error('research ticket exchange timed out'))
    })
    req.on('error', reject)
    req.write(body)
    req.end()
  })
}

function researchGatePlugin(panelUrl: string, backendOrigin: string): Plugin {
  return {
    name: 'fastread-research-gate',
    configureServer(server: ViteDevServer) {
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next: () => void) => {
        const url = new URL(req.url || '/', 'http://127.0.0.1')
        if (url.pathname !== '/' && url.pathname !== '/index.html') {
          next()
          return
        }
        const ticket = (url.searchParams.get('sso') || '').trim()
        if (ticket) {
          void (async () => {
            try {
              const auth = await exchangeResearchTicket(backendOrigin, ticket)
              if (auth.status === 200 && hasSessionCookie(auth.cookies)) {
                for (const cookie of auth.cookies) {
                  res.appendHeader('Set-Cookie', cookie)
                }
                url.searchParams.delete('sso')
                const search = url.searchParams.toString()
                req.url = `${url.pathname}${search ? `?${search}` : ''}`
                next()
                return
              }
            } catch {
              // bounce to panel below
            }
            res.statusCode = 302
            res.setHeader('Location', panelUrl)
            res.setHeader('Cache-Control', 'no-store')
            res.end()
          })()
          return
        }
        const cookie = req.headers.cookie || ''
        if (/(?:^|;\s*)fastread_session=[^;]+/.test(cookie)) {
          next()
          return
        }
        res.statusCode = 302
        res.setHeader('Location', panelUrl)
        res.setHeader('Cache-Control', 'no-store')
        res.end()
      })
    },
  }
}

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
  const panelUrl = (process.env.FASTRESEARCH_PANEL_URL || env.FASTRESEARCH_PANEL_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')

  return {
    base: './',
    plugins: [researchGatePlugin(panelUrl, proxyTarget), react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            markdown: ['react-markdown', 'react-syntax-highlighter', 'remark-gfm', 'remark-math', 'rehype-katex'],
            markmap: ['markmap-lib', 'markmap-view', 'markmap-toolbar', 'markmap-common'],
            vendor: ['react', 'react-dom', 'react-router-dom'],
          },
        },
      },
    },
    server: {
      host: '127.0.0.1',
      port: port,
      allowedHosts: ['127.0.0.1', 'localhost'],
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
