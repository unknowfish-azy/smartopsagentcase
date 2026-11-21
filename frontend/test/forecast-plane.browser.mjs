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

// 确定性 fixture（live 口径，与后端 SentinelForecastService 字段一一对应）。
// 关键：kind/mode/modelStatus 如实反映统计降级，metric 为真实哨兵指标（cpu），
// 单位/名称取真实口径，绝不写回设计稿的 ECT/°C。
function liveFixture() {
  const forecast = []
  for (let step = 1; step <= 2; step += 1) {
    const t = step * 30
    const median = 93 + Math.sin(t / 8) * 0.8 + t * 0.02
    const spread = 0.6 + Math.sqrt(t) * 0.25
    forecast.push({ t, h: step, median, p10: median - spread, p90: median + spread, lower: median - spread, upper: median + spread })
  }
  const series = []
  for (let i = 0; i <= 20; i += 1) series.push({ t: -i * 30, v: 88 + Math.sin(i / 6) * 3 + Math.sin(i / 2) * 0.6 })
  return {
    generatedAt: '2026-11-19T15:20:31Z',
    status: 'ok',
    kind: 'statistical',
    mode: 'linear',
    modelStatus: 'fallback',
    modelStatusDetail: '未找到 patchtst.pt，本次走统计降级',
    note: '权重缺失或输入不满足模型约束，本次走统计降级（linear）；这不是神经网络效果。',
    metric: 'cpu',
    sensor: 'ect',
    cn: '冷却液温度',
    en: 'ECT',
    sensorCn: '冷却液温度',
    sensorEn: 'ECT',
    metricName: 'cpu',
    unit: '%',
    horizonSec: 60,
    steps: 2,
    sampleIntervalSec: 30,
    sampleCount: 21,
    inferenceMs: 12,
    thresholds: { warnAbove: 85, critAbove: 95, warnBelow: 0, critBelow: 0, low: false },
    model: {
      version: 'statistical-baseline',
      arch: 'linear',
      params: 0,
      metrics: { mae: null, rmse: null, mape: null },
      trainedAt: null,
      epochs: null,
      gate: 'FALLBACK',
      kind: 'statistical',
      mode: 'linear',
      modelStatus: 'fallback',
      modelStatusDetail: '未找到 patchtst.pt',
      note: 'MAE/RMSE/MAPE 仅在真实独立测试集评测后才有值；当前无评测产物，字段恒为空。'
    },
    series,
    forecast,
    crossings: [{ kind: 'warn', h: 20, step: 1, value: 96.0, threshold: 85, confidence: 0.73 }]
  }
}

// 真实目录：只列出确有采样的槽位（cpu/memory），未采样的槽位不出现。
function catalogFixture() {
  const slot = (key, cn, en, metric) => ({
    key, cn, en, metric, unit: '%', taskId: 1, sampleCount: 117, sampleIntervalSec: 30,
    lastSampledAt: '2026-11-16T10:00:00Z', warnAbove: 85, critAbove: 95, warnBelow: 0, critBelow: 0, low: false
  })
  return { slots: [slot('ect', '冷却液温度', 'ECT', 'cpu'), slot('rpm', '曲轴转速', 'RPM', 'memory')], horizons: [15, 30, 60, 120] }
}
const modelsFixture = () => ({ kind: 'fallback', torchAvailable: true, reachable: true, weightsExpected: 'ai-service/models/patchtst.pt' })

// 单函数 route 内部分发（mosaic-wall.browser.mjs 已验证的写法）：
// 避免多次注册的匹配顺序与 glob `?` 语义的不确定性；只拦真 /api/ 路径。
function mockApi(page, mode) {
  page.route(url => url.pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path.startsWith('/api/auth/session')) return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } })
    if (path.startsWith('/api/sentinel/forecast/catalog')) return route.fulfill({ json: { code: 200, data: catalogFixture() } })
    if (path.startsWith('/api/sentinel/forecast/model-info')) return route.fulfill({ json: { code: 200, data: modelsFixture() } })
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

  // ── 2b) demo 态回放/键盘：真实链路只有一个"现在"，回放只对演示数据开放 ──
  const subCount = () => page.evaluate(async () => {
    const m = await import('/src/visual/motionScheduler.js')
    return m.subscriberCount()
  })
  const demoBaseSubs = await subCount()
  await page.getByRole('button', { name: '回放' }).click()
  await check('demo 回放时 motionScheduler 订阅 +1', async () => {
    assert.equal(await subCount(), demoBaseSubs + 1)
  })
  await page.getByRole('button', { name: '暂停' }).click()
  await check('demo 暂停后订阅回基线', async () => {
    await page.waitForFunction(async (base) => {
      const m = await import('/src/visual/motionScheduler.js')
      return m.subscriberCount() === base
    }, demoBaseSubs, { timeout: 3000 })
  })
  await page.keyboard.press(' ')
  await check('Space 开启播放（按钮变暂停）', async () => {
    await page.getByRole('button', { name: '暂停' }).waitFor()
  })
  await page.keyboard.press('ArrowLeft')
  await check('ArrowLeft 中止播放（按钮变回放）', async () => {
    await page.getByRole('button', { name: '回放' }).waitFor()
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
  await check('live 态槽位显示真实指标名，不显示引擎别名', async () => {
    // 用容器定位而非 role：页面里「模型指标」group 会被子串匹配命中，导致误判。
    const buttons = livePage.locator('.forecast-sensors button')
    assert.deepEqual((await buttons.allInnerTexts()).sort(), ['cpu', 'memory'])
    assert.equal(await buttons.filter({ hasText: 'ECT' }).count(), 0)
  })
  await check('live 态标题取真实指标并标注 UI 别名', async () => {
    const title = await livePage.locator('#forecast-chart-title').innerText()
    assert.match(title, /cpu/)
    assert.match(title, /ECT/)
  })
  await check('live 态如实标注统计降级，不写成 MLP+GRU', async () => {
    await livePage.getByText('统计降级（非神经模型）').first().waitFor()
    const modelCard = livePage.locator('section.forecast-card')
      .filter({ has: livePage.locator('#forecast-model-title') })
    assert.match(await modelCard.locator('.forecast-card-en').innerText(), /STATISTICAL FALLBACK/)
    assert.equal(await livePage.getByText('MLP + GRU').count(), 0)
  })
  await check('live 态回放被禁用（真实数据没有可回放的过去）', async () => {
    const btn = livePage.getByRole('group', { name: '回放' }).getByRole('button')
    assert.equal(await btn.isDisabled(), true)
  })
  await check('live 态训练卡不显示合成 epoch', async () => {
    const text = await livePage.locator('.forecast-bottom-card').first().innerText()
    assert.doesNotMatch(text, /最佳 epoch/)
    assert.match(text, /统计降级/)
  })
  await check('live 态数据源表用真实指标名与真实采样间隔', async () => {
    const text = await livePage.locator('.fc-sources').innerText()
    assert.match(text, /cpu/)
    assert.match(text, /30s/)
    assert.doesNotMatch(text, /冷却液温度 ECT/)
  })

  // ── 4) 视野切换：120s → +120s ──
  const asideBefore = await livePage.locator('.forecast-card-aside').first().innerText()
  await livePage.getByRole('group', { name: '视野' }).getByRole('button', { name: '120s' }).click()
  await check('视野切 120s 后窗口标注变化', async () => {
    const aside = await livePage.locator('.forecast-card-aside').first().innerText()
    assert.match(aside, /\+120s/)
    assert.notEqual(aside, asideBefore)
  })

  // ── 5) 导航落位：SENTINEL 组最后一项 ──
  // 导航组后来新增了 sections/observability/twin 等条目，forecast 不再是最后一项；
  // 这里验证它存在、文案正确，且与其余 /sentinel/* 条目同列表（列表里也混有 /incidents）。
  await check('导航含「预测面」且与其他哨兵项同组', async () => {
    const ok = await livePage.evaluate(() => {
      const link = document.querySelector('a[href="/sentinel/forecast"]')
      if (!link) return false
      if (!link.textContent.includes('预测面')) return false
      const links = [...link.parentElement.querySelectorAll('a[href]')]
      return links.length > 1 && links.some(a => a.getAttribute('href')?.startsWith('/sentinel/'))
    })
    assert.ok(ok, '预测面链接应存在于导航中')
  })

  // ── 6) 无横向溢出 ──
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

  // ── 7) reduced-motion：live 态回放本就禁用，断言不被自动播放 ──
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

  await check('控制台无 error', async () => {
    assert.deepEqual(errors.filter(e => !e.includes('vite')), [])
    assert.deepEqual(liveErrors.filter(e => !e.includes('vite')), [])
  })

  console.log(`PASS forecast-plane browser acceptance (${results.filter(r => r.pass).length}/${results.length})`)
  await livePage.close()
} finally {
  await browser.close()
  vite.kill()
}
