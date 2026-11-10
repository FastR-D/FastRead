import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'

// Run after build. Only the HTTP service is substituted; the production UI stays real.
const artifacts = 'test-results/fastui'
await mkdir(artifacts, { recursive: true })
const server = await preview({ configFile: false, preview: { host: '127.0.0.1', port: 0 } })
const base = `http://127.0.0.1:${server.httpServer.address().port}`
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block', colorScheme: 'light' })
const writes = [], errors = [], scenarios = []
let providers = [{ id: 'provider-1', name: 'Workspace model', models: ['model-a', 'model-b'] }]
await context.route('**/api/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() === 'POST') writes.push({ path, body: request.postDataJSON() })
  let value = { items: [] }, status = 200
  if (path === '/api/auth/me') value = { id: 'reader', display_name: 'Reader', role: 'owner', workspace_id: 'workspace', csrf: 'fixture-csrf', workspace: { name: 'Workspace', daily_limit: 24 } }
  else if (path === '/api/providers') {
    if (request.method() === 'POST') providers = [...providers, { id: 'provider-2', ...request.postDataJSON() }]
    value = { items: providers }
  } else if (path === '/api/auth/fastcas/status') value = { enabled: true, link: { id: 'link', state: 'prepared', subject: 'reader', version: 1 } }
  else if (path === '/api/auth/local-credential') { status = 422; value = { detail: '原密码未通过校验' } }
  else if (path === '/api/papers') value = { items: [], total: 0 }
  await route.fulfill({ status, json: value })
})
try {
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(base)
  await page.getByRole('button', { name: '模型设置', exact: true }).click()
  await page.getByRole('button', { name: 'Reader', exact: true }).click()
  const model = page.getByRole('region', { name: '模型设置' })
  const account = page.getByRole('region', { name: '账号设置' })
  const name = model.getByLabel('名称', { exact: true })
  await name.fill('Research endpoint draft')
  await account.getByText('设置本地登录邮箱和密码', { exact: true }).click()
  await account.getByLabel('登录邮箱', { exact: true }).fill('reader@example.test')
  await account.getByLabel('新密码', { exact: true }).fill('long-password-draft')
  await name.focus()
  const peer = await context.newPage()
  await peer.goto(base)
  await peer.evaluate(() => localStorage.setItem('fastread.theme', 'dark'))
  await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'dark')
  await expect(name).toBeFocused()
  await expect(name).toHaveValue('Research endpoint draft')
  await expect(account.getByLabel('新密码', { exact: true })).toHaveValue('long-password-draft')
  await expect(name).toHaveClass(/fastui-input/)
  assert.equal(await name.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(23, 30, 39)')
  scenarios.push('cross-tab theme preserves both forms and focused input')
  await model.getByLabel('设置页颜色模式').selectOption('system')
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'light')
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'dark')
  scenarios.push('system follows browser preference without remount')
  const picker = model.getByLabel('当前使用的模型')
  await picker.selectOption('provider-1|model-b')
  await expect(picker).toHaveValue('provider-1|model-b')
  await name.focus(); await page.keyboard.press('Tab')
  await expect(model.getByLabel('API 地址', { exact: true })).toBeFocused()
  const save = model.getByRole('button', { name: '保存供应商' })
  await save.click()
  assert.equal(writes.length, 0, 'required fields must block submission')
  await model.getByLabel('API 地址', { exact: true }).fill('https://model.example.test/v1')
  await model.getByLabel('API 密钥', { exact: true }).fill('fixture-key')
  await save.click()
  await expect(page.getByRole('status').filter({ hasText: '供应商已保存' })).toBeVisible()
  assert.deepEqual(writes[0], { path: '/api/providers', body: { name: 'Research endpoint draft', base_url: 'https://model.example.test/v1', api_key: 'fixture-key', models: ['qwen3.8-27b', 'glm-5.2'] } })
  await expect(name).toHaveValue('')
  await expect(picker).toHaveValue('provider-1|model-b')
  scenarios.push('native select, Tab order, validation, FormData submit and reset')
  await account.getByRole('button', { name: '保存本地登录方式' }).click()
  await expect(account.getByRole('alert')).toHaveText('原密码未通过校验')
  await expect(account.getByLabel('新密码', { exact: true })).toHaveValue('')
  await expect(account.getByLabel('登录邮箱', { exact: true })).toHaveValue('reader@example.test')
  scenarios.push('account failure feedback and existing credential cleanup')
  for (const width of [1440, 1024, 390]) for (const mode of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 })
    await model.getByLabel('设置页颜色模式').selectOption(mode)
    for (const surface of [model, account]) {
      assert.ok(await surface.evaluate(el => el.scrollWidth <= el.clientWidth), 'settings surface overflows')
      await expect(surface.locator('.fastui-input').first()).toHaveCSS('background-color', mode === 'dark' ? 'rgb(23, 30, 39)' : 'rgb(255, 255, 255)')
    }
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: `${artifacts}/${mode}-${width}.png`, fullPage: true })
  }
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', scenarios, viewports: [1440, 1024, 390], modes: ['light', 'dark'] }, null, 2))
  console.log('PASS FastRead FastUI production settings/account browser scenarios')
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
