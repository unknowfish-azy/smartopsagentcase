// 洞察台浏览器验收：路由可达、三投影切换、时间窗、键盘、关联四态文案、空态、部分失败、DEMO、无溢出、sr-only 列表。
// 自带 API mock，不依赖后端。
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\inspector-desk\\browser`
await mkdir(artifact, { recursive: true })
const port = 4330 + Math.floor(Math.random() * 50)
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

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))

  // Fixtures：三种关联状态
  const events = [
    { id: 'EV-1', createdAt: '2026-11-14T10:00:00Z', severity: 'HIGH', taskId: 'prom-mem', category: 'OBSERVABILITY', target: 'prom-1', traceId: 'tr_hit' },
    { id: 'EV-2', createdAt: '2026-11-14T11:00:00Z', severity: 'WARN', taskId: 'mysql-conn', category: 'DATABASE', target: 'mysql-1', traceId: 'tr_miss' },
    { id: 'EV-3', createdAt: '2026-11-14T12:00:00Z', severity: 'CRITICAL', taskId: 'k8s-pvc', category: 'CLOUD_NATIVE', target: 'k8s-1', traceId: null }
  ]
  const runs = [
    { id: 'RUN-1', toolId: 'prometheus-query', startedAt: '2026-11-14T10:01:00Z', endedAt: '2026-11-14T10:01:08Z', status: 'SUCCESS', traceId: 'tr_hit', exitCode: 0 }
  ]

  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: events } }))
  await page.route('**/api/inspector/summary*', route => route.fulfill({ json: { code: 200, data: {} } }))
  await page.route('**/api/inspector/statistics*', route => route.fulfill({ json: { code: 200, data: { byCategory: { DATABASE: 16, CLOUD_NATIVE: 17, OBSERVABILITY: 20, STABILITY: 11 } } } }))
  await page.route('**/api/operations/runs*', route => route.fulfill({ json: { code: 200, data: { items: runs, total: 1 } } }))
  await page.route('**/api/auth/session*', route => { route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } }) })
  await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' })); localStorage.setItem('smartops_theme', 'dark') })

  await page.goto(`${base}/inspector/desk`, { waitUntil: 'networkidle' })

  // 1. 路由可达 + 三个 tab
  await page.getByRole('tablist', { name: '投影' }).waitFor()
  const tabs = page.getByRole('tablist', { name: '投影' }).getByRole('tab')
  await check('三个投影 tab 存在', async () => assert.equal(await tabs.count(), 3))
  await check('默认选中纠察', async () => {
    const first = tabs.first()
    assert.equal(await first.getAttribute('aria-selected'), 'true')
  })

  // 2. 三个投影切换
  await tabs.nth(1).click()
  await check('切到统计后 data-view 变化', async () => {
    await page.waitForFunction(() => document.querySelector('.inspector-desk')?.getAttribute('data-view') === 'stats')
  })
  await tabs.nth(2).click()
  await check('切到运行', async () => {
    await page.waitForFunction(() => document.querySelector('.inspector-desk')?.getAttribute('data-view') === 'runs')
  })
  await tabs.nth(0).click()

  // 3. 时间窗
  const winTabs = page.getByRole('tablist', { name: '时间窗' }).getByRole('tab')
  await winTabs.nth(1).click()
  await check('时间窗 7d 同步到 URL', async () => {
    await page.waitForFunction(() => new URL(location.href).searchParams.get('window') === '7d')
  })
  await winTabs.nth(0).click()

  // 4. 键盘
  await page.keyboard.press('3')
  await check('键盘 3 切到运行', async () => {
    await page.waitForFunction(() => document.querySelector('.inspector-desk')?.getAttribute('data-view') === 'runs')
  })
  await page.keyboard.press('1')
  await check('键盘 1 切回纠察', async () => {
    await page.waitForFunction(() => document.querySelector('.inspector-desk')?.getAttribute('data-view') === 'events')
  })

  // 5. 关联文案：选中 EV-1（linked）
  await page.evaluate(() => {
    // 触发选中：直接调用内部状态不便，用键盘 → 选中第一个
  })
  // 用键盘 → 选中第一条（EV-1，tr_hit → linked）
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(300)
  const selCard = page.locator('.side-card').first()
  await check('选中 EV-1 显示已关联文案', async () => {
    const text = await selCard.innerText()
    assert.match(text, /已关联 RUN-1/)
  })

  // 切到 EV-2（tr_miss → miss 文案）
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(300)
  await check('选中 EV-2 显示未命中文案', async () => {
    const text = await selCard.innerText()
    assert.match(text, /运行记录里没有命中/)
  })

  // 切到 EV-3（no-trace）
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(300)
  await check('选中 EV-3 显示无 trace 文案', async () => {
    const text = await selCard.innerText()
    assert.match(text, /没有 traceId/)
  })

  // 6. 空态：mock events 为空
  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: [] } }))
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('tablist', { name: '投影' }).getByRole('tab').nth(0).click()
  await check('空态显示窗口内没有纠察事件', async () => {
    await page.getByText('窗口内没有纠察事件').waitFor()
  })

  // 7. 部分失败：runs 503
  await page.route('**/api/operations/runs*', route => route.fulfill({ status: 503, json: { code: 503, message: 'runs unavailable' } }))
  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: events } }))
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('tablist', { name: '投影' }).getByRole('tab').nth(2).click()
  await check('运行投影失败显示 — + 原因', async () => {
    await page.getByText('runs unavailable').waitFor()
  })
  // 纠察投影仍正常
  await page.getByRole('tablist', { name: '投影' }).getByRole('tab').nth(0).click()
  await check('纠察投影在 runs 失败时仍正常', async () => {
    await page.getByRole('img', { name: /洞察台时间轴/ }).waitFor()
  })

  // 8. DEMO
  await page.getByRole('button', { name: '查看演示数据' }).click()
  await check('DEMO 角标出现', async () => {
    await page.getByText('DEMO · 虚构示例').waitFor()
  })

  // 9. 无横向溢出
  for (const w of [375, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width: w, height: 1000 })
    await page.waitForTimeout(200)
    await check(`无横向溢出 ${w}px`, async () => {
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
      assert.ok(overflow, `${w}px 存在横向溢出`)
    })
  }

  // 10. sr-only 列表项数 = 当前投影可见项数（退出 DEMO，重新加载 fixtures）
  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: events } }))
  await page.route('**/api/operations/runs*', route => route.fulfill({ json: { code: 200, data: { items: runs, total: 1 } } }))
  await page.getByRole('button', { name: '退出演示' }).click()
  await page.waitForTimeout(500)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('tablist', { name: '投影' }).getByRole('tab').nth(0).click()
  await check('sr-only 列表项数 = 纠察可见项数', async () => {
    const count = await page.locator('.sr-only li').count()
    assert.equal(count, events.length)
  })

  // 截图
  await page.screenshot({ path: `${artifact}/inspector-desk-demo.png`, fullPage: true })

  await check('控制台无 error', async () => assert.deepEqual(errors.filter(e => !e.includes('vite')), []))

  console.log(`PASS inspector-desk browser acceptance (${results.filter(r => r.pass).length}/${results.length})`)
  await page.close()
} finally {
  await browser.close()
  vite.kill()
}
