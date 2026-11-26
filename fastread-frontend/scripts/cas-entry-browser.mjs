import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import assert from 'node:assert/strict'

const server = await preview({ configFile: false, preview: { host: '127.0.0.1', port: 0 } })
const base = `http://127.0.0.1:${server.httpServer.address().port}`
const browser = await chromium.launch({ channel: 'msedge', headless: true })
let authenticated = false
let logins = 0
const context = await browser.newContext({ serviceWorkers: 'block' })
context.setDefaultTimeout(15000)
await context.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname
  if (path === '/api/auth/fastcas/login') {
    authenticated = true
    logins++
    return route.fulfill({ status: 302, headers: { location: `${base}/?fastcas=complete` } })
  }
  let json = { items: [] }
  if (path === '/api/auth/me') {
    if (!authenticated) return route.fulfill({ status: 401, json: { detail: 'Login required' } })
    json = {
      id: 'fixture-reader',
      display_name: 'Reader',
      role: 'owner',
      workspace_id: 'fixture-workspace',
      csrf: 'fixture-csrf',
      workspace: { name: 'Fixture' },
    }
  } else if (path === '/api/auth/fastcas/available') json = { enabled: true, login_enabled: true }
  else if (path === '/api/auth/fastcas/status')
    json = { enabled: true, link_enabled: true, link: { state: 'active' } }
  else if (path === '/api/integrations/status')
    json = {
      fastnews: { connected: false, cas_available: true },
      fastwrite: { connected: false, cas_available: true },
    }
  await route.fulfill({ json })
})
try {
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${base}/?section=settings&auth=cas`)
  await expect(page.getByRole('tab', { name: '设置', exact: true })).toHaveAttribute(
    'aria-selected',
    'true'
  )
  await expect(page.getByRole('tabpanel', { name: '设置', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '通过 CAS 连接 FastWrite' })).toBeVisible()
  assert.equal(logins, 1, 'CAS return must not loop through login')
  assert.deepEqual(errors, [])
  console.log('PASS CAS application entry restores the settings tab after login')
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
