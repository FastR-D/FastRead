import { chromium, expect } from '@playwright/test'
import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { once } from 'node:events'
import assert from 'node:assert/strict'

const python = process.env.FASTREAD_TEST_PYTHON
if (!python) throw new Error('Set FASTREAD_TEST_PYTHON to the isolated backend Python.')
const artifacts = 'test-results/fastcas-modes'
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ headless: true })
const scenarios = [], errors = []
try {
  for (const mode of [
    { name: 'default-no-sdk-config', configured: false, enabled: false, login: false, link: false, state: 'none' },
    { name: 'global-off-partial-config', configured: false, global: 'false', enabled: false, login: false, link: false, state: 'none' },
    { name: 'login-off-link-on', configured: true, enabled: true, login: false, link: true, state: 'none' },
    { name: 'login-on-link-off', configured: true, enabled: true, login: true, link: false, state: 'none' },
    { name: 'prepared-link-off', configured: true, enabled: true, login: true, link: false, state: 'prepared' },
    { name: 'active-link-off', configured: true, enabled: true, login: false, link: false, state: 'active' },
  ]) {
    const listener = createServer()
    await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve))
    const port = listener.address().port
    await new Promise(resolve => listener.close(resolve))
    const base = `http://127.0.0.1:${port}`
    const root = await mkdtemp(join(tmpdir(), 'fastread-cas-modes-'))
    const env = { ...process.env }
    for (const key of Object.keys(env)) if (key.startsWith('FASTREAD_FASTCAS_')) delete env[key]
    Object.assign(env, {
      PYTHONUTF8: '1',
      ...(mode.global ? { FASTREAD_FASTCAS_ENABLED: mode.global } : {}),
      ...(mode.configured ? { FASTREAD_FASTCAS_LOGIN_ENABLED: String(mode.login), FASTREAD_FASTCAS_LINK_ENABLED: String(mode.link) } : {}),
      ...(mode.configured ? { FASTREAD_FASTCAS_ISSUER: 'https://cas.example.test', FASTREAD_FASTCAS_CLIENT_ID: 'read',
        FASTREAD_FASTCAS_CLIENT_SECRET: 'disposable-secret', FASTREAD_FASTCAS_REDIRECT_URI: base + '/api/auth/fastcas/callback' }
        : mode.global === 'false' ? { FASTREAD_FASTCAS_ISSUER: 'https://cas.example.test' } : {}),
    })
    const receiver = spawn(python, ['scripts/fastcas-modes-receiver.py', '--root', root, '--port', String(port), '--frontend', resolve('dist'), '--link-state', mode.state], { env, stdio: ['ignore', 'pipe', 'pipe'] })
    let log = ''
    for (const stream of [receiver.stdout, receiver.stderr]) stream.on('data', data => { log += data })
    const context = await browser.newContext({ serviceWorkers: 'block' })
    try {
      await expect.poll(async () => { try { return (await fetch(base + '/api/health')).ok } catch { return false } }, { timeout: 20000, message: mode.name }).toBe(true)
      const page = await context.newPage()
      page.on('pageerror', error => errors.push(error.message))
      await page.goto(base)
      await expect(page.getByRole('heading', { name: '登录资料库' })).toBeVisible()
      const available = await (await context.request.get(base + '/api/auth/fastcas/available')).json()
      assert.deepEqual(available, { enabled: mode.enabled, login_enabled: mode.login, link_enabled: mode.link })
      await expect(page.getByRole('link', { name: '使用 FastCAS 登录' })).toHaveCount(mode.login ? 1 : 0)
      if (!mode.login) assert.equal((await context.request.get(base + '/api/auth/fastcas/login')).status(), mode.enabled ? 403 : 404)
      await page.getByLabel('邮箱', { exact: true }).fill('reader@example.test')
      await page.getByLabel('密码', { exact: true }).fill('fixture-password-1234')
      await page.getByRole('button', { name: '确认', exact: true }).click()
      await page.getByRole('button', { name: '账号设置', exact: true }).click()
      const account = page.getByRole('region', { name: '账号设置' })
      const status = await (await context.request.get(base + '/api/auth/fastcas/status')).json()
      assert.equal(status.link_enabled, mode.link)
      if (!mode.enabled) {
        await expect(account.getByText('此实例未启用 FastCAS，本地登录照常可用。')).toBeVisible()
      } else {
        await account.getByLabel('当前账号密码', { exact: true }).fill('fixture-password-1234')
        if (mode.state === 'none') {
          const link = account.getByRole('button', { name: '认证当前账号', exact: true })
          if (mode.link) await expect(link).toBeEnabled()
          else await expect(link).toBeDisabled()
        } else {
          if (mode.state === 'prepared') await expect(account.getByRole('button', { name: '重试完成认证', exact: true })).toBeDisabled()
          await expect(account.getByRole('button', { name: '解除认证', exact: true })).toBeEnabled()
        }
        if (!mode.link) {
          const me = await (await context.request.get(base + '/api/auth/me')).json()
          const denied = await context.request.post(base + '/api/auth/fastcas/link', { headers: { Origin: base, 'X-CSRF-Token': me.csrf }, data: { password: 'fixture-password-1234' } })
          assert.equal(denied.status(), 403)
        }
      }
      await account.getByText('设置本地登录邮箱和密码', { exact: true }).click()
      await expect(account.getByLabel('新密码', { exact: true })).toBeVisible()
      await page.screenshot({ path: `${artifacts}/${mode.name}.png`, fullPage: true })
      scenarios.push({ name: mode.name, status: 'passed', available, link_state: status.link?.state || null })
    } catch (error) {
      throw new Error(`${mode.name}: ${error.message}\n${log}`, { cause: error })
    } finally {
      await context.close()
      if (receiver.exitCode === null && receiver.signalCode === null) {
        const exited = once(receiver, 'exit')
        receiver.kill()
        await exited
      }
    }
  }
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', backend: 'create_web_app + SQLite + real local cookie/CSRF; no HTTP interception', scenarios }, null, 2))
  console.log(`PASS ${scenarios.length} real FastRead backend + Chromium account/login mode scenarios`)
} finally { await browser.close() }
