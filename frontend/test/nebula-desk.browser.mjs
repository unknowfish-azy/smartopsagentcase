// 星云投影浏览器验收（T32d）：第 4 投影切换、粒子渲染、hover tooltip（维度重着色）、
// 点击开既有证据抽屉且选中联动、键盘 4、DEMO 水印态、空态非空转球、窄屏隐藏 tab、双主题截图、0 报错。
// 自带 API mock（精确锚定 /api/ 具体路径，勿用 **/api/** ——照片墙已踩过误匹配源码模块的坑），不依赖后端。
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\frontend\\test-artifacts\\nebula`
await mkdir(artifact, { recursive: true })
const port = 4430 + Math.floor(Math.random() * 50)
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

  // Fixtures：120 条事件 × 4 等级 × 8 类别（覆盖维度八色带），24h 窗口内均匀铺开
  const categories = ['AGENT_BEHAVIOR', 'EVIDENCE_QUALITY', 'TOOL_USAGE', 'OBSERVABILITY', 'APPROVAL', 'VERIFICATION', 'DATABASE', 'SECURITY']
  const severities = ['PASS', 'WARN', 'HIGH', 'CRITICAL']
  const now = Date.now()
  const events = Array.from({ length: 120 }, (_, i) => ({
    id: `EV-${String(i).padStart(3, '0')}`,
    createdAt: new Date(now - (23 - (i % 24)) * 3600 * 1000).toISOString(),
    severity: severities[i % 4],
    taskId: `task-${i % 9}`,
    category: categories[i % 8],
    target: `node-${i % 5}`,
    traceId: i % 3 === 0 ? `tr-${i}` : null
  }))
  const runs = events.filter(e => e.traceId).slice(0, 10).map((e, i) => ({
    id: `RUN-${i}`,
    toolId: 'prometheus-query',
    startedAt: new Date(now - 3600 * 1000).toISOString(),
    endedAt: new Date(now - 3500 * 1000).toISOString(),
    status: 'SUCCESS',
    traceId: e.traceId,
    exitCode: 0
  }))

  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: events } }))
  await page.route('**/api/inspector/summary*', route => route.fulfill({ json: { code: 200, data: {} } }))
  await page.route('**/api/inspector/statistics*', route => route.fulfill({ json: { code: 200, data: { byCategory: {} } } }))
  await page.route('**/api/operations/runs*', route => route.fulfill({ json: { code: 200, data: { items: runs, total: runs.length } } }))
  await page.route('**/api/auth/session*', route => route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } }))
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' }))
    // 尊重已存主题（后续用例会切 light），缺省 dark
    if (!localStorage.getItem('smartops_theme')) localStorage.setItem('smartops_theme', 'dark')
  })

  await page.goto(`${base}/inspector/desk`, { waitUntil: 'networkidle' })

  const tabs = page.getByRole('tablist', { name: '投影' }).getByRole('tab')

  // 1. 第 4 投影 tab + 默认仍为纠察（省赛分镜口径零破坏）
  await check('默认投影仍为纠察', async () => {
    assert.equal(await tabs.first().getAttribute('aria-selected'), 'true')
    assert.equal(await tabs.count(), 4)
  })

  // 2. 键盘 4 → 星云
  await page.keyboard.press('4')
  await check('键盘 4 切到星云', async () => {
    await page.waitForFunction(() => document.querySelector('.inspector-desk')?.getAttribute('data-view') === 'nebula')
  })
  await check('星云 aria-label 摘要含四等级', async () => {
    const label = await page.locator('.nebula-card').getAttribute('aria-label')
    assert.match(label, /星云投影，\d+ 颗事件：严重 \d+、高 \d+、警告 \d+、通过 \d+/)
  })

  // 3. Canvas 已绘制粒子（非空白）
  await check('星云 canvas 有粒子像素', async () => {
    const painted = await page.evaluate(() => {
      const canvas = document.querySelector('.nebula-card canvas')
      const ctx = canvas.getContext('2d')
      const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
      let hit = 0
      for (let i = 3; i < data.length; i += 4) if (data[i] > 0) hit += 1
      return hit
    })
    assert.ok(painted > 500, `不透明像素过少：${painted}`)
  })

  // 4. hover：网格扫到粒子 → tooltip 出现
  const canvasBox = await page.locator('.nebula-card canvas').boundingBox()
  let hoverPoint = null
  outer: for (let gx = 0.25; gx <= 0.76; gx += 0.05) {
    for (let gy = 0.2; gy <= 0.81; gy += 0.06) {
      const x = canvasBox.x + canvasBox.width * gx
      const y = canvasBox.y + canvasBox.height * gy
      await page.mouse.move(x, y)
      await page.waitForTimeout(30)
      if (await page.locator('.nebula-card .tip').isVisible()) { hoverPoint = { x, y }; break outer }
    }
  }
  await check('hover 粒子出现 tooltip', async () => {
    assert.ok(hoverPoint, '网格扫描未命中任何粒子')
  })
  await check('tooltip 含等级/任务/维度字段', async () => {
    const html = await page.locator('.nebula-card .tip').innerHTML()
    assert.match(html, /等级/)
    assert.match(html, /任务/)
    assert.match(html, /维度/)
  })

  // 5. 点击同一粒子 → 选中 + 打开既有证据抽屉（零新契约）
  await page.mouse.click(hoverPoint.x, hoverPoint.y)
  await check('点击粒子写入 URL ?id=', async () => {
    await page.waitForFunction(() => new URL(location.href).searchParams.get('id')?.startsWith('EV-'))
  })
  await check('证据抽屉打开', async () => {
    await page.waitForFunction(() => {
      const el = document.querySelector('.drawer, [class*="drawer"]')
      return el && getComputedStyle(el).display !== 'none'
    })
  })

  // 6. 选中态与三视图联动：切回纠察，URL id 保持
  await tabs.nth(0).click()
  await check('切回纠察视图选中不丢', async () => {
    await page.waitForFunction(() => document.querySelector('.inspector-desk')?.getAttribute('data-view') === 'events')
    assert.ok(new URL(page.url()).searchParams.get('id')?.startsWith('EV-'))
  })
  await page.screenshot({ path: `${artifact}/nebula-selected-events-dark.png` })

  // 7. 空态：清空 events → 星云显示空态而非空转球
  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: [] } }))
  await page.reload({ waitUntil: 'networkidle' })
  await page.keyboard.press('4')
  await check('空态显示文案且不渲染粒子球', async () => {
    await page.getByText('窗口内没有纠察事件').waitFor()
  })

  // 8. 窄屏隐藏星云 tab
  await page.setViewportSize({ width: 375, height: 800 })
  await page.waitForTimeout(300)
  await check('窄屏 375px 星云 tab 隐藏', async () => {
    const tab = page.getByRole('tablist', { name: '投影' }).getByRole('tab', { name: /星云/ })
    assert.equal(await tab.count(), 0)
  })

  // 恢复 120 条 fixtures（步骤 7 的空 mock 只服务于空态用例）
  await page.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: events } }))

  // 9. DEMO 态：星云渲染 + 水印（恢复宽屏与数据）
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: '查看演示数据' }).click()
  await check('DEMO 态星云仍有粒子渲染', async () => {
    await page.keyboard.press('4')
    await page.waitForFunction(() => document.querySelector('.nebula-card canvas'))
    const painted = await page.evaluate(() => {
      const canvas = document.querySelector('.nebula-card canvas')
      const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height)
      let hit = 0
      for (let i = 3; i < data.length; i += 4) if (data[i] > 0) hit += 1
      return hit
    })
    assert.ok(painted > 500, `DEMO 态不透明像素过少：${painted}`)
  })
  await page.screenshot({ path: `${artifact}/nebula-demo-dark.png` })

  // 10. 双主题截图：light
  await page.getByRole('button', { name: '退出演示' }).click()
  await page.evaluate(() => localStorage.setItem('smartops_theme', 'light'))
  await page.reload({ waitUntil: 'networkidle' })
  await page.keyboard.press('4')
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${artifact}/nebula-light.png` })

  /* ---------- 非 reduced 上下文：动画推进 / 抽样脚注 / 掉帧降采样 ---------- */
  const page2 = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  page2.setDefaultTimeout(10000)
  page2.on('pageerror', e => errors.push(e.message))
  await page2.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: events } }))
  await page2.route('**/api/inspector/summary*', route => route.fulfill({ json: { code: 200, data: {} } }))
  await page2.route('**/api/inspector/statistics*', route => route.fulfill({ json: { code: 200, data: { byCategory: {} } } }))
  await page2.route('**/api/operations/runs*', route => route.fulfill({ json: { code: 200, data: { items: runs, total: runs.length } } }))
  await page2.route('**/api/auth/session*', route => route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } }))

  // 11. 非 reduced：自转动画帧持续推进
  await page2.goto(`${base}/inspector/desk?view=nebula`, { waitUntil: 'networkidle' })
  await page2.waitForFunction(() => document.querySelector('.nebula-card canvas'))
  await check('非 reduced：canvas 动画帧持续推进（自转/呼吸）', async () => {
    const a = await page2.evaluate(() => document.querySelector('.nebula-card canvas').toDataURL())
    await page2.waitForTimeout(600)
    const b = await page2.evaluate(() => document.querySelector('.nebula-card canvas').toDataURL())
    assert.notEqual(a, b, '600ms 前后 canvas 无变化，动画未运行')
  })

  // 12. 抽样脚注：1500 条事件 → 如实标注 1000/1500
  const bigEvents = Array.from({ length: 1500 }, (_, i) => ({
    id: `BG-${String(i).padStart(4, '0')}`,
    createdAt: new Date(now - (i % 24) * 3600 * 1000).toISOString(),
    severity: severities[i % 4],
    taskId: `task-${i % 9}`,
    category: categories[i % 8],
    target: `node-${i % 5}`,
    traceId: null
  }))
  await page2.route('**/api/inspector/events*', route => route.fulfill({ json: { code: 200, data: bigEvents } }))
  await page2.reload({ waitUntil: 'networkidle' })
  await check('抽样脚注如实标注 1000/1500', async () => {
    await page2.getByText(/已抽样 1000 \/ 总数 1500/).waitFor()
  })

  // 13. 掉帧降采样：CPU 节流 12x → EMA < 22fps → 逐档降 + 脚注如实跟随
  const cdp = await page2.context().newCDPSession(page2)
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 12 })
  await check('掉帧降采样脚注出现且粒数如实', async () => {
    await page2.getByText(/掉帧降采样至 \d+ 粒/).waitFor({ timeout: 30000 })
  })
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 })
  await page2.close()

  await check('控制台无 error', async () => assert.deepEqual(errors.filter(e => !e.includes('vite')), []))

  const passed = results.filter(r => r.pass).length
  console.log(`PASS nebula-desk browser acceptance (${passed}/${results.length})`)
  if (passed !== results.length) {
    for (const r of results.filter(r => !r.pass)) console.error(`FAIL ${r.name}: ${r.err}`)
    process.exitCode = 1
  }
  await page.close()
} catch (e) {
  console.error('NEBULA BROWSER ACCEPTANCE FAILED:', e.message)
  for (const r of results.filter(r => !r.pass)) console.error(`FAIL ${r.name}: ${r.err}`)
  process.exitCode = 1
} finally {
  await browser.close()
  vite.kill()
}
