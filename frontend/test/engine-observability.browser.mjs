// 引擎可观测大屏浏览器验收（T40）：路由可达、导航落位、live（含 STALLED/ERROR/NOT_RUN/NO_DATA/RUNNING）、
// 真实事件时间轴、事件明细、offline 空态且不 fallback demo、无横向溢出、0 pageError、轮询发生。
// 自带 API mock，不依赖后端。
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import { mkdir } from 'node:fs/promises'

const root = process.cwd().replace(/\\frontend$/, '')
const artifact = `${root}\\.runtime\\engine-observability\\browser`
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

function engine(id, name, status, ageSec, periodSec, count, detail) {
  return {
    id, name, status,
    lastEventAtEpochSec: status === 'NO_DATA' || status === 'NOT_RUN' ? null : Math.floor(Date.now() / 1000) - ageSec,
    lastEventAtText: status === 'NO_DATA' || status === 'NOT_RUN' ? '—' : '2026-11-16 14:00:00',
    ageSec, expectedPeriodSec: periodSec, eventCount: count,
    lastEventSummary: status === 'NOT_RUN' ? '—' : '真实事件摘要 fixture',
    detail
  }
}
function liveFixture() {
  return {
    generatedAt: Math.floor(Date.now() / 1000),
    engines: [
      engine('sentinel-poll', '哨兵巡检', 'RUNNING', 5, 30, 128, '运行中 · 距上次心跳 5s / 阈值 30s'),
      engine('sentinel-guardian', '守护 Agent', 'STALLED', 240, 60, 44, '疑似停摆 · 距上次 240s / 阈值 60s'),
      engine('web-research', '联网研究', 'ERROR', 10, 90, 31, '最近事件异常 · 距上次 10s（阈值 90s）'),
      engine('inspector', '纠察', 'NO_DATA', 0, 300, 0, '无数据 · 该引擎事件源暂无真实记录'),
      engine('decision-loop', '决策闭环', 'RUNNING', 120, 300, 17, '运行中 · 距上次心跳 120s / 阈值 300s'),
      engine('operation-run', '运维执行', 'RUNNING', 20, 300, 9, '运行中 · 距上次心跳 20s / 阈值 300s'),
      engine('training', '模型训练', 'NOT_RUN', 0, 0, 0, '未运行 · 无真实训练事件源')
    ]
  }
}
function eventFixture(engineId) {
  if (engineId === 'training' || engineId === 'inspector') return []
  const now = Math.floor(Date.now() / 1000)
  return [
    { at: now - 3, kind: 'SUCCESS', summary: '真实事件 · 最近' },
    { at: now - 30, kind: 'FIRED', summary: '真实事件 · 较早' }
  ]
}

let snapshotCalls = 0
function mockApi(page, mode) {
  page.route(url => url.pathname.startsWith('/api/'), route => {
    const u = new URL(route.request().url())
    const path = u.pathname
    if (path.startsWith('/api/auth/session')) return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 't', role: 'operator' }, csrfToken: 'csrf' } } })
    if (path.startsWith('/api/engine-observability/snapshot')) {
      snapshotCalls++
      return mode === 'offline'
        ? route.fulfill({ status: 503, json: { code: 503, message: 'telemetry unavailable' } })
        : route.fulfill({ json: { code: 200, data: liveFixture() } })
    }
    if (path.startsWith('/api/engine-observability/event-stream')) {
      const eng = u.searchParams.get('engine') || ''
      return route.fulfill({ json: { code: 200, data: { engine: eng, events: eventFixture(eng) } } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  page.setDefaultTimeout(10000)
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' })); localStorage.setItem('smartops_theme', 'dark') })

  // ── 1) offline 态：503 → 空态，绝不 fallback demo ──
  mockApi(page, 'offline')
  await page.goto(`${base}/sentinel/observability`, { waitUntil: 'networkidle' })
  await check('路由可达 .eo-shell', async () => { await page.locator('.eo-shell').waitFor() })
  await check('offline 态 data-state=offline', async () => {
    assert.equal(await page.locator('.eo-shell').getAttribute('data-state'), 'offline')
  })
  await check('offline 空态提示且无演示入口（不 fallback）', async () => {
    await page.getByText('后端遥测不可用').waitFor()
    assert.equal(await page.getByRole('button', { name: /演示/ }).count(), 0)
  })

  // ── 2) live 态：重新加载并给 live mock ──
  const page2 = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' })
  page2.on('pageerror', e => errors.push(e.message))
  await page2.addInitScript(() => { localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 't', role: 'operator' })); localStorage.setItem('smartops_theme', 'dark') })
  mockApi(page2, 'live')
  await page2.goto(`${base}/sentinel/observability`, { waitUntil: 'networkidle' })
  await check('live 态 data-state=live', async () => {
    assert.equal(await page2.locator('.eo-shell').getAttribute('data-state'), 'live')
  })
  await check('渲染 7 张引擎卡', async () => {
    assert.equal(await page2.locator('.eo-card').count(), 7)
  })
  await check('STALLED 卡显示可解释的超时文案', async () => {
    const txt = await page2.locator('.eo-card--stalled').first().innerText()
    assert.match(txt, /距上次 240s \/ 阈值 60s/)
    assert.match(txt, /疑似停摆/)
  })
  await check('ERROR 卡红色状态', async () => {
    assert.ok(await page2.locator('.eo-card--error').count() >= 1)
  })
  await check('training 卡为 NOT_RUN 灰卡且注明无事件源', async () => {
    const card = page2.locator('.eo-card--notrun')
    assert.equal(await card.count(), 1)
    const txt = await card.innerText()
    assert.match(txt, /未运行/)
    assert.match(txt, /无事件源/)
  })
  await check('真实事件时间轴渲染（有事件时不显示空态）', async () => {
    await page2.locator('.eo-timeline-canvas').waitFor()
    assert.equal(await page2.locator('.eo-timeline-empty').count(), 0)
  })
  await check('事件明细表渲染真实事件', async () => {
    assert.ok(await page2.locator('.eo-table tbody tr').count() >= 1)
  })
  await check('概览条统计正确', async () => {
    const summary = await page2.locator('.eo-summary').innerText()
    assert.match(summary, /运行中\s*3/)
    assert.match(summary, /疑似停摆\s*1/)
  })
  await check('无横向溢出', async () => {
    const overflow = await page2.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    assert.equal(overflow, false)
  })
  await check('快照端点被调用（轮询就绪）', async () => {
    assert.ok(snapshotCalls >= 1)
  })
  await check('0 pageError', async () => {
    assert.deepEqual(errors, [])
  })
  await page2.screenshot({ path: `${artifact}\\live.png`, fullPage: true })
  await page2.close()

  console.log(`\n[engine-observability] ${results.filter(r => r.pass).length}/${results.length} PASS`)
} catch (e) {
  console.error('\n[engine-observability] FAILED:', e.message)
  for (const r of results) console.error(`  ${r.pass ? '✓' : '✗'} ${r.name}${r.err ? ' — ' + r.err : ''}`)
  process.exitCode = 1
} finally {
  await browser.close()
  vite.kill('SIGTERM')
}
