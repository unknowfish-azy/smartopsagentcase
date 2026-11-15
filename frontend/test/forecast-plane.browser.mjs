// 预测面浏览器验收（执行包 §7.2）：路由可达、导航落位、三态（offline/demo/live）、
// 视野切换、回放订阅（暂停后 motionScheduler 订阅数回 0）、键盘（Space/←）、
// 无横向溢出、reduced-motion 默认不播放、DEMO 双重声明、控制台 0 error。
// 自带 API mock，不依赖后端。
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\forecast-plane\\browser`
await mkdir(artifact, { recursive: true })
const port = 4380 + Math.floor(Math.random() * 50)
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

// 确定性 fixture（live 口径）。字段名以实现为准（useForecastSeries.normalizePayload）：
// body.forecast 非空才判 live；forecast 元素 {t, median, p10, p90}；历史为 body.series。
function liveFixture() {
  const forecast = []
  for (let t = 0; t <= 30; t += 5) {
    const median = 93 + Math.sin(t / 8) * 0.8 + t * 0.02
    const spread = 0.6 + Math.sqrt(t) * 0.25
    forecast.push({ t, median, p10: median - spread, p90: median + spread })
  }
  const series = []
  for (let t = -120; t <= 0; t += 2) series.push({ t, v: 88 + Math.sin(t / 30) * 3 + Math.sin(t / 7) * 0.6 })
  return {
    generatedAt: '2026-11-19T15:20:31Z',
    model: { version: 'v3.2', arch: 'MLP+GRU', params: 28417, metrics: { mae: 1.84, rmse: 2.61, mape: 2.3 }, trainedAt: '2026-11-18T21:40:00Z', epochs: 42, gate: 'PASS' },
    series,
    forecast,
    crossings: [{ kind: 'warn', h: 20, value: 96.0, confidence: 0.73 }],
    unit: '°C'
  }
}
const modelsFixture = () => ({ models: [{ version: 'v3.2', gate: 'PASS' }, { version: 'v3.3', gate: 'PENDING' }] })

// 单函数 route 内部分发（mosaic-wall.browser.mjs 已验证的写法）：
// 避免多次注册的匹配顺序与 glob `?` 语义的不确定性；只拦真 /api/ 路径。
function mockApi(page, mode) {
  page.route(url => url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.startsWith('/api/auth/session')) return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } })
    if (path.startsWith('/api/sentinel/forecast/models')) return route.fulfill({ json: { code: 200, data: modelsFixture() } })
    if (path.startsWith('/api/sentinel/forecast')) {
      return mode === 'offline' ? route.fulfill({ status: 503, json: { code: 503, message: 'forecast unavailable' } }) : route.fulfill({ json: { code: 200, data: liveFixture() } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })
}
const mockLive = page => mockApi(page, 'live')
const mockOffline = page => mockApi(page, 'offline')

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))

  await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' })); localStorage.setItem('smartops_theme', 'dark') })

  // ── 1) offline 态：503 → 空态 + 离线 chip ──
  mockOffline(page)
  await page.goto(`${base}/sentinel/forecast`, { waitUntil: 'networkidle' })
  await check('路由可达 .forecast-plane', async () => {
    await page.locator('.forecast-plane').waitFor()
  })
  await check('offline 态角标为离线', async () => {
    assert.equal(await page.locator('.forecast-plane').getAttribute('data-state'), 'offline')
    await page.getByText('离线', { exact: true }).waitFor()
  })
  await check('offline 空态提供查看演示数据集入口', async () => {
    await page.getByRole('button', { name: '查看演示数据集' }).waitFor()
  })

  // ── 2) demo 态：点按钮 → DEMO 双重声明 ──
  await page.getByRole('button', { name: '查看演示数据集' }).click()
  await check('demo 态 data-state=demo', async () => {
    assert.equal(await page.locator('.forecast-plane').getAttribute('data-state'), 'demo')
  })
  await check('DEMO 角标存在', async () => {
    await page.getByText('DEMO · 虚构示例').first().waitFor()
  })
  await check('页脚含虚构声明', async () => {
    const foot = await page.locator('.forecast-page-foot').innerText()
    assert.match(foot, /虚构/)
  })

  // ── 3) live 态：新开页面 + 200 mock（避免路由清空/重载竞态）──
  const livePage = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  livePage.setDefaultTimeout(10000)
  const liveErrors = []
  livePage.on('pageerror', e => liveErrors.push(e.message))
  await livePage.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' })); localStorage.setItem('smartops_theme', 'dark') })
  mockLive(livePage)
  await livePage.goto(`${base}/sentinel/forecast`, { waitUntil: 'networkidle' })
  await check('live 态 data-state=live', async () => {
    assert.equal(await livePage.locator('.forecast-plane').getAttribute('data-state'), 'live')
    await livePage.getByText('正常', { exact: true }).waitFor()
  })
  await check('live 态无 DEMO 角标', async () => {
    assert.equal(await livePage.getByText('DEMO · 虚构示例').count(), 0)
  })

  // ── 4) 视野切换：120s → +120s ──
  const asideBefore = await livePage.locator('.forecast-card-aside').first().innerText()
  await livePage.getByRole('group', { name: '视野' }).getByRole('button', { name: '120s' }).click()
  await check('视野切 120s 后窗口标注变化', async () => {
    const aside = await livePage.locator('.forecast-card-aside').first().innerText()
    assert.match(aside, /\+120s/)
    assert.notEqual(aside, asideBefore)
  })

  // ── 5) 回放订阅：播放 +1，暂停后回基线 ──
  // MainLayout 全局装饰层可能常驻订阅调度器，故用差值断言而非绝对 0。
  const subCount = () => livePage.evaluate(async () => {
    const m = await import('/src/visual/motionScheduler.js')
    return m.subscriberCount()
  })
  const baseSubs = await subCount()
  await livePage.getByRole('button', { name: '回放' }).click()
  await check('回放时 motionScheduler 订阅 +1', async () => {
    assert.equal(await subCount(), baseSubs + 1)
  })
  await livePage.getByRole('button', { name: '暂停' }).click()
  await check('暂停后订阅回基线', async () => {
    await livePage.waitForFunction(async (base) => {
      const m = await import('/src/visual/motionScheduler.js')
      return m.subscriberCount() === base
    }, baseSubs, { timeout: 3000 })
  })

  // ── 6) 键盘：Space 切播放，← 中止播放 ──
  await livePage.keyboard.press(' ')
  await check('Space 开启播放（按钮变暂停）', async () => {
    await livePage.getByRole('button', { name: '暂停' }).waitFor()
  })
  await livePage.keyboard.press('ArrowLeft')
  await check('ArrowLeft 中止播放（按钮变回放）', async () => {
    await livePage.getByRole('button', { name: '回放' }).waitFor()
  })

  // ── 7) 导航落位：SENTINEL 组最后一项 ──
  await check('导航含「预测面」且为 SENTINEL 最后一项', async () => {
    const ok = await livePage.evaluate(() => {
      const link = document.querySelector('a[href="/sentinel/forecast"]')
      if (!link) return false
      if (!link.textContent.includes('预测面')) return false
      const list = link.parentElement
      const links = [...list.querySelectorAll('a[href]')]
      return links[links.length - 1]?.getAttribute('href') === '/sentinel/forecast'
    })
    assert.ok(ok, '预测面链接应存在于 SENTINEL 组末尾')
  })

  // ── 8) 无横向溢出 ──
  for (const w of [375, 768, 1024, 1440, 1920]) {
    await livePage.setViewportSize({ width: w, height: 1000 })
    await livePage.waitForTimeout(200)
    await check(`无横向溢出 ${w}px`, async () => {
      const overflow = await livePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
      assert.ok(overflow, `${w}px 存在横向溢出`)
    })
  }
  await livePage.setViewportSize({ width: 1440, height: 1000 })

  // 截图（live 态，1440）
  await livePage.screenshot({ path: `${artifact}/forecast-live-1440.png`, fullPage: true })

  // ── 9) reduced-motion：默认不播放 ──
  const rmPage = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  rmPage.setDefaultTimeout(10000)
  await rmPage.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' })); localStorage.setItem('smartops_theme', 'dark') })
  mockLive(rmPage)
  await rmPage.goto(`${base}/sentinel/forecast`, { waitUntil: 'networkidle' })
  await check('reduced-motion 下默认不播放', async () => {
    await rmPage.locator('.forecast-plane').waitFor()
    await rmPage.waitForTimeout(400)
    const btnText = await rmPage.getByRole('group', { name: '回放' }).getByRole('button').innerText()
    assert.equal(btnText.trim(), '回放', 'reduced-motion 下不应自动进入播放态')
  })
  await rmPage.screenshot({ path: `${artifact}/forecast-reduced-motion.png` })
  await rmPage.close()

  await check('控制台无 error', async () => assert.deepEqual(errors.filter(e => !e.includes('vite')), []))

  console.log(`PASS forecast-plane browser acceptance (${results.filter(r => r.pass).length}/${results.length})`)
  await livePage.close()
} finally {
  await browser.close()
  vite.kill()
}
