import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'

const artifacts = 'test-results/design-review'
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
      is_admin: true,
      role: 'owner',
      csrf: 'fixture',
      workspace_id: 'workspace',
      workspace: { name: 'Workspace', daily_limit: 24 },
    }
  else if (path === '/admin/status')
    value = { users: 12, papers: 368, queued: 2, running: 1, version: '4.1.0' }
  else if (path === '/admin/users')
    value = {
      items: [
        {
          id: 'reader',
          email: 'reader@example.test',
          display_name: '研究员',
          role: 'admin',
          workspace_name: '研究工作区',
          disabled: false,
        },
      ],
    }
  else if (path === '/admin/workspaces')
    value = { items: [{ id: 'workspace', name: '研究工作区' }] }
  else if (path === '/admin/providers')
    value = {
      items: [
        {
          id: 'shared',
          name: '研究模型',
          models: ['model-a'],
          base_url: 'https://model.example.test/v1',
          enabled: true,
          workspace_ids: ['workspace'],
          user_ids: [],
        },
      ],
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

// Visual QA fixtures only. No example papers are added to the user's library.
const examples = [
  [
    'Attention Is All You Need',
    'Ashish Vaswani · Noam Shazeer',
    2017,
    '注意力机制',
    '从注意力机制出发，理解 Transformer 的方法与结构。',
  ],
  [
    'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks',
    'Patrick Lewis · Ethan Perez',
    2020,
    '检索增强',
    '结合参数化记忆与外部检索，探索知识密集型任务。',
  ],
  [
    'LoRA: Low-Rank Adaptation of Large Language Models',
    'Edward J. Hu · Yelong Shen',
    2021,
    '高效微调',
    '关注低秩更新的参数效率，以及不同任务上的适用范围。',
  ],
  [
    'Scaling Laws for Neural Language Models',
    'Jared Kaplan · Sam McCandlish',
    2020,
    '模型规模',
    '理解模型规模、数据规模与训练计算量之间的关系。',
  ],
  [
    'Direct Preference Optimization: Your Language Model is Secretly a Reward Model',
    'Rafael Rafailov · Archit Sharma',
    2023,
    '偏好对齐',
    '对照偏好优化目标、训练过程与实验设计。',
  ],
  [
    'Lost in the Middle: How Language Models Use Long Contexts',
    'Nelson F. Liu · Kevin Lin',
    2023,
    '长上下文',
    '记录长上下文阅读中信息位置对任务表现的影响。',
  ],
]
papers.splice(
  0,
  papers.length,
  ...examples.map(([title, authors, year, tag, principle], i) => ({
    id: `paper-${i + 1}`,
    title,
    active_version: 'v1',
    page_count: 12,
    summary: '',
    year,
    tags: [tag],
    principle,
    metadata: { authors: authors.split(' · '), page_count: 12, year },
    versions: [{ id: 'v1', page_count: 12, created: 1794484800 }],
    knowledge_bases: [],
  }))
)
books.splice(
  0,
  books.length,
  { id: 'book-1', name: '大语言模型与推理', paper_count: 6, description: '从基础架构到推理能力' },
  { id: 'book-2', name: '检索增强与知识系统', paper_count: 3, description: '让回答回到可靠的依据' },
  { id: 'book-3', name: '高效训练与模型对齐', paper_count: 4, description: '方法、实验与研究笔记' }
)
report.content.executive_summary =
  '这篇论文提出以注意力机制为核心的 Transformer 架构。在阅读时，先建立编码器与解码器的整体结构，再理解多头注意力如何组织信息，最后回到实验条件中核对效果。'
report.content.key_questions = [
  {
    question: '为什么从循环结构转向注意力机制？',
    answer:
      '从序列建模的需求出发，关注信息在不同位置之间如何传递。阅读时对照原文，区分结构设计的动机、并行计算的收益与论文实际报告的结果。',
    why_it_matters: '建立方法选择与研究问题之间的联系。',
    evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
  },
  {
    question: '多头注意力在方法中承担什么角色？',
    answer:
      '分别跟踪 Query、Key 与 Value 的来源，并把每一步运算对应到模块的输入和输出。这有助于理解不同注意力头如何学习不同的表示。',
    evidence: [{ page: 1, exact_quote: 'Research methods and reproducible evidence.' }],
  },
]
report.content.contributions = []
report.content.limitations = ['本页为界面验收示例，阅读内容与页码使用测试数据。']
try {
  await page.goto(base)
  await expect(page.locator('.knowledge-paper')).toHaveCount(6)
  await expect
    .poll(
      () =>
        page.evaluate(
          () =>
            [...document.querySelectorAll('link[data-app-font]')].filter(link => link.sheet).length
        ),
      { timeout: 30000 }
    )
    .toBe(4)
  const fontStatus = await page.evaluate(async () => {
    await document.fonts.ready
    return Promise.all(
      [400, 500, 600, 700].map(async weight => {
        const faces = await document.fonts.load(
          `${weight} 14px "HarmonyOS Sans SC"`,
          'FastRead 论文库管理设置'
        )
        return { weight, loaded: faces.length > 0 && faces.every(face => face.status === 'loaded') }
      })
    )
  })
  await writeFile(`${artifacts}/fonts.json`, JSON.stringify(fontStatus, null, 2))
  console.log('HarmonyOS CDN:', fontStatus)
  for (const mode of ['light', 'dark']) {
    if (mode === 'dark') await page.getByRole('button', { name: '切换暗黑模式' }).click()
    for (const width of [360, 390, 768, 1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 })
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `${mode} ${width}: page overflow`
      )
      const navigation = page.getByRole('group', { name: '主导航 controls', exact: true })
      for (const name of ['论文库', '管理']) {
        await expect(navigation.getByRole('tab', { name, exact: true })).toBeInViewport()
      }
      const geometry = await page.locator('.app-topbar-inner').evaluate(el => {
        const [brand, nav, account] = [...el.children].map(child => child.getBoundingClientRect())
        return {
          fits: brand.right <= account.left,
          separated:
            nav.top >= brand.bottom || (brand.right <= nav.left && nav.right <= account.left),
        }
      })
      assert.ok(geometry.fits && geometry.separated, `${mode} ${width}: header overlaps`)
      const active = navigation.getByRole('tab', { selected: true })
      await expect(active).toHaveCSS('border-top-width', '0px')
      await expect(active).toHaveCSS('border-right-width', '0px')
      await expect(active).toHaveCSS('border-radius', '4px')
      await expect(active).toHaveCSS('box-shadow', 'none')
      await active.hover()
      await expect(active).toHaveCSS('background-color', 'rgb(8, 97, 77)')
      await expect(active.locator('..')).toHaveCSS('border-top-width', '0px')
      await active.focus()
      await page.keyboard.press('End')
      await expect(navigation.getByRole('tab', { name: '管理', exact: true })).toBeFocused()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('tabpanel', { name: '管理', exact: true })).toBeVisible()
      await navigation.getByRole('tab', { name: '论文库', exact: true }).click()
      await page.screenshot({
        animations: 'disabled',
        path: `${artifacts}/navbar-${width}-${mode}.png`,
      })
    }
  }
  await page.getByRole('button', { name: '切换浅色模式' }).click()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/library-light.png` })
  const sidebar = page.locator('#library-sidebar')
  await expect(sidebar.getByRole('button', { name: '导入论文', exact: true })).toHaveCount(0)
  await expect(sidebar.getByRole('button', { name: '搜索论文', exact: true })).toHaveCount(0)
  await page
    .getByRole('group', { name: '论文库操作' })
    .getByRole('button', { name: '搜索论文' })
    .click()
  await expect(page.getByRole('region', { name: '搜索论文', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '搜索论文' })).toHaveCount(0)
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/search-light.png` })
  await sidebar.getByRole('button', { name: '后台任务' }).click()
  await expect(page.getByRole('heading', { name: '后台任务' })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '后台任务' })).toHaveCount(0)
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/jobs-light.png` })
  await page.getByRole('button', { name: 'FastRead 论文库' }).click()
  await page.getByRole('button', { name: '账号菜单' }).hover()
  await expect(page.getByRole('menu', { name: '账号菜单' })).toBeVisible()
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/account-menu.png` })
  await page.getByRole('button', { name: '账号菜单' }).focus()
  await page.keyboard.press('Escape')

  await page.getByRole('tab', { name: '管理', exact: true }).click()
  const adminNavigation = page.getByRole('tablist', { name: '管理分类' })
  for (const width of [1440, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 1000 })
    if (width <= 900 && (await page.getByRole('button', { name: '展开导航' }).count()))
      await page.getByRole('button', { name: '展开导航' }).click()
    await expect(adminNavigation).toHaveAttribute(
      'aria-orientation',
      width <= 900 ? 'horizontal' : 'vertical'
    )
    for (const [name, key] of [
      ['运行概览', 'overview'],
      ['用户管理', 'users'],
      ['共享模型', 'models'],
    ]) {
      await adminNavigation.getByRole('tab', { name, exact: true }).click()
      const panel = page.getByRole('tabpanel', { name, exact: true })
      await expect(panel).toBeVisible()
      await expect(panel.getByRole('heading', { name, exact: true })).toBeVisible()
      await expect(panel.getByText('正在加载', { exact: false })).toHaveCount(0)
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        `admin ${key} ${width}: page overflow`
      )
      await page.screenshot({
        animations: 'disabled',
        path: `${artifacts}/admin-${key}-${width}.png`,
      })
    }
    await adminNavigation.getByRole('tab', { name: '运行概览' }).focus()
    await page.keyboard.press(width <= 900 ? 'ArrowRight' : 'ArrowDown')
    await expect(adminNavigation.getByRole('tab', { name: '用户管理' })).toBeFocused()
  }
  await page.setViewportSize({ width: 1440, height: 1000 })

  await page.getByRole('button', { name: '账号菜单', exact: true }).click()
  await page.getByRole('menuitem', { name: '设置', exact: true }).click()
  await expect(page.getByRole('region', { name: '设置', exact: true })).toBeVisible()
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/settings-light.png` })
  await expect(page.getByRole('tab', { name: '设置', exact: true })).toHaveCount(0)
  const sidebarStyle = () => page.locator('.workbench-sidebar').evaluate(el => {
    const button = el.querySelector('.sidebar-navigation .fastui-button')
    const css = getComputedStyle(button)
    return { width: el.getBoundingClientRect().width, height: button.getBoundingClientRect().height, radius: css.borderRadius, padding: css.padding, fontWeight: css.fontWeight, background: css.backgroundColor }
  })
  const settingsSidebar = await sidebarStyle()
  await page.getByRole('tab', { name: '应用联动', exact: true }).click()
  for (const selector of ['.settings-page', '.integration-status', '.integration-connection']) {
    for (const box of await page.locator(selector).all()) {
      if (await box.isVisible()) { await expect(box).toHaveCSS('border-top-width', '0px'); await expect(box).toHaveCSS('box-shadow', 'none') }
    }
  }
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/connections-light.png` })
  await page.getByRole('tab', { name: '管理', exact: true }).click()
  assert.deepEqual(await sidebarStyle(), settingsSidebar, 'management and settings must use identical sidebar geometry and selection')
  await page.getByRole('tab', { name: '论文库', exact: true }).click()
  assert.deepEqual(await sidebarStyle(), settingsSidebar, 'library and settings must use identical sidebar geometry and selection')
  scenarios.push('equal sidebar width, spacing and selection; settings menu entry and border-free integrations')

  await page.getByRole('tab', { name: '论文库', exact: true }).click()

  await page.getByRole('button', { name: '导入论文', exact: true }).last().click()
  await expect(page.getByRole('dialog', { name: '导入论文', exact: true })).toBeVisible()
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/import-light.png` })
  await page.keyboard.press('Escape')
  await page
    .getByRole('navigation', { name: '知识库目录' })
    .getByRole('button', { name: '大语言模型与推理' })
    .click()
  await expect(page.locator('.pdf-sheet canvas')).toBeVisible()
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/reader-light.png` })
  await page.getByRole('button', { name: '阅读导览', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: '为什么从循环结构转向注意力机制？' })
  ).toBeVisible()
  const guideButton = page.getByRole('button', { name: '阅读导览', exact: true })
  await guideButton.hover()
  await expect(guideButton).toHaveCSS('background-color', 'rgb(8, 97, 77)')
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/guide-light.png` })
  await page.getByRole('button', { name: '收起资料列表' }).click()
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/focus-light.png` })
  await page.getByRole('button', { name: '展开资料列表' }).click()
  for (const mode of ['light', 'dark']) {
    if (mode === 'dark') await page.getByRole('button', { name: '切换暗黑模式' }).click()
    await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', mode)
    await page.setViewportSize({ width: 390, height: 844 })
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      'mobile overflow'
    )
    assert.ok(
      await page
        .getByRole('navigation', { name: '阅读章节' })
        .evaluate(el => el.getBoundingClientRect().height < 80),
      'mobile reading navigation must stay in one row'
    )
    await page.screenshot({ animations: 'disabled', path: `${artifacts}/guide-mobile-${mode}.png` })
    await page.getByRole('button', { name: 'FastRead 论文库', exact: true }).click()
    await expect(page.locator('.knowledge-paper')).toHaveCount(6)
    await page.screenshot({
      animations: 'disabled',
      path: `${artifacts}/library-mobile-${mode}.png`,
    })
    await page.setViewportSize({ width: 1440, height: 1000 })
    if (mode === 'dark')
      await page.screenshot({ animations: 'disabled', path: `${artifacts}/library-dark.png` })
    await page
      .getByRole('navigation', { name: '知识库目录' })
      .getByRole('button', { name: '大语言模型与推理' })
      .click()
    await page.getByRole('button', { name: '阅读导览', exact: true }).click()
  }
  // A blocked font CDN must still leave a usable interface with system fallbacks.
  await context.route('https://cdn.jsdelivr.net/**', route => route.abort())
  await page.setViewportSize({ width: 360, height: 844 })
  await page.goto(base)
  await expect(page.locator('.knowledge-paper')).toHaveCount(6)
  await page.getByRole('button', { name: '账号菜单', exact: true }).click()
  await page.getByRole('menuitem', { name: '设置', exact: true }).click()
  await expect(page.getByRole('region', { name: '设置', exact: true })).toBeVisible()
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    'font fallback overflow'
  )
  await page.screenshot({ animations: 'disabled', path: `${artifacts}/font-fallback-mobile.png` })
  assert.deepEqual(errors, [])
  console.log(
    'PASS design screenshots: library, import, reader, guide, focus, mobile and dark mode'
  )
} finally {
  await browser.close()
  await new Promise(resolve => server.httpServer.close(resolve))
}
