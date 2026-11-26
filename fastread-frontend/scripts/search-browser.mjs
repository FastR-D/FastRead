import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
const server = await preview({ configFile: false, preview: { host: '127.0.0.1', port: 0 } })
const base = `http://127.0.0.1:${server.httpServer.address().port}`
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' })
const writes = [], errors = [], jobs = []
const book = { id: 'search-book', name: '检索研究', paper_count: 0, papers: [] }
await context.route('https://**', route => route.abort())
await context.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname.replace('/api', '')
  const body = route.request().method() === 'POST' ? route.request().postDataJSON() : null
  if (body) writes.push({ path, body })
  let value = { items: [] }, status = 200
  if (path === '/auth/me') value = { id: 'reader', display_name: 'Reader', csrf: 'fixture', workspace: { name: 'Workspace', daily_limit: 24 } }
  else if (path === '/papers') value = { items: [], total: 0 }
  else if (path === '/knowledge-bases') value = { items: [book] }
  else if (path === '/knowledge-bases/search-book') value = book
  else if (path === '/search') {
    if (body.query === 'error') { status = 503; value = { detail: '检索暂不可用' } }
    else value = { sources: { crossref: { available: true } }, papers: body.query === 'empty' ? [] : [{ id: body.query, title: body.query, authors: ['Researcher'], year: 2026, url: `https://example.test/${encodeURIComponent(body.query)}.pdf`, abstract: 'Research evidence.' }] }
  } else if (path === '/imports/url') { value = { id: `job-${jobs.length}`, kind: 'import_url', state: 'queued' }; jobs.push(value) }
  else if (path === '/jobs') value = { items: jobs.map(job => ({ ...job, state: 'succeeded' })) }
  await route.fulfill({ status, json: value })
})
try {
  const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message))
  await page.goto(base)
  await page.getByRole('button', { name: '搜索论文', exact: true }).click()
  const search = page.getByRole('region', { name: '搜索论文', exact: true })
  await expect(search).toBeVisible(); await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(search.getByLabel('搜索结果导入知识库')).toHaveValue('')
  const query = search.getByLabel('搜索公开论文')
  await query.fill('Grounded retrieval'); await query.press('Enter')
  await expect(search.getByRole('heading', { name: 'Grounded retrieval', exact: true })).toBeVisible()
  await query.fill('empty'); await query.press('Enter'); await expect(search.getByText('没有找到匹配的论文，试试其他标题、DOI 或关键词。')).toBeVisible()
  await query.fill('error'); await query.press('Enter'); await expect(search.getByRole('alert')).toHaveText('检索暂不可用')
  await query.fill('Recoverable search'); await query.press('Enter')
  await expect(search.getByRole('heading', { name: 'Recoverable search' })).toBeVisible()
  await search.getByRole('button', { name: '返回阅读', exact: true }).click()
  await page.getByRole('navigation', { name: '知识库目录' }).getByRole('button', { name: '检索研究' }).click()
  await page.getByRole('button', { name: '搜索论文', exact: true }).click()
  await expect(search.getByLabel('搜索结果导入知识库')).toHaveValue('search-book')
  await query.fill('Knowledge search'); await query.press('Enter')
  await search.getByRole('button', { name: '导入这篇论文', exact: true }).click()
  await expect(search.getByRole('button', { name: '已导入', exact: true })).toBeDisabled({ timeout: 10000 })
  assert.equal(writes.filter(write => write.path === '/imports/url').length, 1)
  assert.equal(writes.find(write => write.path === '/imports/url').body.knowledge_id, 'search-book')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await mkdir('test-results/search', { recursive: true })
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({ path: `test-results/search/search-${width}.png` })
  }
  await search.getByRole('button', { name: '返回阅读', exact: true }).click()
  await expect(search).toHaveCount(0)
  await expect(page.getByRole('button', { name: '搜索论文', exact: true })).toBeVisible()
  assert.match(page.url(), /book=search-book/)
  assert.deepEqual(errors, [])
  console.log('PASS inline search, repeat query, empty/error recovery, knowledge destination, import status, return and responsive layouts')
} finally { await context.close(); await browser.close(); await new Promise(resolve => server.httpServer.close(resolve)) }
