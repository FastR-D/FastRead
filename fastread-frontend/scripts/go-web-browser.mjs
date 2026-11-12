import { chromium, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'

const base = process.env.FASTREAD_TEST_BASE_URL || 'http://127.0.0.1:13015'
const email = process.env.FASTREAD_TEST_EMAIL, password = process.env.FASTREAD_TEST_PASSWORD
if (!email || !password) throw new Error('Set FASTREAD_TEST_EMAIL and FASTREAD_TEST_PASSWORD to a disposable administrator account.')
const artifacts = 'test-results/go-web'
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: 'light' })
const page = await context.newPage(), errors = [], scenarios = [], stamp = Date.now()
page.on('pageerror', e => errors.push(e.message))
page.setDefaultTimeout(30000)
function textPdf() {
  const stream = 'BT /F1 18 Tf 50 740 Td (FastRead Browser Validation) Tj 0 -32 Td /F1 12 Tf (Research methods and reproducible evidence.) Tj 0 -22 Td (This paper studies an efficient reading workflow.) Tj ET'
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`]
  let data = '%PDF-1.4\n', offsets = [0]
  objects.forEach((object, i) => { offsets.push(Buffer.byteLength(data)); data += `${i + 1} 0 obj\n${object}\nendobj\n` })
  const xref = Buffer.byteLength(data)
  data += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(data)
}
try {
  await page.goto(base)
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page.getByRole('tab', { name: '论文库' })).toBeVisible({ timeout: 30000 })
  const health = await (await context.request.get(`${base}/api/health`)).json()
  assert.equal(health.backend, 'go')
  await page.getByRole('tab', { name: '用户管理' }).click()
  await page.getByRole('button', { name: '创建用户', exact: true }).click()
  const newEmail = `browser-${stamp}@example.test`
  await page.getByLabel('邮箱', { exact: true }).fill(newEmail)
  await page.getByLabel('姓名', { exact: true }).fill('Browser reader')
  await page.getByLabel('初始密码', { exact: true }).fill(`browser-test-password-${stamp}`)
  await page.getByLabel('操作原因', { exact: true }).fill('Browser account validation')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  const userRow = page.getByRole('row').filter({ hasText: newEmail })
  await expect(userRow).toBeVisible()
  for (const status of ['disabled', 'active']) {
    await userRow.getByRole('button', { name: '编辑', exact: true }).click()
    await page.getByLabel(/^状态/).selectOption(status)
    await page.getByLabel('操作原因', { exact: true }).fill('Browser account validation')
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await expect(userRow.getByText(status === 'active' ? '启用' : '停用', { exact: true })).toBeVisible()
  }
  scenarios.push('real login, administrator creation and account enable/disable')
  await page.getByRole('tab', { name: '管理后台' }).click()
  await page.getByText('添加公用模型', { exact: true }).click()
  const form = page.locator('.admin-create-provider form')
  const providerName = `Browser shared model ${stamp}`
  await form.getByLabel('名称', { exact: true }).fill(providerName)
  await form.getByLabel('API 地址', { exact: true }).fill('https://api.openai.com/v1')
  await form.getByLabel('API 密钥', { exact: true }).fill('disposable-browser-fixture')
  await form.getByLabel('模型 ID（逗号分隔）').fill('browser-test-model')
  await form.getByRole('checkbox').first().check()
  await form.getByRole('button', { name: '保存公用模型' }).click()
  const provider = page.locator('.shared-models article').filter({ hasText: providerName })
  await expect(provider).toBeVisible()
  await provider.getByRole('button', { name: '停用模型' }).click()
  await expect(provider.getByRole('button', { name: '启用模型' })).toBeVisible()
  scenarios.push('shared provider creation, workspace grant and disable')
  await page.getByRole('button', { name: '设置', exact: true }).click()
  const settings = page.getByRole('dialog', { name: '设置', exact: true })
  await expect(settings.getByText('应用联动', { exact: true })).toBeVisible()
  await settings.getByLabel('颜色模式').selectOption('dark')
  await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'dark')
  await page.screenshot({ path: `${artifacts}/settings-dark.png` })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'CAS 认证', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'CAS 认证' }).getByRole('heading', { name: 'FastCAS 账号认证' })).toBeVisible()
  await page.keyboard.press('Escape')
  scenarios.push('real settings, integration availability, CAS state and dark theme')
  await page.getByRole('tab', { name: '论文库' }).click()
  await page.getByText('导入论文', { exact: true }).click()
  await page.getByLabel('上传 PDF', { exact: true }).setInputFiles({ name: `browser-validation-${stamp}.pdf`, mimeType: 'application/pdf', buffer: textPdf() })
  let imported
  await expect.poll(async () => {
    const data = await (await context.request.get(`${base}/api/jobs`)).json()
    imported = data.items.find(job => job.kind === 'import_pdf' && job.state === 'succeeded')
    const failed = data.items.find(job => job.kind === 'import_pdf' && job.state === 'failed')
    if (failed) throw new Error(`PDF import failed: ${failed.error}`)
    return Boolean(imported)
  }, { timeout: 120000, intervals: [1000, 3000, 5000] }).toBe(true)
  await page.goto(`${base}/?paper=${encodeURIComponent(imported.result.paper_id)}`)
  await expect(page.locator('.notebook-desk')).toBeVisible({ timeout: 30000 })
  await expect(page.locator('.pdf-sheet canvas')).toBeVisible({ timeout: 30000 })
  await page.getByRole('button', { name: '笔记', exact: true }).click()
  await page.getByRole('button', { name: '新建', exact: true }).click()
  await page.getByLabel('笔记标题', { exact: true }).fill(`Browser note ${stamp}`)
  await page.getByLabel('笔记正文', { exact: true }).fill('A reading note saved through the Go API.')
  await page.getByRole('button', { name: '保存这条笔记', exact: true }).click()
  await expect(page.getByText(`Browser note ${stamp}`, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '对话', exact: true }).click()
  await page.screenshot({ path: `${artifacts}/paper-desktop.png` })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: `${artifacts}/paper-mobile.png`, fullPage: true })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile reading layout overflows')
  scenarios.push('real PDF worker import, PDF render, saved research note and mobile reader')
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', backend: health, browser: 'Edge', scenarios }, null, 2))
  console.log(`PASS ${scenarios.length} real Go API + Edge scenarios`)
} finally { await browser.close() }
