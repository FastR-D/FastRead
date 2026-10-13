import { start } from './web/sso-bootstrap'

// Fetch the UI in parallel with authentication, without making authentication
// wait for React/Markdown to download and execute first.
const app = Promise.all([import('./web/App'), import('react'), import('react-dom/client')])
void app.catch(() => {})
void start(async initialUser => {
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('UI load timeout')), 15000) })
  const [{ default: App }, { createElement, StrictMode }, { createRoot }] = await Promise.race([app, deadline]).finally(() => clearTimeout(timer))
  createRoot(document.getElementById('root')!).render(createElement(StrictMode, null, createElement(App, { initialUser })))
}).catch(() => {
  const root = document.getElementById('root')!
  root.replaceChildren()
  const title = document.createElement('h2'); title.textContent = '连接暂时中断'
  const detail = document.createElement('p'); detail.textContent = '页面资源或登录服务未能及时响应，请重试。'
  const retry = document.createElement('button'); retry.textContent = '重新连接'; retry.onclick = () => location.reload()
  root.append(title, detail, retry)
})
