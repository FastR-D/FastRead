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
  if (path === '/auth/me') value = { id: 'reader', display_name: 'Reader', is_admin: true, role:'owner', csrf: 'fixture', workspace: { name: 'Workspace', daily_limit: 24 } }
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
  await mkdir('test-results/spacing', { recursive: true })
  async function collapse() { const toggle = page.getByRole('button', { name: '收起导航', exact: true }); if (await toggle.count()) await toggle.click() }
  async function sidebarTab(name) { const toggle = page.getByRole('button', { name: '展开导航', exact: true }); if (await toggle.isVisible()) await toggle.click(); await page.getByRole('tab', { name, exact: true }).click(); await collapse() }
  async function geometry() {
    const pageBox = page.locator('.app-page').filter({ visible: true }); await expect(pageBox).toBeVisible()
    return pageBox.evaluate(el => {
      const r = el.getBoundingClientRect(), h = el.querySelector('.app-page-heading').getBoundingClientRect(), title = el.querySelector('h1'), t = title.getBoundingClientRect(), css = getComputedStyle(el), font = getComputedStyle(title)
      const sidebar = document.querySelector('.workbench-sidebar').getBoundingClientRect()
      return { width:r.width, x:r.x, y:r.y, padding:css.padding, gap:css.gap, headingX:h.x-r.x, headingY:h.y-r.y, titleX:t.x-r.x, titleY:t.y-r.y, fontSize:font.fontSize, lineHeight:font.lineHeight, sidebarWidth:sidebar.width }
    })
  }
  for (const width of [1440,1024,768,390,360]) {
    await page.setViewportSize({ width,height:1000 })
    await page.getByRole('button', { name:'FastRead 论文库',exact:true }).click(); await collapse()
    const baseline = await geometry(); assert.equal(baseline.padding, width>=1280?'32px':width>600?'24px':'16px')
    if(width>900)assert.equal(baseline.sidebarWidth,232)
    await page.screenshot({path:`test-results/spacing/library-${width}.png`})
    const toggle=page.getByRole('button',{name:'展开导航',exact:true});if(await toggle.isVisible())await toggle.click()
    await page.getByRole('button',{name:'后台任务',exact:true}).click();await collapse()
    assert.deepEqual(await geometry(),baseline,`jobs ${width}`)
    await page.screenshot({path:`test-results/spacing/jobs-${width}.png`})
    await page.getByRole('tab',{name:'管理',exact:true}).click();await collapse()
    assert.deepEqual(await geometry(),baseline,`management ${width}`)
    await sidebarTab('用户管理');assert.deepEqual(await geometry(),baseline,`users ${width}`)
    await page.getByRole('button',{name:'账号菜单',exact:true}).click()
    await page.getByRole('menuitem',{name:'设置',exact:true}).click();await collapse()
    assert.deepEqual(await geometry(),baseline,`settings ${width}`)
    await sidebarTab('应用联动');assert.deepEqual(await geometry(),baseline,`integrations ${width}`)
    await page.screenshot({path:`test-results/spacing/settings-${width}.png`})
  }
  assert.deepEqual(errors,[])
  console.log('PASS equal page padding, title position, content gap, sidebar width across library/jobs/admin/users/settings/integrations at 1440/1024/768/390/360px')
} finally { await context.close(); await browser.close(); await new Promise(resolve => server.httpServer.close(resolve)) }
