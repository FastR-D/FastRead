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
let signedIn = true
let availability = { enabled: true, login_enabled: true, link_enabled: true }
let accountStatus = { enabled: true, link_enabled: true, link: { id: 'link', state: 'prepared', subject: 'reader', version: 1 } }
await context.route('**/api/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() === 'POST') writes.push({ path, body: request.postDataJSON() })
  let value = { items: [] }, status = 200
  if (path === '/api/auth/me') {
    status = signedIn ? 200 : 401
    value = signedIn ? { id: 'reader', display_name: 'Reader', role: 'owner', workspace_id: 'workspace', csrf: 'fixture-csrf', workspace: { name: 'Workspace', daily_limit: 24 } } : { detail: 'Login required' }
  }
  else if (path === '/api/auth/fastcas/available') value = availability
  else if (path === '/api/providers') {
    if (request.method() === 'POST') providers = [...providers, { id: 'provider-2', ...request.postDataJSON() }]
    value = { items: providers }
  } else if (path === '/api/auth/fastcas/status') value = accountStatus
  else if (path === '/api/auth/local-credential') { status = 422; value = { detail: '原密码未通过校验' } }
  else if (path === '/api/papers') value = { items: [], total: 0 }
  await route.fulfill({ status, json: value })
})
try {
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(base)
  await page.getByRole('button', { name: '模型设置', exact: true }).click()
  await page.getByRole('button', { name: '账号设置', exact: true }).click()
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
  // Merge regression: independent server modes must survive the real FastUI account surface.
  for (const link of [null, { id: 'link', state: 'prepared', subject: 'reader', version: 1 }]) {
    accountStatus = { enabled: true, link_enabled: false, link }
    await page.reload()
    await page.getByRole('button', { name: '账号设置', exact: true }).click()
    await account.getByLabel('当前账号密码', { exact: true }).fill('original-password')
    const blocked = account.getByRole('button', { name: link ? '重试完成认证' : '认证当前账号', exact: true })
    await expect(blocked).toBeDisabled()
    if (link) await expect(account.getByRole('button', { name: '解除认证', exact: true })).toBeEnabled()
    const count = writes.length
    await blocked.evaluate(button => button.click())
    assert.equal(writes.length, count)
  }
  accountStatus = { enabled: true, link_enabled: true, link: null }
  await page.reload()
  await page.getByRole('button', { name: '账号设置', exact: true }).click()
  await account.getByLabel('当前账号密码', { exact: true }).fill('original-password')
  await expect(account.getByRole('button', { name: '认证当前账号', exact: true })).toBeEnabled()
  accountStatus = { enabled: false, link_enabled: false, link: null }
  await page.reload()
  await page.getByRole('button', { name: '账号设置', exact: true }).click()
  await expect(account.getByText('此实例未启用 FastCAS，本地登录照常可用。')).toBeVisible()
  await expect(account.getByRole('button', { name: '认证当前账号', exact: true })).toHaveCount(0)
  scenarios.push('link-off blocks new and prepared activation, keeps revoke; enabled and provider-off account states')
  signedIn = false
  for (const flags of [
    { enabled: true, login_enabled: true, link_enabled: false },
    { enabled: true, login_enabled: false, link_enabled: true },
    { enabled: false, login_enabled: false, link_enabled: false },
  ]) {
    availability = flags
    await page.reload()
    await expect(page.getByRole('heading', { name: '登录资料库' })).toBeVisible()
    await expect.poll(() => page.getByRole('link', { name: '使用 FastCAS 登录' }).count()).toBe(flags.enabled && flags.login_enabled ? 1 : 0)
    if (flags.login_enabled) await expect(page.getByRole('link', { name: '使用 FastCAS 登录' })).toHaveAttribute('href', '/api/auth/fastcas/login')
    await page.getByRole('button', { name: '使用邀请注册', exact: true }).click()
    await expect(page.getByRole('heading', { name: '邀请注册' })).toBeVisible()
    await expect(page.getByRole('link', { name: '使用 FastCAS 登录' })).toHaveCount(0)
    await page.getByRole('button', { name: '恢复账号', exact: true }).click()
    await expect(page.getByRole('heading', { name: '恢复账号' })).toBeVisible()
  }
  scenarios.push('independent login visibility with local invitation/recovery always usable')
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', scenarios, viewports: [1440, 1024, 390], modes: ['light', 'dark'] }, null, 2))
  console.log('PASS FastRead FastUI production settings/account browser scenarios')
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
