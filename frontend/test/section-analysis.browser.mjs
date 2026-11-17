// 断面对比分析面浏览器验收：路由可达、导航落位、三态（offline→demo 按钮/live）、
// 测点多选切换、窗口切换、无横向溢出、DEMO 双重声明、页脚声明、控制台 0 error。
// 自带 API mock，不依赖后端。骨架照 forecast-plane.browser.mjs。
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\section-analysis\\browser`
await mkdir(artifact, { recursive: true })
const port = 4480 + Math.floor(Math.random() * 50)
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: `${root}\\frontend`, stdio: 'ignore' })
const base = `http://127.0.0.1:${port}`
for (let attempt = 0; attempt < 100; attempt++) {
  try { const r = await fetch(base); if (r.ok) break } catch {}
  await new Promise(r => setTimeout(r, 100))
}

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const results = []
async function check(name, fn) {
  try { await fn(); results.push({ name, pass: true }) } catch (e) { results.push({ name, pass: false, err: e.message }); throw e }
}

// live fixture：两个测点的归一化偏移序列
function liveFixture() {
  const series = {
    ect: [],
    egt: []
  }
  for (let t = 0; t <= 120; t += 2) {
    series.ect.push({ t, o: Math.sin(t / 18) * 22 })
    series.egt.push({ t, o: Math.sin(t / 26 + 1.1) * 38 })
  }
  return {
    generatedAt: '2026-11-16T12:00:00Z',
    generatedAtSec: 1763284800,
    windowSec: 120,
    series,
    spread: series.ect.map((p, i) => ({ t: p.t, spread: Math.abs(p.o - series.egt[i].o) })),
    snapshots: [
      { key: 'ect', cn: '冷却液温度', en: 'ECT', unit: '°C', digits: 1, value: 90.2, offset: 8.6, grade: 'ok' },
      { key: 'egt', cn: '排气温度', en: 'EGT', unit: '°C', digits: 0, value: 562, offset: 70.2, grade: 'warn' }
    ],
    demo: false
  }
}

function mockApi(page, mode) {
  page.route(url => url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.startsWith('/api/auth/session')) return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } })
    if (path.startsWith('/api/sentinel/sections')) {
      // offline：返回 200 但 series 为空（避免 503 污染 console error 断言），走"返回数据为空"离线分支
      return mode === 'offline' ? route.fulfill({ json: { code: 200, data: { series: {} } } }) : route.fulfill({ json: { code: 200, data: liveFixture() } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })
}

const errors = []
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 960 } })
  const page = await ctx.newPage()
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`))
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`) })

  // ---- 场景 A：offline → 演示按钮 ----
  mockApi(page, 'offline')
  await page.goto(`${base}/sentinel/sections`, { waitUntil: 'networkidle' })

  await check('路由可达：页头出现', async () => {
    await page.waitForSelector('h1:has-text("断面对比")', { timeout: 8000 })
  })

  await check('offline 态：提示 + 查看演示数据集按钮', async () => {
    await page.waitForSelector('.sp-chart-empty', { timeout: 5000 })
    await page.waitForSelector('button:has-text("查看演示数据集")', { timeout: 2000 })
  })

  await check('offline 态：读数显示 —（不编造）', async () => {
    const empty = await page.locator('.sp-empty').count()
    assert.ok(empty >= 1, '应有 — 空态')
  })

  await check('点击演示 → DEMO 双重声明（角标 + 页脚）', async () => {
    await page.click('button:has-text("查看演示数据集")')
    await page.waitForSelector('.sp-chip--demo', { timeout: 4000 })
    const chipText = await page.locator('.sp-chip--demo').innerText()
    assert.ok(chipText.includes('DEMO'), '角标含 DEMO')
    const foot = await page.locator('.sp-page-foot').innerText()
    assert.ok(foot.includes('演示数据'), '页脚含演示声明')
    assert.ok(foot.includes('虚构示例'), '页脚含虚构声明')
  })

  await check('demo 态：主图 canvas 渲染 + 读数汇总行', async () => {
    await page.waitForSelector('.so-chart-canvas', { timeout: 4000 })
    const rows = await page.locator('.sp-snap-row').count()
    assert.ok(rows >= 2, `读数行 >= 2，实际 ${rows}`)
  })

  await check('测点多选：切掉一个再切回', async () => {
    await page.click('button.sp-sensor:has-text("ECT")') // 至少 2 个时允许移除
    await page.waitForTimeout(300)
    let count = await page.locator('button.sp-sensor[aria-pressed="true"]').count()
    assert.ok(count >= 1)
    await page.click('button.sp-sensor:has-text("ECT")')
    await page.waitForTimeout(300)
    count = await page.locator('button.sp-sensor[aria-pressed="true"]').count()
    assert.ok(count >= 2)
  })

  await check('窗口切换 60s → aria-pressed 更新', async () => {
    await page.click('button.sp-seg__btn:has-text("60s")')
    await page.waitForTimeout(300)
    const pressed = await page.locator('button.sp-seg__btn[aria-pressed="true"]').innerText()
    assert.equal(pressed.trim(), '60s')
    await page.click('button.sp-seg__btn:has-text("120s")')
  })

  await check('无横向溢出', async () => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    assert.ok(overflow <= 0, `横向溢出 ${overflow}px`)
  })

  await page.screenshot({ path: `${artifact}\\demo.png`, fullPage: true })

  // ---- 场景 B：live 态 ----
  const page2 = await ctx.newPage()
  mockApi(page2, 'live')
  await page2.goto(`${base}/sentinel/sections`, { waitUntil: 'networkidle' })
  await check('live 态：无 DEMO 角标，MODE LIVE', async () => {
    await page2.waitForSelector('h1:has-text("断面对比")', { timeout: 8000 })
    await page2.waitForTimeout(1200) // 等 boot（live 优先于 1s demo 兜底）
    const chipCount = await page2.locator('.sp-chip--demo').count()
    assert.equal(chipCount, 0)
  })
  await check('live 态：读数来自 fixture', async () => {
    await page2.waitForSelector('.sp-snap-row', { timeout: 4000 })
    const text = await page2.locator('.sp-snap-body').innerText()
    assert.ok(text.includes('90.2'), 'fixture 值 90.2 出现')
    assert.ok(text.includes('预警'), 'EGT warn 分级出现')
  })
  await page2.screenshot({ path: `${artifact}\\live.png`, fullPage: true })

  // ---- 导航落位 ----
  const page3 = await ctx.newPage()
  mockApi(page3, 'live')
  await page3.goto(`${base}/sentinel`, { waitUntil: 'networkidle' })
  await check('侧栏出现 SECTION ANALYSIS 项', async () => {
    // 侧栏组默认折叠，断言路由链接存在即可（展开后可见）
    await page3.locator('a[href="/sentinel/sections"]').first().waitFor({ state: 'attached', timeout: 6000 })
  })

  await check('控制台 0 error', async () => {
    assert.deepEqual(errors, [])
  })
} finally {
  await browser.close()
  vite.kill()
}

const failed = results.filter(r => !r.pass)
console.log(`\n== section-analysis.browser: ${results.length - failed.length}/${results.length} passed ==`)
for (const r of results) console.log(`  ${r.pass ? 'PASS' : 'FAIL'} ${r.name}${r.pass ? '' : ' :: ' + r.err}`)
if (failed.length) process.exit(1)
