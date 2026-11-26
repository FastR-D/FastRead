import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'

const artifacts = 'test-results/continuous-reader'
await mkdir(artifacts, { recursive: true })
const server = await preview({ configFile: false, preview: { host: '127.0.0.1', port: 0 } })
const base = `http://127.0.0.1:${server.httpServer.address().port}`
const browser = await chromium.launch({
  channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
  headless: true,
})
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  serviceWorkers: 'block',
  colorScheme: 'light',
})
const page = await context.newPage(),
  errors = [],
  scenarios = [],
  writes = [],
  reads = []
page.on('pageerror', error => errors.push(error.message))
page.setDefaultTimeout(15000)
const papers = ['paper-1', 'paper-2'].map((id, i) => ({
  id,
  title: `Research Paper ${i + 1}`,
  active_version: 'v1',
  page_count: 40,
  summary: '',
  year: 2026,
  tags: ['retrieval'],
  principle: 'Evidence grounded retrieval.',
  metadata: { authors: ['Reader'], page_count: 40, year: 2026 },
  versions: [
    { id: 'v1', page_count: 40, created: 1794484800 },
    { id: 'v2', page_count: 40, created: 1794398400 },
  ],
  knowledge_bases: [],
}))
const books = [
  {
    id: 'book-1',
    name: 'Research library',
    paper_count: 2,
    description: 'Compare retrieval methods.',
  },
]
let failNextChat = true
let notes = [],
  annotations = [],
  messages = []
const report = {
  id: 'report-1',
  version_id: 'v1',
  content: {
    key_questions: [
      {
        question: 'What is studied?',
        answer: 'A reading workflow.',
        evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
      },
    ],
    process: [],
    contributions: [],
  },
}
function textPdf() {
  const count = 40,
    kids = Array.from({ length: count }, (_, i) => `${4 + i * 2} 0 R`).join(' ')
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R /Outlines 84 0 R >>',
    `<< /Type /Pages /Kids [${kids}] /Count ${count} >>`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  for (let i = 0; i < count; i++) {
    const landscape = i === 2,
      w = landscape ? 842 : 595,
      h = landscape ? 595 : 842
    const stream = `BT /F1 18 Tf 50 ${h - 60} Td (Document page ${i + 1}) Tj 0 -32 Td /F1 12 Tf (Research methods and reproducible evidence.) Tj ET`
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${5 + i * 2} 0 R >>`,
      `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`
    )
  }
  objects.push(
    '<< /Type /Outlines /First 85 0 R /Last 85 0 R /Count 1 >>',
    '<< /Title (Methods) /Parent 84 0 R /Dest [42 0 R /Fit] >>'
  )
  let data = '%PDF-1.4\n',
    offsets = [0]
  objects.forEach((o, i) => {
    offsets.push(Buffer.byteLength(data))
    data += `${i + 1} 0 obj\n${o}\nendobj\n`
  })
  const xref = Buffer.byteLength(data)
  data += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets
    .slice(1)
    .map(o => `${String(o).padStart(10, '0')} 00000 n \n`)
    .join('')}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(data)
}
await context.route('**/api/**', async route => {
  const req = route.request(),
    url = new URL(req.url()),
    path = url.pathname.replace('/api', '')
  const body = ['POST', 'PUT', 'PATCH'].includes(req.method()) ? req.postDataJSON() : null
  if (body) writes.push({ path, body })
  if (req.method() === 'GET' && path !== '/jobs') reads.push(path)
  if (path.endsWith('/file'))
    return route.fulfill({ contentType: 'application/pdf', body: textPdf() })
  let value = { items: [] }
  if (path === '/auth/me')
    value = {
      id: 'reader',
      role: 'owner',
      csrf: 'fixture',
      workspace_id: 'workspace',
      workspace: { name: 'Workspace', daily_limit: 24 },
    }
  else if (path === '/providers')
    value = { items: [{ id: 'provider-1', name: 'Model', models: ['model-a'] }] }
  else if (path === '/papers') value = { items: papers, total: papers.length }
  else if (path === '/knowledge-bases') {
    if (body) books.push({ id: 'created-book', ...body, paper_count: 0 })
    value = body ? books.at(-1) : { items: books }
  } else if (path === '/tags') value = { items: [{ tag: 'retrieval', paper_count: 2 }] }
  else if (/^\/knowledge-bases\/[^/]+$/.test(path))
    value = {
      ...books.find(b => b.id === path.split('/')[2]),
      papers: path.includes('created-book') ? [] : papers,
    }
  else if (/^\/papers\/[^/]+$/.test(path)) value = papers.find(p => p.id === path.split('/')[2])
  else if (path.endsWith('/conversations')) value = { id: 'conversation-1', items: [] }
  else if (path.endsWith('/reports/report-1')) value = report
  else if (path.endsWith('/reports')) value = { items: [{ id: 'report-1', version_id: 'v1' }] }
  else if (path.endsWith('/annotations')) {
    if (body) annotations.push({ id: 'annotation-1', ...body })
    value = { items: annotations }
  } else if (path.endsWith('/neighbors'))
    value = { papers: [papers[1]], anchors: [], paper_tags: ['retrieval'], has_snapshot: true }
  else if (path === '/workspace-notes') {
    if (body) notes.push({ id: `note-${notes.length}`, ...body })
    value = { items: notes }
  } else if (path.endsWith('/summary')) {
    papers[0].summary = body.content
    value = { ok: true }
  } else if (path.endsWith('/messages')) {
    if (body && failNextChat) {
      failNextChat = false
      return route.fulfill({ status: 503, json: { detail: 'Temporary chat failure' } })
    }
    if (body) {
      messages.push({ id: 'message-1', role: 'user', content: body.content, evidence: {} })
      messages.push({
        id: 'message-2',
        role: 'assistant',
        content: 'Research methods [S1].',
        evidence: {
          sources: [
            {
              id: 'S1',
              paper_id: 'paper-1',
              page: 1,
              version_id: 'v1',
              quote: 'Research methods and reproducible evidence.',
            },
          ],
        },
      })
    }
    value = body ? { id: 'chat-job', state: 'succeeded' } : { items: messages }
  }
  await route.fulfill({ json: value })
})
try {
  await context.route('https://cdn.jsdelivr.net/**', route => route.abort())
  await page.goto(base + '/?book=book-1')
  await expect(page.locator('.pdf-sheet')).toHaveCount(40)
  const first = page.locator('.pdf-sheet[data-page="1"]')
  await expect(first).toHaveAttribute('data-ready', 'true')
  const viewport = page.locator('.pdf-scroll'),
    number = page.getByLabel('PDF 页码')
  const geometry = await page.evaluate(() =>
    Object.fromEntries(
      [
        '.web-shell',
        '#main-library',
        '.notebook-desk',
        '.desk-reading',
        '.pdf-workspace',
        '.pdf-toolbar',
        '.pdf-scroll',
        '.reading-notes',
      ].map(sel => {
        const el = document.querySelector(sel),
          r = el.getBoundingClientRect()
        return [
          sel,
          {
            top: r.top,
            height: r.height,
            bottom: r.bottom,
            scroll: el.scrollHeight,
            client: el.clientHeight,
          },
        ]
      })
    )
  )
  await page.screenshot({ path: `${artifacts}/initial.png` })
  assert.ok(geometry['.pdf-toolbar'].height <= 38, 'compact toolbar height')
  assert.ok(geometry['.notebook-desk'].bottom <= 1000, 'reader fits viewport')
  assert.ok(
    geometry['#main-library'].scroll <= geometry['#main-library'].client + 1,
    'no outer reader scroll'
  )

  await expect(page.locator('#desk-sources .desk-source svg')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '添加资料', exact: true })).toHaveCount(0)
  const toolbar = page.getByRole('group', { name: '阅读工作区视图' })
  for (const name of ['阅读导览', '原文阅读', '搜索论文', '下载当前文档', '收起右侧'])
    await expect(toolbar.getByRole('button', { name, exact: true })).toBeVisible()
  await expect(
    page.getByRole('group', { name: 'PDF 阅读工具' }).getByRole('button', { name: '收起右侧' })
  ).toHaveCount(0)
  await expect(page.getByText('原文件', { exact: true })).toHaveCount(0)
  const ys = await toolbar
    .locator('button,select')
    .evaluateAll(els =>
      els.map(el => el.getBoundingClientRect().y + el.getBoundingClientRect().height / 2)
    )
  assert.ok(Math.max(...ys) - Math.min(...ys) < 4, 'reading toolbar must share one row')
  await viewport.hover()
  await page.mouse.wheel(0, 1600)
  await expect.poll(async () => Number(await number.inputValue())).toBeGreaterThan(1)
  const scrolled = await viewport.evaluate(el => el.scrollTop)
  await page.waitForTimeout(200)
  assert.ok(
    Math.abs((await viewport.evaluate(el => el.scrollTop)) - scrolled) < 80,
    'scroll should not snap back'
  )
  await number.fill('20')
  await expect(page.locator('[data-page="20"]')).toHaveAttribute('data-ready', 'true')
  await expect(page.locator('[data-page="20"] canvas')).toBeInViewport()
  await expect
    .poll(() =>
      page.locator('.pdf-sheet canvas').evaluateAll(els => els.filter(el => el.width > 0).length)
    )
    .toBeLessThan(10)
  await page.locator('[data-page="20"] .textLayer').evaluate(el => {
    const text = [...el.querySelectorAll('span')].find(el =>
      el.textContent.includes('Research methods')
    ).firstChild
    const range = document.createRange()
    range.selectNodeContents(text)
    const selected = window.getSelection()
    selected.removeAllRanges()
    selected.addRange(range)
  })
  await page.locator('[data-page="20"]').dispatchEvent('mouseup')
  await page.getByRole('button', { name: '添加批注', exact: true }).click()
  await page.getByLabel('当前页批注', { exact: true }).fill('Continuous reader annotation')
  await page.getByRole('button', { name: '保存批注', exact: true }).click()
  assert.equal(writes.find(w => w.path.endsWith('/annotations')).body.page, 20)
  await number.fill('1')
  await expect(number).toHaveValue('1')
  await page.getByRole('button', { name: '第 20 页', exact: true }).click()
  await expect(number).toHaveValue('20')
  await expect(page.locator('[data-page="20"] canvas')).toBeInViewport()
  await page.getByRole('button', { name: '收起右侧', exact: true }).click()
  await expect(page.locator('.reading-notes')).toHaveCount(0)
  await page.getByRole('button', { name: '展开右侧', exact: true }).click()
  await expect(page.locator('.reading-notes')).toBeVisible()
  await expect(number).toHaveValue('20')
  await expect(page.locator('[data-page="20"] canvas')).toBeInViewport()
  await page.getByLabel('PDF 缩放').selectOption('1.5')
  await expect(number).toHaveValue('20')
  await expect(page.locator('[data-page="20"] canvas')).toBeInViewport()
  await page.getByLabel('PDF 缩放').selectOption('1')
  await expect(number).toHaveValue('20')
  for (const tab of ['对话', '笔记', '报告', '近邻']) {
    await page.getByRole('tab', { name: tab, exact: true }).click()
    await expect(page.locator('.research-panel .research-panel-heading')).toHaveCSS(
      'padding',
      '0px'
    )
    await page.screenshot({ path: `${artifacts}/${tab}.png` })
  }
  await page.getByRole('button', { name: '文内查找', exact: true }).click()
  const find = page.getByRole('search', { name: '文内查找' })
  await page.getByLabel('查找文档内容').fill('Document page 20')
  await expect(find.getByRole('status')).toHaveText('1 / 1')
  await expect(number).toHaveValue('20')
  await expect(page.locator('[data-page="20"] .citation-highlights mark')).toHaveCount(1)
  await page.getByLabel('查找文档内容').fill('Research methods')
  await expect(find.getByRole('status')).toHaveText('1 / 40')
  await page.getByRole('button', { name: '下一个匹配' }).click()
  await expect(number).toHaveValue('2')
  await page.getByRole('button', { name: '上一个匹配' }).click()
  await expect(number).toHaveValue('1')
  await page.getByLabel('查找文档内容').fill('no such phrase')
  await expect(find.getByRole('status')).toHaveText('0 / 0')
  await page.getByRole('button', { name: '关闭查找' }).click()
  await page.getByRole('button', { name: '文档目录', exact: true }).click()
  await page
    .getByRole('navigation', { name: '文档目录' })
    .getByRole('button', { name: 'Methods' })
    .click()
  await expect(number).toHaveValue('20')
  await page.getByLabel('PDF 缩放').selectOption('page')
  await expect
    .poll(() =>
      page.locator('[data-page="20"] canvas').evaluate(el => el.getBoundingClientRect().height)
    )
    .toBeLessThan(await viewport.evaluate(el => el.clientHeight))
  await page.getByLabel('PDF 缩放').selectOption('1')
  await page.getByRole('button', { name: '高亮文本', exact: true }).click()
  await expect(page.getByRole('button', { name: '高亮文本', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true'
  )
  await page.locator('[data-page="20"] .textLayer').evaluate(el => {
    const text = [...el.querySelectorAll('span')].find(el =>
      el.textContent.includes('Document page')
    ).firstChild
    const range = document.createRange()
    range.selectNodeContents(text)
    const selected = window.getSelection()
    selected.removeAllRanges()
    selected.addRange(range)
  })
  await page.locator('[data-page="20"]').dispatchEvent('mouseup')
  await expect.poll(() => annotations.length).toBe(2)
  await page.getByRole('button', { name: '高亮文本', exact: true }).click()
  await page.getByRole('tab', { name: '笔记', exact: true }).click()
  await page.getByRole('button', { name: '汇总批注到阅读笔记' }).click()
  await expect(page.getByLabel('阅读笔记', { exact: true })).toBeVisible()
  assert.match(await page.getByLabel('阅读笔记', { exact: true }).inputValue(), /第 20 页/)
  await page.getByRole('button', { name: '保存笔记', exact: true }).click()
  await page.getByRole('tab', { name: '对话', exact: true }).click()
  await expect(page.locator('[data-assistant-ui="thread"]')).toBeVisible()
  await page.getByLabel('向所选资料提问').fill('Explain the method')
  await page.getByLabel('向所选资料提问').press('Enter')
  await expect(page.getByRole('alert').filter({ hasText: 'Temporary chat failure' })).toBeVisible()
  await expect(page.getByLabel('向所选资料提问')).toHaveValue('Explain the method')
  await page.getByLabel('向所选资料提问').press('Enter')
  await expect(page.locator('.desk-message.assistant')).toContainText('Research methods')
  assert.equal(writes.find(w => w.path.endsWith('/messages')).body.content, 'Explain the method')
  await expect(page.getByLabel('向所选资料提问')).toHaveValue('')
  await page.screenshot({ path: `${artifacts}/assistant-thread.png` })
  await page.getByLabel('向所选资料提问').fill('A recoverable draft')
  await page.getByRole('tab', { name: '笔记', exact: true }).click()
  await page.getByRole('tab', { name: '对话', exact: true }).click()
  await expect(page.getByLabel('向所选资料提问')).toHaveValue('A recoverable draft')
  await page.getByLabel('向所选资料提问').fill('')

  await page.getByRole('button', { name: '添加', exact: true }).click()
  const add = page.getByRole('dialog', { name: '添加资料', exact: true })
  await expect(add.getByRole('button', { name: '选择 PDF 文件' })).toBeVisible()
  await expect(add.getByLabel('上传资料 PDF')).toBeHidden()
  await page.screenshot({ path: `${artifacts}/upload.png` })
  await page.keyboard.press('Escape')
  await page.getByLabel('文档版本', { exact: true }).selectOption('v2')
  await expect(number).toHaveValue('1')
  await expect(first).toHaveAttribute('data-ready', 'true')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载当前文档' }).click()
  const downloaded = await download
  assert.match(downloaded.suggestedFilename(), /\.pdf$/)
  assert.match(downloaded.url(), /version=v2/)
  for (const width of [1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await number.fill('3')
    await expect(page.locator('[data-page="3"]')).toHaveAttribute('data-ready', 'true')
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    assert.ok(
      await page.locator('#main-library').evaluate(el => el.scrollHeight <= el.clientHeight + 1),
      `outer reader overflow at ${width}`
    )
    await page.screenshot({ path: `${artifacts}/reader-${width}.png` })
  }
  for (const [width, height] of [
    [1440, 800],
    [1024, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height })
    await expect(page.getByLabel('向所选资料提问')).toBeVisible()
    assert.ok(
      await page.locator('#main-library').evaluate(el => el.scrollHeight <= el.clientHeight + 1),
      `reader overflow at ${width} x ${height}`
    )
    const composer = await page.locator('.desk-composer').boundingBox()
    assert.ok(composer.y + composer.height <= height + 1, 'composer must stay inside screen')
  }
  assert.deepEqual(errors, [])
  console.log(
    'PASS continuous PDF, compact toolbar, document find/outline, fit page, highlights, notes, assistant-ui send/retry/drafts, viewport sizing and downloads'
  )
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
