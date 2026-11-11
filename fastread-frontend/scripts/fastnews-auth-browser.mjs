import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { chromium, expect } from '@playwright/test'

const python = process.env.FASTREAD_TEST_PYTHON
if (!python) throw new Error('Set FASTREAD_TEST_PYTHON to Python with the published fastcas-sdk 0.1.2.')
const artifacts = process.env.FASTREAD_AUTH_ARTIFACTS || 'test-results/fastnews-auth'
await mkdir(artifacts, { recursive: true })
const listener = createServer()
await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve))
const port = listener.address().port
await new Promise(resolve => listener.close(resolve))
const origin = `http://127.0.0.1:${port}`
const root = await mkdtemp(join(tmpdir(), 'fastread-news-auth-'))
const child = spawn(python, ['-B', 'scripts/fastnews-auth-receiver.py', '--root', root, '--port', String(port)],
  { env: { ...process.env, PYTHONUTF8: '1' }, stdio: ['ignore', 'pipe', 'pipe'] })
let log = '', browser
const results = [], errors = []
for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => { log += chunk })
try {
  await expect.poll(async () => { try { return (await fetch(origin+'/api/health')).ok } catch { return false } }, { timeout: 20000 }).toBe(true)
  browser = await chromium.launch({ headless: true })
  const cases = ['cas', 'local', 'research'].flatMap(flow => ['none', 'other-account', 'same-account'].map(oldSession => ({ flow, oldSession })))
  cases.unshift({ flow: 'cas', oldSession: 'none', direct: true })
  cases.push(...['baseline', 'proof'].map(failure => ({ flow: 'cas', oldSession: 'other-account', failure })))
  for (const { flow, oldSession, failure, direct } of cases) {
    const context = await browser.newContext({ serviceWorkers: 'block' })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    const posts = []
    page.on('request', request => { if (new URL(request.url()).pathname === '/api/integrations/fastnews/intake') posts.push(request.postDataJSON()) })
    const pending = () => page.evaluate(() => Object.entries(sessionStorage).filter(([key]) => key.startsWith('fastread:fastnews:')).map(([, value]) => JSON.parse(value)))
    async function login(email) {
      const init = await context.request.get(origin+'/api/auth/session-init')
      const response = await context.request.post(origin+'/api/auth/login', { headers: { 'X-CSRF-Token': (await init.json()).csrf }, data: { email, password: 'fixture-password-1234' } })
      assert.equal(response.status(), 200)
      return (await (await context.request.get(origin+'/api/auth/me')).json())
    }
    let old = null
    if (flow === 'research' && oldSession === 'same-account') {
      const response = await context.request.post(origin+'/api/auth/research', { data: { ticket: 'valid-research' } })
      assert.equal(response.status(), 200)
      old = await (await context.request.get(origin+'/api/auth/me')).json()
    } else if (oldSession !== 'none') old = await login(oldSession === 'same-account' ? 'cas@example.test' : 'old@example.test')
    const oldContext = old ? await browser.newContext({ storageState: await context.storageState() }) : null
    const caseId = `${flow}-${oldSession}${direct ? '-direct' : ''}${failure ? '-'+failure : ''}`
    const carrier = { source: 'fastnews', id: `auth-${caseId}`, title: `Pending via ${caseId}`, authors: '', abstract: '', url: 'https://example.test/paper', venue: '', year: '2026' }
    const arrival = origin+'/?sso=expired-ticket#fastnews='+encodeURIComponent(JSON.stringify(carrier))
    if (failure === 'baseline') await page.route('**/api/auth/me', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }), { times: 1 })
    await page.goto(arrival)
    if (failure === 'baseline') {
      await expect(page.getByRole('heading', { name: '连接暂时中断' })).toBeVisible()
      assert.equal(posts.length, 0)
      assert.equal((await pending())[0].status, 'login-required')
      assert.equal(new URL(page.url()).searchParams.has('sso'), false)
      await page.goto(origin)
    }
    await expect(page.getByRole('heading', { name: '登录资料库', exact: true })).toBeVisible()
    assert.equal(posts.length, 0)
    assert.equal((await pending())[0].status, 'login-required')
    if (!direct) {
      await page.reload()
      await expect(page.getByRole('heading', { name: '登录资料库', exact: true })).toBeVisible()
      assert.equal(posts.length, 0, 'failed ticket must not use an old cookie after reload')
      // Callback query text is not authentication proof, even with /me=200 from an old account.
      await page.goto(origin+'/?fastcas=complete')
      await expect(page.getByRole('heading', { name: '登录资料库', exact: true })).toBeVisible()
      assert.equal(posts.length, 0)
    }
    let releaseProof
    if (flow === 'cas') {
      if (!direct) {
        // An invalid production callback must also leave the old session blocked.
        await page.goto(origin+'/api/auth/fastcas/callback?code=invalid&state=invalid')
        await expect(page.getByRole('heading', { name: '登录资料库', exact: true })).toBeVisible()
        assert.equal(posts.length, 0)
      }
      // Hold the actual /me response after CAS, never synthesize authentication.
      // The new cookie and callback query alone must not dispatch intake.
      let proofStarted = false
      const gate = new Promise(resolve => { releaseProof = resolve })
      await page.route('**/api/auth/me', async route => {
        proofStarted = true
        await gate
        if (failure === 'proof') await route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
        else await route.continue()
      }, { times: 1 })
      await page.getByRole('link', { name: '使用 FastCAS 登录', exact: true }).click()
      await page.waitForURL(url => url.origin === origin && url.searchParams.get('fastcas') === 'complete')
      await expect.poll(() => proofStarted).toBe(true)
      assert.equal(posts.length, 0)
      assert.equal((await pending())[0].status, 'login-required')
    } else if (flow === 'local') {
      await page.getByLabel('邮箱', { exact: true }).fill('cas@example.test')
      await page.getByLabel('密码', { exact: true }).fill('wrong-password')
      await page.getByRole('button', { name: '确认', exact: true }).click()
      await expect(page.getByRole('status').filter({ hasText: '邮箱或密码错误' })).toBeVisible()
      assert.equal(posts.length, 0)
      await page.getByLabel('密码', { exact: true }).fill('fixture-password-1234')
      await page.getByRole('button', { name: '确认', exact: true }).click()
    } else {
      await page.goto(origin+'/?sso=valid-research')
    }
    await expect.poll(async () => {
      const response = await context.request.get(origin+'/api/auth/me')
      if (!response.ok()) return false
      const user = await response.json()
      return !!user.csrf && user.csrf !== old?.csrf
    }, { message: `${flow}: newly issued authenticated session` }).toBe(true)
    const me = await context.request.get(origin+'/api/auth/me')
    assert.equal(me.status(), 200)
    const user = await me.json()
    releaseProof?.()
    if (failure === 'proof') {
      await expect(page.getByRole('heading', { name: '连接暂时中断' })).toBeVisible()
      assert.equal(posts.length, 0)
      assert.equal((await pending())[0].status, 'login-required')
      await page.reload()
    }
    try {
      await expect(page.getByRole('status').filter({ hasText: '已收入' })).toContainText(carrier.title, { timeout: 10000 })
    } catch (error) {
      const observed = { flow, oldSession, backendMeStatus: me.status(), frontendLoginVisible: await page.getByRole('heading', { name: '登录资料库', exact: true }).isVisible(), pending: await pending(), intakePosts: posts.length }
      await writeFile(`${artifacts}/failure.json`, JSON.stringify(observed, null, 2))
      await page.screenshot({ path: `${artifacts}/failure.png`, fullPage: true })
      throw error
    }
    assert.equal(posts.length, 1)
    assert.equal(posts[0].external_id, carrier.id)
    assert.deepEqual(await pending(), [])
    if (old) {
      assert.notEqual(user.csrf, old.csrf)
      if (oldSession === 'same-account') assert.equal(user.workspace_id, old.workspace_id)
      else assert.notEqual(user.workspace_id, old.workspace_id)
    }
    const listing = await (await context.request.get(origin+'/api/papers')).json()
    const stored = listing.items.find(paper => paper.title === carrier.title)
    assert.ok(stored)
    if (oldContext && user.workspace_id !== old.workspace_id) {
      assert.equal((await oldContext.request.get(origin+'/api/papers/'+stored.id)).status(), 404)
      const oldListing = await (await oldContext.request.get(origin+'/api/papers')).json()
      assert.ok(!oldListing.items.some(paper => paper.title === carrier.title))
    }
    await page.reload()
    await expect(page.getByRole('button', { name: '模型设置', exact: true })).toBeVisible()
    assert.equal(posts.length, 1)
    await page.screenshot({ path: `${artifacts}/${caseId}.png` })
    results.push({ flow, oldSession, ...(direct ? { direct } : {}), ...(failure ? { failure } : {}), status: 'passed', intakePosts: posts.length, backendMeStatus: me.status() })
    await context.close()
    await oldContext?.close()
  }
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', boundary: 'published SDK 0.1.2 + OIDC HTTP PKCE/nonce/signature + production callback + SQLite + built UI', scenarios: results }, null, 2))
  console.log(`PASS ${results.length} failed News ticket → fresh authentication → persisted intake browser scenarios`)
} finally {
  await browser?.close()
  if (child.exitCode === null && child.signalCode === null) {
    const exited = once(child, 'exit')
    child.kill()
    await exited
  }
  await writeFile(`${artifacts}/receiver.log`, log)
}
