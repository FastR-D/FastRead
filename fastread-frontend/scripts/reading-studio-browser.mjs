import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'

const artifacts = 'test-results/reading-studio'
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
let generated = false,
  reportFailed = false
const report = {
  id: 'report-1',
  version_id: 'v1',
  content: {
    reading_mode: 'deep',
    repository: {
      url: 'https://github.com/example/research',
      commit: 'a'.repeat(40),
      paths: ['src/model.py'],
      files: [
        {
          path: 'src/model.py',
          content: 'def encode(x):\n    return x / 2',
          line_start: 1,
          line_end: 2,
          truncated: false,
        },
      ],
    },
    implementation: [
      {
        title: 'Scale implementation',
        description: 'The implementation scales the input.',
        evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
        code_evidence: [
          { path: 'src/model.py', line_start: 1, line_end: 2, quote: 'return x / 2' },
        ],
      },
    ],
    executive_summary:
      'Understand a method through its source, arithmetic and controlled experiments.',
    formulas: [
      {
        title: 'Scaled score',
        latex: 's=x/c',
        explanation: 'Divide the input by a scale.',
        variables: [
          { name: 'x', label: 'Input', min: 0, max: 20, value: 4 },
          { name: 'c', label: 'Scale', min: 1, max: 10, value: 2 },
        ],
        expression: { op: 'div', args: ['x', 'c'] },
        evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
      },
    ],
    experiments: [
      {
        title: 'Controlled results',
        conditions: 'The same dataset and evaluation setup.',
        metric: 'Accuracy',
        unit: '%',
        rows: [
          {
            label: 'Baseline',
            value: '90.0',
            evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
          },
          {
            label: 'Method',
            value: '95.5',
            evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
          },
        ],
      },
    ],
    limitations: ['Only one controlled dataset was evaluated.'],
    terms: [{ term: 'Grounding', explanation: 'Return to the original source.' }],
    suggested_questions: ['What would change on a new dataset?'],
    key_questions: [
      {
        question: 'What is studied?',
        answer: 'A reading workflow.',
        evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
      },
    ],
    process: [
      {
        step: 'Encode inputs',
        description: 'Prepare the source representation.',
        input: 'Source tokens',
        output: 'Encoded tokens',
        purpose: 'Preserve evidence.',
        evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
      },
      {
        step: 'Compare evidence',
        description: 'Compare the encoded sources.',
        input: 'Encoded tokens',
        output: 'Located evidence',
        evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
      },
    ],
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
  else if (path === '/jobs')
    value = {
      items: generated
        ? [
            {
              id: 'reading-job',
              kind: 'report',
              resource_id: 'paper-1',
              state: reportFailed ? 'failed' : 'succeeded',
              error: reportFailed ? 'Fixture provider unavailable' : '',
            },
          ]
        : [],
    }
  else if (path.endsWith('/reports/report-0'))
    value = {
      ...report,
      id: 'report-0',
      content: { ...report.content, executive_summary: 'Previous reading preserved.' },
    }
  else if (path.endsWith('/reports/report-1')) value = report
  else if (path.endsWith('/reports')) {
    if (body) {
      generated = true
      value = { id: 'reading-job', kind: 'report', resource_id: 'paper-1', state: 'queued' }
    } else
      value = {
        items: [
          { id: 'report-1', version_id: 'v1', created: 1794484800 },
          { id: 'report-0', version_id: 'v1', created: 1794484700 },
        ],
      }
  } else if (path.endsWith('/annotations')) {
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
  await page.getByLabel('筛选本页论文').fill('Paper 2')
  await expect(page.locator('.knowledge-paper')).toHaveCount(1)
  await page.getByLabel('筛选本页论文').fill('')
  await page.getByRole('button', { name: '列表', exact: true }).click()
  await expect(page.locator('.paper-list-layout')).toBeVisible()
  await page.getByRole('button', { name: '卡片', exact: true }).click()
  await page
    .getByRole('navigation', { name: '知识库目录' })
    .getByRole('button', { name: 'Research library' })
    .click()
  await expect(page.locator('.pdf-sheet canvas')).toBeVisible()
  await page.getByRole('button', { name: '阅读导览', exact: true }).click()
  const studio = page.getByRole('region', { name: '交互阅读内容' })
  await expect(
    studio.getByText(
      'Understand a method through its source, arithmetic and controlled experiments.',
      { exact: true }
    )
  ).toBeVisible()
  await page.getByLabel('阅读记录').selectOption('report-0')
  await expect(studio.getByText('Previous reading preserved.')).toBeVisible()
  await page.getByLabel('阅读记录').selectOption('report-1')
  await page.getByRole('button', { name: '方法拆解' }).click()
  await expect(studio.getByText('Source tokens', { exact: true })).toBeVisible()
  await studio.getByRole('button', { name: '下一步', exact: true }).click()
  await expect(studio.getByText('Located evidence', { exact: true })).toBeVisible()
  await studio.getByRole('button', { name: '继续追问', exact: true }).click()
  await expect(page.getByLabel('向所选资料提问')).toContainText('Compare evidence')
  await expect(page.getByRole('tab', { name: '对话', exact: true })).toHaveAttribute(
    'aria-selected',
    'true'
  )
  await page.getByRole('button', { name: '阅读导览', exact: true }).click()
  await page.getByRole('button', { name: '仓库联读' }).click()
  await expect(studio.getByRole('link', { name: 'src/model.py · L1–L2' })).toHaveAttribute(
    'href',
    `https://github.com/example/research/blob/${'a'.repeat(40)}/src/model.py#L1-L2`
  )
  await expect(studio.getByText('return x / 2', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '公式探索' }).click()
  await expect(studio.locator('output')).toContainText('2')
  await page.getByLabel('变量 x', { exact: true }).fill('8')
  await expect(studio.locator('output')).toHaveText('计算结果：4')
  await studio.getByRole('button', { name: '保存试算到主笔记' }).click()
  await expect(studio.getByText('已追加到主笔记', { exact: true })).toBeVisible()
  assert.ok(
    writes.some(
      w =>
        w.path.endsWith('/summary') &&
        w.body.content.includes('输出：4') &&
        w.body.content.includes('教学计算')
    )
  )
  await page.getByRole('button', { name: '实验对照' }).click()
  await expect(studio.getByRole('cell', { name: '+5.5', exact: true })).toBeVisible()
  await page.getByLabel('实验比较基准').selectOption('1')
  await expect(studio.getByRole('cell', { name: '-5.5', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '理解与追问' }).click()
  await studio.getByRole('button', { name: '开始引导自测' }).click()
  await expect(studio.getByText('A reading workflow.', { exact: true })).toHaveCount(0)
  await page.getByLabel('我的理解 1').fill('My understanding of evidence.')
  await studio.getByRole('button', { name: '查看解释', exact: true }).click()
  await expect(studio.getByText('A reading workflow.', { exact: true })).toBeVisible()
  await studio.getByRole('button', { name: '保存理解到主笔记' }).click()
  await expect.poll(() => writes.filter(w => w.path.endsWith('/summary')).length).toBe(2)
  assert.ok(
    writes
      .filter(w => w.path.endsWith('/summary'))
      .at(-1)
      .body.content.includes('输出：4'),
    'appending must retain earlier notes'
  )
  await page.getByRole('button', { name: '论文速览' }).click()
  await studio.getByRole('button', { name: '第 1 页 · 原文依据', exact: true }).first().click()
  await expect(page.locator('.citation-highlights mark').first()).toBeVisible()
  await page.getByRole('button', { name: '阅读导览', exact: true }).click()
  await studio.locator('.reading-generation > summary').click()
  await studio.getByRole('button', { name: '快速泛读', exact: true }).click()
  reportFailed = true
  await studio.getByRole('button', { name: '生成新的阅读', exact: true }).click()
  await expect(studio.getByRole('alert')).toContainText('Fixture provider unavailable')
  assert.ok(writes.some(w => w.path.endsWith('/reports') && w.body.reading_mode === 'skim'))
  await expect(studio.getByRole('button', { name: '生成新的阅读', exact: true })).toBeEnabled()
  await studio.getByRole('button', { name: '关联仓库精读', exact: true }).click()
  await page.getByLabel('联读提交 SHA').fill('main')
  await expect(studio.getByRole('button', { name: '生成新的阅读', exact: true })).toBeDisabled()
  await page.getByLabel('联读提交 SHA').fill('a'.repeat(40))
  await page.getByLabel('联读仓库地址').fill('https://github.com/example/research')
  await page.getByLabel('联读文件路径').fill('src/model.py')
  reportFailed = false
  await studio.getByRole('button', { name: '生成新的阅读', exact: true }).click()
  await expect
    .poll(() =>
      writes.some(
        w =>
          w.path.endsWith('/reports') &&
          w.body.reading_mode === 'repository' &&
          w.body.repository.commit === 'a'.repeat(40)
      )
    )
    .toBe(true)
  scenarios.push(
    'history, method steps, contextual questions, arithmetic, experiment baseline, guided recall, main-note append, citation jump and failed generation retry'
  )
  for (const width of [1440, 1024, 390])
    for (const mode of ['light', 'dark']) {
      await page.setViewportSize({ width, height: 1000 })
      await page.evaluate(mode => localStorage.setItem('fastread.theme', mode), mode)
      await page.reload()
      await page.getByRole('button', { name: '阅读导览', exact: true }).click()
      await page.getByRole('button', { name: '公式探索' }).click()
      await expect(studio.locator('output')).toBeVisible()
      await expect(page.locator('.reading-outline [aria-current=step]')).toHaveCount(1)
      await studio.locator('output').scrollIntoViewIfNeeded()
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `reading studio overflows at ${width}`
      )
      await page.screenshot({ path: `${artifacts}/studio-${mode}-${width}.png`, fullPage: true })
    }
  assert.deepEqual(errors, [])
  await writeFile(
    `${artifacts}/results.json`,
    JSON.stringify(
      { status: 'passed', scenarios, viewports: [1440, 1024, 390], modes: ['light', 'dark'] },
      null,
      2
    )
  )
  console.log('PASS reading studio browser scenarios')
} catch (error) {
  await page.screenshot({ path: `${artifacts}/failure.png`, fullPage: true })
  throw error
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
