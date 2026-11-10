import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import { createServer } from 'node:http'
import { spawn, spawnSync } from 'node:child_process'
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import assert from 'node:assert/strict'

const python = process.env.FASTREAD_TEST_PYTHON
if (!python) throw new Error('Set FASTREAD_TEST_PYTHON to a Python with Read backend requirements and News werkzeug installed.')
const contract = JSON.parse(await readFile('../contracts/fastnews-intake/v1/cases.json', 'utf8'))
const news = resolve('../../fast-news/serve.py')
const artifacts = 'test-results/fastnews'
await mkdir(artifacts, { recursive: true })
const work = await mkdtemp(join(tmpdir(), 'fastread-ui-wire-'))
const ticketCalls = [], results = [], errors = []
const research = createServer(async (request, response) => {
  let raw = ''; for await (const chunk of request) raw += chunk
  const body = JSON.parse(raw || '{}')
  assert.equal(request.url, '/api/sso/consume')
  assert.equal(body.audience, 'fast-read')
  ticketCalls.push(body.ticket)
  response.setHeader('Content-Type', 'application/json')
  if (body.ticket === 'expired-ticket') { response.writeHead(401).end(JSON.stringify({ error: 'Expired ticket' })); return }
  response.end(JSON.stringify({ keyId: body.ticket, person: 'News reader' }))
})
await new Promise(resolve => research.listen(0, '127.0.0.1', resolve))
const listener = createServer()
await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve))
const port = listener.address().port
await new Promise(resolve => listener.close(resolve))
const backend = `http://127.0.0.1:${port}`
const receiver = spawn(python, ['scripts/fastnews-receiver.py', '--root', work, '--port', String(port), '--research', `http://127.0.0.1:${research.address().port}`], { env: { ...process.env, PYTHONUTF8: '1' }, stdio: ['ignore', 'pipe', 'pipe'] })
let serverLog = ''
for (const stream of [receiver.stdout, receiver.stderr]) stream.on('data', bytes => { serverLog += bytes })
let server, browser
try {
  await expect.poll(async () => { try { return (await fetch(`${backend}/api/health`)).ok } catch { return false } }, { timeout: 20000, message: 'Read fixture must start: ' + serverLog }).toBe(true)
  server = await preview({ configFile: false, plugins: [{ name: 'subpath-deployment', configurePreviewServer(server) {
    server.middlewares.use((request, _response, next) => { if (request.url.startsWith('/read/')) request.url = request.url.slice('/read'.length); next() })
  } }], preview: { host: '127.0.0.1', port: 0, proxy: { '/api': { target: backend, changeOrigin: false } } } })
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`
  browser = await chromium.launch({ headless: true })
  function handoff(base, ticket = '', paper = contract.handoff) {
    const result = spawnSync(python, ['-c', 'import json,os,runpy,sys; sys.path.insert(0,os.path.dirname(sys.argv[1])); os.environ["FASTREAD_URL"]=sys.argv[2]; app=runpy.run_path(sys.argv[1],run_name="browser_sender"); status,payload=app["build_fastread_handoff"](json.loads(sys.stdin.read()),ticket=sys.argv[3]); assert status==200; print(json.dumps(payload))', news, base.replace(/\/$/, ''), ticket], { env: { ...process.env, PYTHONUTF8: '1' }, input: JSON.stringify(paper), encoding: 'utf8' })
    assert.equal(result.status, 0, result.stderr)
    return JSON.parse(result.stdout).redirect
  }
  async function login(context, base) {
    const init = await context.request.get(base + 'api/auth/session-init')
    const result = await context.request.post(base + 'api/auth/login', { headers: { 'X-CSRF-Token': (await init.json()).csrf }, data: { email: 'reader@example.test', password: 'fixture-password-1234' } })
    assert.equal(result.status(), 200)
  }
  async function session(prefix) {
    const base = origin + prefix
    const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage(), posts = [], receipts = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (new URL(request.url()).pathname === prefix + 'api/integrations/fastnews/intake') posts.push(request.postDataJSON()) })
    page.on('response', async response => { if (new URL(response.url()).pathname === prefix + 'api/integrations/fastnews/intake' && response.ok()) receipts.push(await response.json()) })
    const saved = page.getByRole('status').filter({ hasText: '已收入' })
    return { base, context, page, posts, receipts, saved }
  }
  for (const prefix of ['/', '/read/']) {
    for (const ticket of ['', `ticket-${prefix === '/' ? 'root' : 'subpath'}`]) {
      const { base, context, page, posts, receipts, saved } = await session(prefix)
      if (!ticket) await login(context, base)
      await page.goto(handoff(base, ticket))
      await expect(saved).toContainText(contract.intake.title)
      assert.deepEqual(posts, [contract.intake])
      await expect.poll(() => receipts.length).toBe(1)
      const receipt = receipts[0]
      if (ticket) for (const [key, value] of Object.entries(contract.first_receipt)) assert.equal(receipt[key], value)
      const stored = await (await context.request.get(base + 'api/papers/' + receipt.id)).json()
      assert.equal(stored.title, contract.intake.title)
      assert.equal(stored.metadata.source, 'fastnews')
      assert.equal(stored.metadata.url, contract.intake.url)
      assert.equal((await (await context.request.get(base + 'api/jobs')).json()).items.length, 0, 'metadata intake must not start a PDF/model job')
      assert.ok(!page.url().includes('sso=') && !page.url().includes('#fastnews='))
      assert.equal(await page.evaluate(() => Object.keys(sessionStorage).some(key => key.startsWith('fastread:fastnews:'))), false)
      if (ticket) assert.equal(ticketCalls.filter(value => value === ticket).length, 1)
      await page.reload()
      await expect(page.getByRole('button', { name: '模型设置', exact: true })).toBeVisible()
      assert.equal(posts.length, 1, 'successful handoff must not repeat after refresh')
      await page.screenshot({ path: `${artifacts}/${prefix === '/' ? 'root' : 'subpath'}-${ticket ? 'ticket' : 'session'}.png` })
      results.push({ prefix, scenario: ticket ? 'actual News fragment + ticket + real persisted receipt' : 'actual News fragment + existing session', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, receipts, saved } = await session(prefix)
      await login(context, base)
      await page.goto(handoff(base))
      await expect(saved).toContainText(contract.intake.title)
      await expect.poll(() => receipts.length).toBe(1)
      const id = receipts[0].id
      await page.goto(handoff(base))
      await expect(saved).toContainText(contract.intake.title)
      await expect.poll(() => receipts.length).toBe(2)
      assert.equal(receipts[1].id, id)
      for (const [key, value] of Object.entries(contract.repeat_receipt)) assert.equal(receipts[1][key], value)
      assert.deepEqual(posts, [contract.intake, contract.intake])
      results.push({ prefix, scenario: 'explicit repeat handoff follows receiver deduplication receipt', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      const ticket = `held-ticket-${prefix === '/' ? 'root' : 'subpath'}`
      let started = false, release
      const gate = new Promise(resolve => { release = resolve })
      await page.route('**/api/auth/research', async route => { started = true; await gate; await route.continue() })
      try {
        await page.goto(handoff(base, ticket))
        await expect.poll(() => started).toBe(true)
        assert.equal(new URL(page.url()).searchParams.has('sso'), false, 'remove the ticket before the exchange completes')
        assert.equal(await page.evaluate(ticket => JSON.stringify(Object.values(sessionStorage)).includes(ticket), ticket), false)
        assert.equal(posts.length, 0)
        await expect(saved).toHaveCount(0)
      } finally { release() }
      await expect(saved).toContainText(contract.intake.title)
      assert.equal(ticketCalls.filter(value => value === ticket).length, 1)
      results.push({ prefix, scenario: 'ticket removed promptly, never persisted, consumed once before intake', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      await login(context, base)
      let release
      const gate = new Promise(resolve => { release = resolve })
      await page.route('**/api/integrations/fastnews/intake', async route => { await gate; await route.continue() })
      try {
        await page.goto(handoff(base))
        await expect.poll(() => posts.length).toBe(1)
        await expect(saved).toHaveCount(0)
      } finally { release() }
      await expect(saved).toContainText(contract.intake.title)
      results.push({ prefix, scenario: 'no success before the actual POST receipt', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      await login(context, base)
      const title = '字面 + %2F # & 科学'
      await page.goto(handoff(base, '', { ...contract.handoff, title }))
      await expect(saved).toContainText(title)
      assert.deepEqual(posts, [{ ...contract.intake, title }], 'decode percent-encoded JSON once, retaining literal plus/percent characters')
      results.push({ prefix, scenario: 'actual sender Unicode/plus/percent fragment decoded exactly once', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      await page.goto(handoff(base))
      await expect(page.getByRole('heading', { name: '登录资料库' })).toBeVisible()
      await expect(saved).toHaveCount(0)
      assert.equal(posts.length, 0)
      // Navigate away from the original fragment; the pending payload must survive local login.
      await page.goto(base)
      await page.getByLabel('邮箱', { exact: true }).fill('reader@example.test')
      await page.getByLabel('密码', { exact: true }).fill('fixture-password-1234')
      await page.getByRole('button', { name: '确认', exact: true }).click()
      await expect(saved).toContainText(contract.intake.title)
      assert.deepEqual(posts, [contract.intake])
      results.push({ prefix, scenario: 'anonymous arrival, persisted pending, actual local login and intake', status: 'passed' })
      await context.close()
    }
    for (const failure of ['401', '403', '422', 'network', 'receipt']) {
      const { base, context, page, posts, saved } = await session(prefix)
      await login(context, base)
      let failing = true
      await page.route('**/api/integrations/fastnews/intake', async route => {
        if (!failing) return route.continue()
        const headers = { ...route.request().headers() }
        if (failure === 'network') return route.abort('failed')
        if (failure === 'receipt') return route.fulfill({ json: { id: 'not-a-receipt' } })
        if (failure === '401') headers.cookie = ''
        if (failure === '403') headers['x-csrf-token'] = 'wrong'
        const response = await route.fetch({ headers, ...(failure === '422' ? { postData: JSON.stringify({ ...contract.intake, title: 'x'.repeat(301) }) } : {}) })
        assert.equal(response.status(), Number(failure), 'exercise the actual receiver rejection')
        return route.fulfill({ response })
      })
      await page.goto(handoff(base))
      const retry = page.getByRole('button', { name: '重试收入', exact: true })
      await expect(retry).toBeVisible()
      await expect(saved).toHaveCount(0)
      assert.ok(page.url().includes('#fastnews='))
      await page.reload()
      await expect(retry).toBeVisible()
      await expect(saved).toHaveCount(0)
      failing = false
      await retry.click()
      await expect(saved).toContainText(contract.intake.title)
      assert.deepEqual(posts.at(-1), contract.intake)
      results.push({ prefix, scenario: `retained payload and explicit retry after ${failure}`, status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      await login(context, base)
      const title = '  ' + contract.intake.title.replaceAll(' ', '  ') + '  '
      const query = new URLSearchParams({ source: 'fastnews', ...contract.intake, title })
      await page.goto(base + '?' + query)
      await expect(saved).toContainText(contract.intake.title)
      assert.deepEqual(posts, [{ ...contract.intake, title }])
      results.push({ prefix, scenario: 'existing explicit query intake, canonical external_id, receiver-normalized title', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      await login(context, base)
      await page.goto(handoff(base, 'expired-ticket'))
      await expect(page.getByRole('heading', { name: '登录资料库' })).toBeVisible()
      assert.equal(posts.length, 0)
      assert.equal(new URL(page.url()).searchParams.has('sso'), false)
      await expect(saved).toHaveCount(0)
      await page.reload()
      await expect(page.getByRole('heading', { name: '登录资料库' })).toBeVisible()
      assert.equal(posts.length, 0, 'reload after a failed ticket must not use the previous account session')
      await page.getByLabel('邮箱', { exact: true }).fill('reader@example.test')
      await page.getByLabel('密码', { exact: true }).fill('fixture-password-1234')
      await page.getByRole('button', { name: '确认', exact: true }).click()
      await expect(saved).toContainText(contract.intake.title)
      results.push({ prefix, scenario: 'expired ticket cleaned; no intake until local authentication', status: 'passed' })
      await context.close()
    }
    {
      const { base, context, page, posts, saved } = await session(prefix)
      await login(context, base)
      await page.goto(base + '?' + new URLSearchParams({ source: 'fastnews', ...contract.intake }) + '#fastnews=%invalid')
      await expect(page.getByRole('alert').filter({ hasText: 'FastNews' })).toBeVisible()
      await expect(saved).toHaveCount(0)
      assert.equal(posts.length, 0, 'malformed fragment must not fall back to the query shape')
      results.push({ prefix, scenario: 'malformed fragment fails explicitly without query fallback', status: 'passed' })
      await context.close()
    }
  }
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', sender: 'News serve.py build_fastread_handoff', receiver: 'Read create_web_app + isolated SQLite + real cookie/CSRF', scenarios: results }, null, 2))
  console.log(`PASS ${results.length} actual News → browser → Read wire scenarios`)
} finally {
  await browser?.close()
  if (server) await new Promise(resolve => server.httpServer.close(resolve))
  receiver.kill()
  await new Promise(resolve => research.close(resolve))
}
