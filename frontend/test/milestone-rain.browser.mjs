// 里程碑金币雨（「麻袋装钱」合规落地）浏览器回归。
// 覆盖：战报页真实数据推导 → 常驻袋静态帧 → 演示/庆祝触发播放 →
//       帧推进与袋口捕获（DEV 钩子 __milestoneRain）→ 播完像素稳定 →
//       ?preview=1 自动播放 → aria/指针属性 → 降低动效静态帧 →
//       持续动态演示（ambient 默认开）+ 暂停/恢复键位 →
//       双栏独立滚动（滚一栏另一栏与页面不动）+ 演示实例隔离 → 375px 流式回退无溢出。
// 注：需要「画布静止」断言的旧流程用 ?ambient=0 关闭持续动态， ambient 行为由独立流程覆盖。
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)),
  server: { host: '127.0.0.1', port: 5210, strictPort: true },
  logLevel: 'error'
})
await server.listen()
const base = 'http://127.0.0.1:5210'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/milestone-rain/', { recursive: true })

// 真实账本 mock：calls=1234（已达 100/500/1000 三档）、knownTokens=284100（已达 1万/10万 两档）、
// 成功率 97.2% + 1234 次（高稳定月达成）、pending=0（零待确认达成）、unknown=4（全量可计量未达成）
const report = {
  month: '2026-10',
  timezone: 'UTC',
  budget: 300000,
  budgetUsedTokens: 284100,
  budgetUnknownCalls: 4,
  summary: { calls: 1234, successes: 1200, failures: 30, pendingCalls: 0, unknownUsageCalls: 4, knownTokens: 284100, successRate: 97.2 },
  models: [{ connectionId: 1, modelName: 'ops-reasoner', calls: 1234, successes: 1200, failures: 30, pendingCalls: 0, unknownUsageCalls: 4, knownTokens: 284100, inputTokens: 180000, outputTokens: 104100, successRate: 97.2, averageLatencyMs: 980 }],
  daily: []
}

async function newHallPage({ reducedMotion = false, width = 1440, query = '' } = {}) {
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
    reducedMotion: reducedMotion ? 'reduce' : 'no-preference'
  })
  const page = await context.newPage()
  const errors = []
  const vueWarnings = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => {
    if (message.type() === 'warning' && /Unhandled error during execution/.test(message.text())) vueWarnings.push(message.text().slice(0, 120))
  })
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'milestone-check' }))
    localStorage.setItem('smartops_theme', 'dark')
  })
  await page.route('**/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204 })
    if (path === '/api/auth/session') {
      return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 'milestone-check', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'milestone-csrf' } } })
    }
    if (path.startsWith('/api/model-analytics')) return route.fulfill({ json: report })
    return route.fulfill({ json: { code: 200, data: [] } })
  })
  await page.goto(`${base}/milestones${query}`, { waitUntil: 'networkidle' })
  await page.locator('.vessel-stage canvas').waitFor()
  return { page, errors, vueWarnings }
}

const canvasShot = page => page.evaluate(() => document.querySelector('.vessel-stage canvas').toDataURL())

const paintedPixels = page => page.evaluate(() => {
  const canvas = document.querySelector('.vessel-stage canvas')
  const ctx = canvas.getContext('2d')
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
  let count = 0
  for (let i = 3; i < data.length; i += 4) if (data[i] > 8) count += 1
  return count
})

// 完成信号以状态文案为准：funnel 模式金币落袋后画面即静止（捕获态不积分），
// 像素稳定会早于动效正式结束（淡出阶段），不能用来判断播放完毕。
async function waitForStatus(page, text, timeout = 15000) {
  await page.waitForFunction(
    expected => document.querySelector('.rain-status')?.textContent?.includes(expected),
    text,
    { timeout, polling: 200 }
  )
}

async function assertCanvasRests(page) {
  const settled = await canvasShot(page)
  await page.waitForTimeout(300)
  assert.equal(settled, await canvasShot(page), 'canvas rests after celebration')
}

const debugState = page => page.evaluate(() => (window.__milestoneRain ? window.__milestoneRain() : null))

try {
  // ── 1440px · 允许动效 ──
  {
    const { page, errors, vueWarnings } = await newHallPage({ query: '?preview=1&ambient=0' })
    // 真实数据推导：7/11 达成（calls 三档 + tokens 两档 + 高稳定月 + 零待确认）
    assert.match(await page.locator('.hall-footer').innerText(), /已达成 7 \/ 11 项/)
    assert.match(await page.locator('.hall-footer').innerText(), /另含 3 项演示实例/)
    assert.match(await page.locator('.vessel-readout').innerText(), /本月已调用 1,234 次 · 下一档 5,000 次（25%）/)
    // 演示实例：3 张虚线卡 + 分隔带，与 11 张真实卡隔离，不挂庆祝按钮
    assert.equal(await page.locator('.achievement-card:not(.demo)').count(), 11)
    assert.equal(await page.locator('.achievement-card.demo').count(), 3)
    assert.match(await page.locator('.demo-divider').innerText(), /演示实例 · DEMO — 非真实账本数据/)
    assert.match(await page.locator('.achievement-card.demo').first().locator('.status-chip').innerText(), /演示/)
    assert.equal(await page.locator('.achievement-card.demo .celebrate-button').count(), 0)
    // 第一张卡 calls-100 已达成；第四张 calls-5000 是下一档（进行中）
    assert.match(await page.locator('.achievement-card').first().locator('.status-chip').innerText(), /已达成/)
    assert.match(await page.locator('.achievement-card').nth(3).locator('.status-chip').innerText(), /进行中/)
    assert.match(await page.locator('.achievement-card').nth(3).locator('.value-line').innerText(), /1,234/)

    // 常驻袋静态帧：袋身 + 25% 储量已绘制
    assert.ok(await paintedPixels(page) > 1500, 'vessel static frame painted')

    // ?preview=1：有真实达成项 → 自动播放一次。
    // 帧推进用轮询断言（无头环境 rAF  pacing 只有 ~10fps，固定睡眠会卡边界）
    assert.match(await page.locator('.rain-status').innerText(), /正在播放演示庆祝动效/)
    await page.waitForFunction(() => {
      const hook = window.__milestoneRain
      return hook ? hook().frames > 10 && hook().live > 0 : false
    }, null, { timeout: 10000, polling: 100 })
    const mid = await debugState(page)
    assert.ok(mid.frames > 10, 'animation frames advancing')
    assert.ok(mid.live > 0, 'coins alive mid-flight')
    await page.screenshot({ path: 'test-artifacts/milestone-rain/rain-1440-mid.png' })
    await waitForStatus(page, '播放完毕')
    await assertCanvasRests(page)
    assert.ok((await paintedPixels(page)) > 1500, 'vessel survives after celebration')

    // 手动庆祝：点击已达成卡的「庆祝一下」，金币应被捕获进袋
    await page.locator('.achievement-card').first().locator('.celebrate-button').click()
    assert.match(await page.locator('.rain-status').innerText(), /正在庆祝：本月累计调用 · 100/)
    await page.waitForFunction(() => (window.__milestoneRain ? window.__milestoneRain().captured > 0 : false), null, { timeout: 10000, polling: 100 })
    const capturing = await debugState(page)
    assert.ok(capturing.captured > 0, 'coins captured into the vessel')
    await page.screenshot({ path: 'test-artifacts/milestone-rain/rain-1440-capture.png' })
    await waitForStatus(page, '播放完毕')
    await assertCanvasRests(page)
    assert.match(await page.locator('.rain-status').innerText(), /播放完毕/)

    // a11y 与指针契约
    assert.equal(await page.locator('.milestone-rain').getAttribute('aria-hidden'), 'true')
    assert.equal(await page.locator('.milestone-rain').evaluate(node => getComputedStyle(node).pointerEvents), 'none')

    // 播放前后画布必须在动（像素级证明；轮询等下一帧，不赌固定帧率）
    await page.getByRole('button', { name: /演示庆祝动效/ }).click()
    const shotA = await canvasShot(page)
    await page.waitForFunction(prev => {
      const canvas = document.querySelector('.vessel-stage canvas')
      return canvas ? canvas.toDataURL() !== prev : false
    }, shotA, { timeout: 8000, polling: 120 })
    await waitForStatus(page, '播放完毕')
    await assertCanvasRests(page)

    // 双栏独立滚动：滚右栏 → 右栏动、页面与左栏不动；滚左栏 → 左栏动、右栏不动
    const panes = await page.evaluate(() => ({
      listOverflow: getComputedStyle(document.querySelector('.achievement-list')).overflowY,
      vesselOverflow: getComputedStyle(document.querySelector('.vessel-panel')).overflowY,
      pageLocked: document.body.scrollHeight <= window.innerHeight + 1
    }))
    assert.equal(panes.listOverflow, 'auto', 'right pane is its own scroll container')
    assert.equal(panes.vesselOverflow, 'auto', 'left pane is its own scroll container')
    assert.equal(panes.pageLocked, true, 'page itself is viewport-locked, not scrolling')

    const listBox = await page.locator('.achievement-list').boundingBox()
    await page.mouse.move(listBox.x + listBox.width / 2, listBox.y + 40)
    await page.mouse.wheel(0, 400)
    await page.waitForTimeout(250)
    const afterRight = await page.evaluate(() => ({
      list: document.querySelector('.achievement-list').scrollTop,
      vessel: document.querySelector('.vessel-panel').scrollTop,
      page: document.scrollingElement.scrollTop
    }))
    assert.ok(afterRight.list > 0, 'right pane scrolls independently')
    assert.equal(afterRight.vessel, 0, 'left pane unaffected by right-pane scroll')
    assert.equal(afterRight.page, 0, 'page itself does not scroll')

    const listBefore = afterRight.list
    const vesselBox = await page.locator('.vessel-panel').boundingBox()
    await page.mouse.move(vesselBox.x + vesselBox.width / 2, vesselBox.y + 40)
    await page.mouse.wheel(0, 150)
    await page.waitForTimeout(250)
    const afterLeft = await page.evaluate(() => ({
      list: document.querySelector('.achievement-list').scrollTop,
      vessel: document.querySelector('.vessel-panel').scrollTop,
      page: document.scrollingElement.scrollTop
    }))
    assert.ok(afterLeft.vessel > 0, 'left pane scrolls independently')
    assert.equal(afterLeft.list, listBefore, 'right pane unaffected by left-pane scroll')
    assert.equal(afterLeft.page, 0, 'page itself does not scroll')
    await page.screenshot({ path: 'test-artifacts/milestone-rain/hall-1440-ladder.png' })

    // 右栏滚到底：演示实例卡完整可见
    await page.locator('.achievement-list').evaluate(el => { el.scrollTop = el.scrollHeight })
    await page.waitForTimeout(200)
    await page.screenshot({ path: 'test-artifacts/milestone-rain/hall-1440-demo.png' })

    // 双栏复位后拍主图：初始状态（真实卡在右栏顶部、麻袋在左栏顶部）
    await page.evaluate(() => {
      document.querySelector('.achievement-list').scrollTop = 0
      document.querySelector('.vessel-panel').scrollTop = 0
    })
    await page.waitForTimeout(150)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: 'test-artifacts/milestone-rain/hall-1440-dark.png', fullPage: true })
    assert.deepEqual(errors, [])
    assert.deepEqual(vueWarnings, [])
    console.log('PASS 1440px milestone hall: real-ledger achievements, vessel fill, capture, stability, a11y (mock API)')
    await page.close()
  }

  // ── 持续动态演示：默认开、可暂停/恢复（动态持续化 + 键位） ──
  {
    const { page, errors } = await newHallPage()
    const initial = await debugState(page)
    assert.equal(initial.ambient, true, 'ambient demo on by default')
    // 待机帧推进（无任何交互）
    await page.waitForFunction(() => {
      const hook = window.__milestoneRain
      return hook ? hook().ambient && hook().frames > 8 : false
    }, null, { timeout: 10000, polling: 100 })
    // 像素随时间变化（真的在动）
    const shotA = await canvasShot(page)
    await page.waitForFunction(prev => {
      const canvas = document.querySelector('.vessel-stage canvas')
      return canvas ? canvas.toDataURL() !== prev : false
    }, shotA, { timeout: 8000, polling: 200 })
    await page.screenshot({ path: 'test-artifacts/milestone-rain/ambient-1440.png' })
    // 暂停：帧数冻结、像素稳定、aria-pressed 翻转、标签切换
    const pauseButton = page.getByRole('button', { name: /暂停动态演示/ })
    assert.equal(await pauseButton.getAttribute('aria-pressed'), 'true')
    await pauseButton.click()
    await page.waitForFunction(() => window.__milestoneRain && !window.__milestoneRain().ambient, null, { timeout: 5000, polling: 100 })
    const frozen = await debugState(page)
    const frozenShot = await canvasShot(page)
    await page.waitForTimeout(700)
    assert.equal((await debugState(page)).frames, frozen.frames, 'frames frozen while paused')
    assert.equal(frozenShot, await canvasShot(page), 'pixels stable while paused')
    const resumeButton = page.getByRole('button', { name: /恢复动态演示/ })
    assert.equal(await resumeButton.getAttribute('aria-pressed'), 'false')

    // 恢复：ambient 重启、帧继续推进
    await resumeButton.click()
    await page.waitForFunction(prev => {
      const hook = window.__milestoneRain
      return hook ? hook().ambient && hook().frames > prev : false
    }, frozen.frames, { timeout: 10000, polling: 100 })
    assert.deepEqual(errors, [])
    console.log('PASS ambient demo: continuous animation by default, pause/resume toggle works')
    await page.close()
  }

  // ── 375px 移动端 ──
  {
    const { page, errors } = await newHallPage({ width: 375, query: '?ambient=0' })
    assert.ok(await paintedPixels(page) > 800, 'vessel painted on mobile')
    // ≤1100px 流式回退：双栏堆叠、页面整体滚动，不做视口锁定
    const mobile = await page.evaluate(() => ({
      listOverflow: getComputedStyle(document.querySelector('.achievement-list')).overflowY,
      pageScrolls: document.body.scrollHeight > window.innerHeight
    }))
    assert.notEqual(mobile.listOverflow, 'auto', 'mobile falls back to page flow')
    assert.equal(mobile.pageScrolls, true, 'mobile page scrolls as a whole')
    await page.getByRole('button', { name: /演示庆祝动效/ }).click()
    await waitForStatus(page, '播放完毕')
    await assertCanvasRests(page)
    assert.match(await page.locator('.rain-status').innerText(), /播放完毕/)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: 'test-artifacts/milestone-rain/hall-375-dark.png', fullPage: true })
    assert.deepEqual(errors, [])
    console.log('PASS 375px milestone hall: scaled vessel, celebration, no overflow')
    await page.close()
  }

  // ── 降低动效：静态帧、不循环、状态可收敛 ──
  {
    const { page, errors } = await newHallPage({ reducedMotion: true })
    const before = await canvasShot(page)
    await page.waitForTimeout(350)
    assert.equal(before, await canvasShot(page), 'reduced motion draws a static frame')
    assert.ok(await paintedPixels(page) > 1500, 'reduced motion frame still painted')
    await page.getByRole('button', { name: /演示庆祝动效/ }).click()
    await page.waitForTimeout(600)
    assert.match(await page.locator('.rain-status').innerText(), /播放完毕/)
    const after = await canvasShot(page)
    await page.waitForTimeout(350)
    assert.equal(after, await canvasShot(page), 'reduced motion never starts a rAF loop')
    assert.deepEqual(errors, [])
    console.log('PASS reduced motion: static frame, no loop, status converges')
    await page.close()
  }
  // ── TokenUsage 入口芯片：真实达到档位才出现，可跳转战报 ──
  {
    const { page, errors } = await newHallPage()
    await page.goto(`${base}/token-usage`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: 'Token 用量与额度', exact: true }).waitFor()
    const chip = page.locator('.milestone-link')
    await chip.waitFor()
    assert.match(await chip.innerText(), /本月调用已达成 1,000 次里程碑/)
    await chip.click()
    await page.getByRole('heading', { name: '里程碑战报', exact: true }).waitFor()
    assert.equal(page.url(), `${base}/milestones`)
    assert.deepEqual(errors, [])
    console.log('PASS token-usage milestone chip: shown at 1,000 calls and links to the hall')
    await page.close()
  }
} finally {
  await browser.close()
  await server.close()
}
