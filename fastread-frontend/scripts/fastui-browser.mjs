import { chromium, expect } from '@playwright/test'
import { preview } from 'vite'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'

const artifacts = 'test-results/fastui'
await mkdir(artifacts, { recursive: true })
const server = await preview({ configFile: false, preview: { host: '127.0.0.1', port: 0 } })
const base = `http://127.0.0.1:${server.httpServer.address().port}`
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block', colorScheme: 'light' })
const writes = [], errors = [], scenarios = []
let providers = [{ id: 'provider-1', name: 'Workspace model', models: ['model-a', 'model-b'] }]
let signedIn = true, isAdmin = true, newsText = 'Existing research direction', connected = false
let availability = { enabled: true, login_enabled: true, link_enabled: true }
let accountStatus = { enabled: true, link_enabled: true, link: { id: 'link', state: 'prepared', subject: 'reader', version: 1 } }
let users = [{ id: 'reader', email: 'reader@example.test', display_name: 'Reader', role: 'admin', workspace_id: 'workspace', workspace_name: 'Workspace', disabled: false }, { id: 'reader', email: 'reader@example.test', display_name: 'Reader', role: 'admin', workspace_id: 'secondary', workspace_name: 'Second workspace', disabled: false }]
const shared = [{ id: 'shared', name: 'Shared model', models: ['model-c'], enabled: true, workspace_ids: ['workspace'], user_ids: [], base_url: 'https://model.example.test/v1' }]
await context.route('**/api/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  const body = ['POST', 'PATCH', 'PUT'].includes(request.method()) ? request.postDataJSON() : null
  if (body) writes.push({ path, body })
  let value = { items: [] }, status = 200
  if (path === '/api/auth/me') { status = signedIn ? 200 : 401; value = signedIn ? { id: 'reader', is_admin: isAdmin, display_name: 'Reader', role: 'owner', workspace_id: 'workspace', csrf: 'fixture-csrf', workspace: { name: 'Workspace', daily_limit: 24 } } : { detail: 'Login required' } }
  else if (path === '/api/auth/fastcas/available') value = availability
  else if (path === '/api/auth/session-init') value = { csrf: 'signup-csrf' }
  else if (path === '/api/auth/fastcas/registration') value = body ? { url: `${base}/?fastcas=registered` } : { email: 'signup@example.test', display_name: 'CAS reader' }
  else if (path === '/api/providers') { if (body) providers = [...providers, { id: 'provider-2', ...body }]; value = { items: providers } }
  else if (path === '/api/auth/fastcas/status') value = accountStatus
  else if (path === '/api/auth/local-credential') { status = 422; value = { detail: '原密码未通过校验' } }
  else if (path === '/api/papers') value = { items: [{ id: 'paper-1', title: 'A Research Paper', active_version: 'v1', page_count: 4, tags: [] }], total: 1 }
  else if (path === '/api/admin/users') { if (body) users.push({ id: 'new-user', ...body, disabled: false }); value = { items: users } }
  else if (path === '/api/admin/users/new-user') { users = users.map(user => user.id === 'new-user' ? { ...user, ...body } : user); value = { ok: true } }
  else if (path === '/api/admin/workspaces') value = { items: [{ id: 'workspace', name: 'Workspace' }] }
  else if (path === '/api/admin/providers') { if (body) shared.push({ id: 'new-provider', enabled: true, ...body }); value = { items: shared } }
  else if (path === '/api/admin/providers/shared') { Object.assign(shared[0], body); value = { ok: true } }
  else if (path === '/api/admin/status') value = { version: '2.0.0', users: new Set(users.map(user => user.id)).size, papers: 1, queued: 0, running: 0 }
  else if (path === '/api/integrations/status') value = { fastnews: { connected, url: 'https://news.example.test' }, fastwrite: { connected: true, url: 'https://write.example.test' } }
  else if (path === '/api/integrations/connections/fastnews') { connected = request.method() === 'POST'; value = { ok: true } }
  else if (path === '/api/integrations/fastwrite/projects') value = { items: [{ id: 'project-1', name: 'My manuscript' }] }
  else if (path === '/api/integrations/fastwrite/sync') value = { ok: true, url: 'https://write.example.test/project-1' }
  else if (path === '/api/integrations/fastwrite/projects/project-1/feedback') value = { ok: true, saved: 2 }
  else if (path === '/api/integrations/fastwrite/export') value = { files: [{ path: 'bundle/references.bib', content: '@article{paper1,title={A Research Paper}}' }, { path: 'bundle/evidence.md', content: '# A Research Paper' }], papers: [] }
  else if (path === '/api/integrations/fastnews/directions') { if (body) newsText = body.mode === 'replace' ? body.text : `${newsText}\n${body.text}`; value = { text: newsText } }
  else if (path === '/api/research/directions') value = { id: 'direction-job', state: 'queued' }
  else if (path === '/api/jobs/direction-job') value = { id: 'direction-job', state: 'succeeded', result: { text: 'Investigate efficient visual reasoning.' } }
  await route.fulfill({ status, json: value })
})
try {
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(base)
  for (const name of ['论文库', '用户管理', '管理后台']) await expect(page.getByRole('button', { name, exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '论文库', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: /展开左边栏|收起左边栏/ })).toHaveCount(0)
  await page.getByRole('button', { name: '设置', exact: true }).click()
  const settings = page.getByRole('dialog', { name: '设置', exact: true }), name = settings.getByLabel('名称', { exact: true })
  await name.fill('Research endpoint'); await name.focus()
  const peer = await context.newPage(); await peer.goto(base)
  await peer.evaluate(() => localStorage.setItem('fastread.theme', 'dark'))
  await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'dark')
  await expect(name).toBeFocused(); await expect(name).toHaveValue('Research endpoint')
  await expect(name).toHaveCSS('background-color', 'rgb(23, 30, 39)')
  await settings.getByLabel('颜色模式').selectOption('system')
  await page.emulateMedia({ colorScheme: 'light' }); await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'light')
  await page.emulateMedia({ colorScheme: 'dark' }); await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', 'dark')
  await settings.getByLabel('当前使用的模型').selectOption('provider-1|model-b')
  await settings.getByRole('button', { name: '保存供应商' }).click(); assert.equal(writes.length, 0)
  await settings.getByLabel('API 地址', { exact: true }).fill('https://model.example.test/v1')
  await settings.getByLabel('API 密钥', { exact: true }).fill('fixture-key')
  await settings.getByRole('button', { name: '保存供应商' }).click(); await expect(name).toHaveValue('')
  await expect(settings.getByLabel('当前使用的模型')).toHaveValue('provider-1|model-b')
  assert.deepEqual(writes[0], { path: '/api/providers', body: { name: 'Research endpoint', base_url: 'https://model.example.test/v1', api_key: 'fixture-key', models: ['qwen3.8-27b', 'glm-5.2'] } })
  await settings.getByLabel('连接码').fill('fixture-pairing-code')
  await settings.getByRole('button', { name: '保存连接' }).click()
  await expect(settings.getByRole('button', { name: '断开连接' })).toHaveCount(2)
  scenarios.push('native modal, model save, pairing connection, cross-tab and system theme')
  for (const width of [1440, 1024, 390]) for (const mode of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 }); await settings.getByLabel('颜色模式').selectOption(mode)
    assert.ok(await settings.evaluate(el => el.scrollWidth <= el.clientWidth), 'settings modal overflows')
    await page.screenshot({ path: `${artifacts}/settings-${mode}-${width}.png`, fullPage: true, animations: 'disabled' })
  }
  await page.keyboard.press('Escape'); await expect(settings).not.toBeVisible()
  await expect(page.getByRole('button', { name: '设置', exact: true })).toBeFocused()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: 'CAS 认证', exact: true }).click()
  const account = page.getByRole('dialog', { name: 'CAS 认证', exact: true })
  await account.getByText('设置本地登录邮箱和密码', { exact: true }).click()
  await account.getByLabel('登录邮箱', { exact: true }).fill('reader@example.test')
  await account.getByLabel('新密码', { exact: true }).fill('long-password-draft')
  await account.getByRole('button', { name: '保存本地登录方式' }).click()
  await expect(account.getByRole('alert')).toHaveText('原密码未通过校验')
  await expect(account.getByLabel('新密码', { exact: true })).toHaveValue(''); await page.keyboard.press('Escape')
  for (const link of [null, { id: 'link', state: 'prepared', subject: 'reader', version: 1 }]) {
    accountStatus = { enabled: true, link_enabled: false, link }; await page.reload()
    await page.getByRole('button', { name: 'CAS 认证', exact: true }).click()
    await account.getByLabel('当前账号密码', { exact: true }).fill('original-password')
    await expect(account.getByRole('button', { name: link ? '重试完成认证' : '认证当前账号', exact: true })).toBeDisabled()
    if (link) await expect(account.getByRole('button', { name: '解除认证', exact: true })).toBeEnabled()
    await page.keyboard.press('Escape')
  }
  scenarios.push('CAS modal credential cleanup and independent linking modes')
  await page.getByRole('button', { name: '用户管理' }).click()
  const userList = page.getByRole('region', { name: '用户列表', exact: true })
  await expect(userList.getByRole('button', { name: '编辑', exact: true }).first()).toBeDisabled()
  await expect(userList.getByRole('row')).toHaveCount(2)
  await expect(userList).toContainText('Workspace、Second workspace')
  await page.getByRole('button', { name: '新增用户', exact: true }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('new@example.test'); await page.getByLabel('显示名称', { exact: true }).fill('New reader')
  await page.getByLabel('初始密码', { exact: true }).fill('new-reader-password'); await page.getByLabel('工作区名称', { exact: true }).fill('New workspace')
  await page.getByLabel('操作原因', { exact: true }).fill('Browser account creation')
  await page.getByRole('button', { name: '创建用户', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '新增用户', exact: true })).not.toBeVisible()
  const newUser = userList.getByRole('row').filter({ hasText: 'new@example.test' })
  await expect(newUser).toBeVisible()
  const actionColors = await newUser.evaluate(row => {
    const probe = document.createElement('span')
    row.append(probe)
    const colors = Object.fromEntries(Object.entries({ neutral: '--fastui-raised', primary: '--fastui-primary', danger: '--fastui-danger-fill' }).map(([name, token]) => {
      probe.style.backgroundColor = `var(${token})`
      return [name, getComputedStyle(probe).backgroundColor]
    }))
    probe.remove()
    return colors
  })
  await expect(newUser.getByRole('button', { name: '编辑', exact: true })).toHaveCSS('background-color', actionColors.neutral)
  await expect(newUser.getByRole('button', { name: '停用', exact: true })).toHaveCSS('background-color', actionColors.danger)
  await page.getByLabel('搜索用户', { exact: true }).fill('new@example.test')
  await expect(userList.getByRole('row')).toHaveCount(2)
  await newUser.getByRole('button', { name: '编辑', exact: true }).click()
  const editUser = page.getByRole('dialog', { name: '编辑用户权限', exact: true })
  await expect(editUser).toBeVisible()
  await editUser.getByLabel('角色', { exact: true }).selectOption('admin')
  await editUser.getByLabel('操作原因', { exact: true }).fill('Browser role update')
  await editUser.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(newUser.getByRole('cell', { name: '系统管理员', exact: true })).toBeVisible()
  await newUser.getByRole('button', { name: '停用', exact: true }).click()
  await expect(newUser.getByRole('button', { name: '启用', exact: true })).toBeVisible()
  await page.mouse.move(0, 0)
  await expect(newUser.getByRole('button', { name: '启用', exact: true })).toHaveCSS('background-color', actionColors.primary)
  await page.getByLabel('筛选账号状态', { exact: true }).selectOption('active')
  await expect(page.getByRole('heading', { name: '没有匹配的用户', exact: true })).toBeVisible()
  await page.getByLabel('筛选账号状态', { exact: true }).selectOption('')
  await newUser.getByRole('button', { name: '启用', exact: true }).click()
  await page.getByLabel('搜索用户', { exact: true }).fill('')
  for (const width of [1440, 1024, 390]) for (const mode of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 })
    await peer.evaluate(mode => localStorage.setItem('fastread.theme', mode), mode)
    await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', mode)
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'user list overflows the page')
    await page.screenshot({ path: `${artifacts}/users-${mode}-${width}.png`, fullPage: true, animations: 'disabled' })
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '管理后台', exact: true }).click()
  const modelList = page.getByRole('region', { name: '共享模型列表', exact: true })
  const sharedRow = modelList.getByRole('row').filter({ hasText: 'Shared model' })
  await expect(sharedRow).toBeVisible()
  await sharedRow.getByRole('button', { name: '授权', exact: true }).click()
  const grants = page.getByRole('dialog', { name: '模型授权', exact: true })
  await expect(grants.getByLabel('Workspace', { exact: true })).toBeChecked()
  await expect(grants.getByRole('checkbox', { name: 'Reader reader@example.test', exact: true })).toHaveCount(1)
  const scopeInputs = grants.getByRole('searchbox')
  const inputBoxes = await scopeInputs.evaluateAll(inputs => inputs.map(input => { const box = input.getBoundingClientRect(); return { y: box.y, height: box.height } }))
  assert.equal(inputBoxes[0].y, inputBoxes[1].y, 'scope search fields are misaligned')
  assert.equal(inputBoxes[0].height, inputBoxes[1].height, 'scope search fields have different heights')
  const initialScopeHeight = inputBoxes[0].height
  await scopeInputs.first().fill('no-matching-workspace')
  await expect(grants.getByRole('group', { name: '授权工作区', exact: true })).toHaveText('无匹配结果')
  assert.deepEqual(await scopeInputs.evaluateAll(inputs => inputs.map(input => input.getBoundingClientRect().height)), [initialScopeHeight, initialScopeHeight], 'filtering must not stretch search fields')
  await scopeInputs.first().fill('')
  const writesBeforeGrant = writes.length
  await grants.getByLabel('Workspace', { exact: true }).uncheck()
  await grants.getByRole('checkbox', { name: 'New reader new@example.test', exact: true }).check()
  assert.equal(writes.length, writesBeforeGrant, 'grant edits must be staged until saved')
  await grants.getByRole('button', { name: '取消', exact: true }).click()
  await sharedRow.getByRole('button', { name: '授权', exact: true }).click()
  await expect(grants.getByLabel('Workspace', { exact: true })).toBeChecked()
  await expect(grants.getByRole('checkbox', { name: 'New reader new@example.test', exact: true })).not.toBeChecked()
  await grants.getByLabel('Workspace', { exact: true }).uncheck()
  await grants.getByRole('checkbox', { name: 'New reader new@example.test', exact: true }).check()
  for (const width of [1440, 1024, 390]) for (const mode of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 })
    await peer.evaluate(mode => localStorage.setItem('fastread.theme', mode), mode)
    await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', mode)
    assert.ok(await grants.evaluate(el => el.scrollWidth <= el.clientWidth), 'grant dialog overflows')
    await page.locator('html').evaluate((el, touch) => { if (touch) el.dataset.fastuiDensity = 'touch'; else delete el.dataset.fastuiDensity }, width === 390)
    const layout = await grants.evaluate(el => {
      const inputs = [...el.querySelectorAll('input[type="search"]')]
      const styles = getComputedStyle(inputs[0])
      return { inputHeights: inputs.map(input => input.getBoundingClientRect().height), expectedHeight: Math.max(parseFloat(styles.getPropertyValue('--fastui-height-md')), parseFloat(styles.getPropertyValue('--fastui-touch-target'))), rowHeights: [...el.querySelectorAll('.fastui-list-row')].map(row => row.getBoundingClientRect().height) }
    })
    assert.deepEqual(layout.inputHeights, [layout.expectedHeight, layout.expectedHeight], 'scope search fields must retain the FastUI control height')
    assert.ok(layout.rowHeights.every(height => height === 64), 'scope options must retain a fixed height')
    await page.screenshot({ path: `${artifacts}/grants-${mode}-${width}.png`, fullPage: true, animations: 'disabled' })
  }
  await page.locator('html').evaluate(el => { delete el.dataset.fastuiDensity })
  await grants.getByRole('button', { name: '保存授权', exact: true }).click()
  await expect(grants).not.toBeVisible()
  assert.deepEqual(writes.at(-1), { path: '/api/admin/providers/shared', body: { workspace_ids: [], user_ids: ['new-user'] } })
  await expect(sharedRow).toContainText('0 工作区')
  await expect(sharedRow).toContainText('1 用户')
  for (const width of [1440, 1024, 390]) for (const mode of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 })
    await peer.evaluate(mode => localStorage.setItem('fastread.theme', mode), mode)
    await expect(page.locator('html')).toHaveAttribute('data-fastui-theme', mode)
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'model list overflows the page')
    await page.screenshot({ path: `${artifacts}/models-${mode}-${width}.png`, fullPage: true, animations: 'disabled' })
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await sharedRow.getByRole('button', { name: '授权', exact: true }).click()
  await expect(grants.getByLabel('Workspace', { exact: true })).not.toBeChecked()
  await expect(grants.getByRole('checkbox', { name: 'New reader new@example.test', exact: true })).toBeChecked()
  await page.keyboard.press('Escape')
  await sharedRow.getByRole('button', { name: '停用模型', exact: true }).click()
  await expect(sharedRow.getByRole('button', { name: '启用模型', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '添加公用模型', exact: true }).click()
  const createModel = page.getByRole('dialog', { name: '添加公用模型', exact: true })
  await createModel.getByLabel('名称', { exact: true }).fill('New shared model')
  await createModel.getByLabel('API 地址', { exact: true }).fill('https://model.example.test/v1')
  await createModel.getByLabel('API 密钥', { exact: true }).fill('fixture-key')
  await createModel.getByLabel('模型 ID（逗号分隔）', { exact: true }).fill('model-d, model-e')
  await createModel.getByLabel('Workspace', { exact: true }).check()
  await createModel.getByRole('checkbox', { name: 'New reader new@example.test', exact: true }).check()
  await createModel.getByRole('button', { name: '保存公用模型', exact: true }).click()
  await expect(modelList.getByRole('cell', { name: 'model-d、model-e', exact: true })).toBeVisible()
  assert.deepEqual(writes.at(-1).body.workspace_ids, ['workspace'])
  assert.deepEqual(writes.at(-1).body.user_ids, ['new-user'])
  await page.getByLabel('搜索模型', { exact: true }).fill('not-a-model')
  await expect(page.getByRole('heading', { name: '没有匹配的模型', exact: true })).toBeVisible()
  await page.getByLabel('搜索模型', { exact: true }).fill('')
  scenarios.push('FastWrite-style searchable user/model lists, user editing, staged workspace/user grants, creation and enable/disable')
  await page.getByRole('button', { name: '论文库', exact: true }).click(); await page.getByRole('checkbox', { name: '选择论文 A Research Paper' }).check()
  await page.getByRole('button', { name: '提炼研究方向', exact: true }).click()
  const research = page.getByRole('dialog', { name: '提炼研究方向' })
  await research.getByRole('button', { name: '从所选论文提炼方向' }).click()
  await expect(research.getByLabel('研究方向', { exact: true })).toHaveValue('Investigate efficient visual reasoning.')
  await research.getByLabel('研究方向', { exact: true }).fill('Edited research direction'); await research.getByRole('button', { name: '同步到 FastNews' }).click()
  await expect(research.getByRole('status')).toHaveText('研究方向已同步到 FastNews。'); assert.equal(newsText, 'Existing research direction\nEdited research direction')
  await page.keyboard.press('Escape'); await page.getByRole('button', { name: '交接 FastWrite', exact: true }).click()
  const writing = page.getByRole('dialog', { name: '交接 FastWrite' })
  await writing.getByLabel('FastWrite 项目').selectOption('project-1'); await writing.getByRole('button', { name: '同步到写作项目' }).click()
  await expect(writing.getByRole('link', { name: '打开 FastWrite 项目' })).toHaveAttribute('href', 'https://write.example.test/project-1')
  await writing.getByRole('button', { name: '取回写作笔记' }).click()
  await expect(writing.getByRole('status')).toHaveText('已取回 2 条写作笔记，打开对应论文即可查看。')
  await writing.getByLabel('下载格式').selectOption('bibtex'); const download = page.waitForEvent('download')
  await writing.getByRole('button', { name: '下载资料' }).click(); assert.equal((await download).suggestedFilename(), 'fastread-papers.bib')
  scenarios.push('selected papers to editable News directions and FastWrite sync/export')
  isAdmin = false; await page.reload(); await expect(page.getByRole('button', { name: '论文库', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '用户管理' })).toHaveCount(0); await expect(page.getByRole('button', { name: '管理后台' })).toHaveCount(0)
  signedIn = false
  for (const flags of [{ enabled: true, login_enabled: true, link_enabled: false }, { enabled: true, login_enabled: false, link_enabled: true }, { enabled: false, login_enabled: false, link_enabled: false }]) {
    availability = flags; await page.reload(); await expect(page.getByRole('heading', { name: '登录资料库' })).toBeVisible()
    await expect.poll(() => page.getByRole('link', { name: '使用 FastCAS 登录' }).count()).toBe(flags.enabled && flags.login_enabled ? 1 : 0)
    await expect(page.getByRole('button', { name: '使用邀请注册', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: '恢复账号', exact: true }).click(); await expect(page.getByRole('heading', { name: '恢复账号' })).toBeVisible()
  }
  await page.goto(`${base}/?fastcas=register`)
  await expect(page.getByRole('heading', { name: '完善 FastRead 账号', exact: true })).toBeVisible()
  await expect(page.getByLabel('姓名', { exact: true })).toHaveValue('CAS reader')
  await expect(page.getByLabel('邮箱', { exact: true })).toHaveValue('signup@example.test')
  await page.getByLabel('新密码（至少 12 个字符）', { exact: true }).fill('signup-local-password')
  await page.getByRole('button', { name: '确认', exact: true }).click()
  await expect(page).toHaveURL(`${base}/?fastcas=registered`)
  assert.deepEqual(writes.at(-1), { path: '/api/auth/fastcas/registration', body: { email: 'signup@example.test', display_name: 'CAS reader', password: 'signup-local-password' } })
  scenarios.push('non-admin navigation, independent login/recovery and confirmed CAS signup')
  assert.deepEqual(errors, [])
  await writeFile(`${artifacts}/results.json`, JSON.stringify({ status: 'passed', browser: 'Edge', scenarios, viewports: [1440, 1024, 390], modes: ['light', 'dark'] }, null, 2))
  console.log(`PASS ${scenarios.length} FastRead FastUI browser scenarios`)
} catch (error) {
  const last = context.pages()[0]
  if (last) { await last.screenshot({ path: `${artifacts}/failure.png`, fullPage: true, animations: 'disabled' }); await writeFile(`${artifacts}/failure.html`, await last.content()) }
  throw error
} finally { await browser.close(); await new Promise(resolve => server.httpServer.close(resolve)) }
