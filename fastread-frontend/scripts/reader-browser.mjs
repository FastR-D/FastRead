import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'

const artifacts = 'test-results/reader'
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
  page_count: 1,
  summary: '',
  year: 2026,
  tags: ['retrieval'],
  principle: 'Evidence grounded retrieval.',
  metadata: { authors: ['Reader'], page_count: 1, year: 2026 },
  versions: [{ id: 'v1', page_count: 1, created: 1794484800 }],
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
  const stream =
    'BT /F1 18 Tf 50 740 Td (FastRead Browser Validation) Tj 0 -32 Td /F1 12 Tf (Research methods and reproducible evidence.) Tj 0 -22 Td (This paper studies an efficient reading workflow.) Tj ET'
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ]
  let data = '%PDF-1.4\n',
    offsets = [0]
  objects.forEach((object, i) => {
    offsets.push(Buffer.byteLength(data))
    data += `${i + 1} 0 obj\n${object}\nendobj\n`
  })
  const xref = Buffer.byteLength(data)
  data += `xref\n0 6\n0000000000 65535 f \n${offsets
    .slice(1)
    .map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`)
    .join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
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
  await page.goto(base)
  await expect(page.getByRole('button', { name: 'Research library' })).toBeVisible()
  await page.getByRole('button', { name: '后台任务', exact: true }).click()
  await expect(page.getByText('暂无任务', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '搜索论文', exact: true }).click()
  await expect(page.locator('#library-search input')).toBeFocused()
  await page.getByRole('button', { name: '导入论文', exact: true }).click()
  await expect(page.getByLabel('上传 PDF', { exact: true })).toBeVisible()
  await page
    .locator('details')
    .filter({ has: page.getByLabel('上传 PDF', { exact: true }) })
    .locator('summary')
    .click()

  const alignment = await page
    .getByRole('group', { name: '论文批量操作', exact: true })
    .evaluate(el => {
      const elements = [el.firstElementChild, ...el.querySelectorAll('button,select')]
      return elements.map(el => {
        const box = el.getBoundingClientRect()
        return box.y + box.height / 2
      })
    })
  assert.ok(
    Math.max(...alignment) - Math.min(...alignment) <= 1,
    'batch toolbar controls are misaligned'
  )
  await page.getByRole('button', { name: '关系矩阵', exact: true }).click()
  await expect(page.getByRole('region', { name: '论文关系矩阵' })).toBeVisible()
  await page.getByRole('button', { name: '卡片视图' }).click()
  await page.screenshot({ path: `${artifacts}/library-desktop.png` })
  await page.getByRole('button', { name: 'Research library' }).click()
  await expect(page.locator('.pdf-sheet canvas')).toBeVisible()
  await expect(page.locator('.textLayer')).toContainText('FastRead Browser Validation')
  assert.equal(
    await page
      .locator('.textLayer span')
      .first()
      .evaluate(el => getComputedStyle(el).color),
    'rgba(0, 0, 0, 0)'
  )
  await expect(page.getByRole('checkbox', { name: '问答参考 Research Paper 1' })).toBeChecked()
  await page.getByRole('checkbox', { name: '问答参考 Research Paper 2' }).uncheck()
  await page.getByRole('button', { name: '查看关系矩阵' }).click()
  const matrix = page.getByRole('dialog', { name: '关系矩阵', exact: true })
  await expect(matrix).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(matrix).not.toBeVisible()
  await expect(page.getByRole('button', { name: '查看关系矩阵' })).toBeFocused()
  await page.getByRole('button', { name: '添加', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '添加资料' })).toBeVisible()
  await page.keyboard.press('Escape')
  scenarios.push('FastUI library assets, relation matrix, source selection and native desk dialogs')

  const tabs = page.getByRole('tab', { name: '笔记', exact: true })
  await page.getByRole('tab', { name: '对话', exact: true }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(tabs).toBeFocused()
  await expect(tabs).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: '报告', exact: true }).click()
  await expect(page.getByText('What is studied?', { exact: true })).toBeVisible()
  await tabs.click()
  const readsBeforeTyping = reads.length
  await page.getByLabel('阅读笔记', { exact: true }).fill('A saved reading summary')
  await page.getByLabel('当前页批注', { exact: true }).fill('A page annotation')
  await page.evaluate(
    () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  )
  assert.equal(
    reads.length,
    readsBeforeTyping,
    'typing notes must not reload the PDF, sources or report'
  )

  await page.getByRole('button', { name: '保存批注', exact: true }).click()
  await expect(page.getByText('A page annotation', { exact: true })).toBeVisible()
  await page.getByLabel('阅读笔记', { exact: true }).fill('A saved reading summary')
  await page.getByRole('button', { name: '保存笔记', exact: true }).click()
  await page.getByRole('button', { name: '新建', exact: true }).click()
  await page.getByLabel('笔记标题').fill('Research note')
  await page.getByLabel('笔记正文').fill('Saved notebook content')
  await page.getByRole('button', { name: '保存这条笔记' }).click()
  await page.getByText('Research note', { exact: true }).click()
  await expect(page.getByText('Saved notebook content', { exact: true })).toBeVisible()
  scenarios.push('keyboard tabs, page annotation, reading summary and notebook note persistence')

  await page.locator('.textLayer').evaluate(el => {
    const node = [...el.querySelectorAll('span')].find(el =>
      el.textContent.includes('Research methods')
    ).firstChild
    const range = document.createRange()
    range.selectNodeContents(node)
    const selection = window.getSelection()
    selection.removeAllRanges()
    selection.addRange(range)
  })
  await page.locator('.pdf-sheet').dispatchEvent('mouseup')
  await page.getByRole('button', { name: '问这段', exact: true }).click()
  await expect(page.getByRole('tab', { name: '对话', exact: true })).toHaveAttribute(
    'aria-selected',
    'true'
  )
  await page.getByLabel('向所选资料提问').fill('Explain the evidence')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '保存为笔记' })).toBeVisible()
  await page.getByRole('button', { name: '[S1] 原文 · 第 1 页', exact: true }).click()
  await expect(page.locator('.citation-highlights mark').first()).toBeVisible()
  await page.getByRole('tab', { name: '报告', exact: true }).click()
  await expect(page.getByText('What is studied?', { exact: true })).toBeVisible()
  await page.getByRole('tab', { name: '近邻', exact: true }).click()
  await page.getByLabel('近邻关键词').fill('not a matching title')
  await expect(page.getByText('当前条件下没有近邻论文', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '清除筛选', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Research Paper 2' })).toBeVisible()
  scenarios.push(
    'PDF text selection, quoted questions, citation highlight, reports and neighbor filtering'
  )

  for (const width of [1440, 1024, 390])
    for (const mode of ['light', 'dark']) {
      await page.setViewportSize({ width, height: 1000 })
      await page.evaluate(mode => localStorage.setItem('fastread.theme', mode), mode)
      await page.reload()
      await expect(page.locator('.pdf-sheet canvas')).toBeVisible()
      await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', mode)
      await page.getByRole('tab', { name: '笔记', exact: true }).click()
      await expect(page.getByLabel('阅读笔记', { exact: true })).toHaveValue(
        'A saved reading summary'
      )
      await page.getByLabel('阅读笔记', { exact: true }).scrollIntoViewIfNeeded()
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `reader overflows at ${width}`
      )
      assert.ok(
        await page.locator('.pdf-scroll').evaluate(el => el.clientHeight > 100),
        'PDF has no scroll viewport'
      )
      if (width === 1440)
        assert.ok(
          await page.locator('.pdf-scroll').evaluate(el => el.scrollHeight > el.clientHeight),
          'PDF page bottom is unreachable'
        )
      const unstyled = await page
        .locator('button,input,select,textarea')
        .evaluateAll(elements =>
          elements
            .filter(el => !/fastui-(button|input|select|textarea|tab)/.test(el.className))
            .map(el => el.outerHTML)
        )
      assert.deepEqual(unstyled, [], 'application controls must use FastUI')
      await page.screenshot({ path: `${artifacts}/reader-${mode}-${width}.png`, fullPage: true })
    }
  scenarios.push(
    'desktop, tablet and mobile reader in both themes with reachable notes and PDF scrolling'
  )
  assert.ok(
    writes.some(
      ({ path, body }) =>
        path.endsWith('/messages') &&
        body.paper_ids.length === 1 &&
        body.content.includes('Research methods')
    )
  )
  assert.deepEqual(errors, [])
  await writeFile(
    `${artifacts}/results.json`,
    JSON.stringify(
      { status: 'passed', scenarios, viewports: [1440, 1024, 390], modes: ['light', 'dark'] },
      null,
      2
    )
  )
  console.log(`PASS ${scenarios.length} FastUI reader browser scenarios`)
} catch (error) {
  await page.screenshot({ path: `${artifacts}/failure.png`, fullPage: true })
  throw error
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
