import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { start } from './web/sso-bootstrap'

void start(async () => {
  const { default: App } = await import('./web/App')
  createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
})
