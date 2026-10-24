// 蜘蛛巡网动效浏览器回归（哨兵 CRAWLER 面板）。
// 覆盖：1440px 画布渲染与帧推进（DEV 钩子 __spiderCrawler）→ 像素随时间变化（真的在爬）→
//       面板语义与 aria → 375px 无横向溢出 → 降低动效静态帧（帧数不涨、像素稳定）。
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const server = await createServer({
  root: fileURLToPath(new URL('../', import.meta.url)),
  server: { host: '127.0.0.1', port: 5212, strictPort: true },
  logLevel: 'error'
})
await server.listen()
const base = 'http://127.0.0.1:5212'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/spider-crawler/', { recursive: true })

async function newSentinelPage({ reducedMotion = false, width = 1440 } = {}) {
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
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'crawler-check' }))
    localStorage.setItem('smartops_theme', 'dark')
  })
  await page.route('**/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204 })
    if (path === '/api/auth/session') {
      return route.fulfill({ json: { code: 200, data: { user: { id: 1, username: 'crawler-check', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'crawler-csrf' } } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })
  await page.goto(`${base}/sentinel`, { waitUntil: 'networkidle' })
  await page.locator('.crawler-stage canvas').waitFor()
  return { page, errors, vueWarnings }
}

const canvasShot = page => page.evaluate(() => document.querySelector('.crawler-stage canvas').toDataURL())

const paintedPixels = page => page.evaluate(() => {
  const canvas = document.querySelector('.crawler-stage canvas')
  const ctx = canvas.getContext('2d')
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height)
  let count = 0
  for (let i = 3; i < data.length; i += 4) if (data[i] > 8) count += 1
  return count
})

// 无头 rAF 可能只有 ~10fps：一律轮询等待，不写固定 sleep + 阈值
async function waitForFrames(page, minFrames, timeout = 15000) {
  await page.waitForFunction(min => {
    const state = window.__spiderCrawler?.()
    return state && state.frames >= min
  }, minFrames, { timeout, polling: 150 })
}

async function debugState(page) {
  return page.evaluate(() => window.__spiderCrawler?.() || null)
}

try {
  // ---- 流 1：1440px 桌面 —— 渲染、帧推进、真的在爬 ----
  {
    const { page, errors, vueWarnings } = await newSentinelPage()
    const initial = await debugState(page)
    assert.ok(initial && initial.segments >= 60, `web generated (${initial.segments} segments)`)
    await waitForFrames(page, initial.frames + 6)

    // 像素级证明：蜘蛛在动（间隔采样两次画布必须不同）
    const shotA = await canvasShot(page)
    await page.waitForFunction(prev => document.querySelector('.crawler-stage canvas').toDataURL() !== prev, shotA, { timeout: 8000, polling: 200 })
    const walking = await debugState(page)
    assert.ok(walking.frames > initial.frames, 'frames advancing')
    assert.ok(walking.bodyX > 0 && walking.bodyY > 0, 'spider body has a position')

    // 蜘蛛位置随时间推进（位置在网范围内变化）
    const posA = await debugState(page)
    await page.waitForFunction(() => true, null, { timeout: 600 }).catch(() => {})
    await page.waitForTimeout(900)
    const posB = await debugState(page)
    const drift = Math.hypot(posB.bodyX - posA.bodyX, posB.bodyY - posA.bodyY)
    assert.ok(drift > 4 || posB.segments === 0, `spider crawls (drift ${drift}px)`)

    // 语义与 aria：面板标题存在、画布不可交互
    assert.ok(await page.getByRole('heading', { name: /CRAWLER \/ 拓扑巡网/ }).isVisible())
    assert.equal(await page.locator('.spider-crawler').getAttribute('aria-hidden'), 'true')
    assert.ok(await paintedPixels(page) > 2000, 'web + spider painted')

    await page.screenshot({ path: 'test-artifacts/spider-crawler/sentinel-1440-dark.png', fullPage: false })
    await page.locator('.sentinel-crawler').screenshot({ path: 'test-artifacts/spider-crawler/crawler-panel-1440.png' })
    assert.deepEqual(errors, [])
    assert.deepEqual(vueWarnings, [])
    console.log('PASS 1440px sentinel crawler: web rendered, frames advancing, spider crawling, a11y (mock API)')
    await page.close()
  }

  // ---- 流 2：375px 移动 —— 无横向溢出 ----
  {
    const { page, errors } = await newSentinelPage({ width: 375 })
    await waitForFrames(page, 6)
    assert.ok(await paintedPixels(page) > 800, 'web painted on mobile')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    await page.locator('.sentinel-crawler').scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-artifacts/spider-crawler/crawler-panel-375.png' })
    assert.deepEqual(errors, [])
    console.log('PASS 375px sentinel crawler: scaled web, no overflow')
    await page.close()
  }

  // ---- 流 3：降低动效 —— 静态帧，帧数不涨 ----
  {
    const { page, errors } = await newSentinelPage({ reducedMotion: true })
    const state = await debugState(page)
    assert.equal(state.reducedMotion, true)
    assert.equal(state.frames, 1, 'exactly one static frame')
    await page.waitForTimeout(900)
    const still = await debugState(page)
    assert.equal(still.frames, 1, 'no loop under reduced motion')
    assert.equal(await canvasShot(page), await canvasShot(page), 'pixels stable under reduced motion')
    assert.ok(await paintedPixels(page) > 800, 'static web + spider still painted')
    assert.deepEqual(errors, [])
    console.log('PASS reduced motion: static web frame, no loop')
    await page.close()
  }
} finally {
  await browser.close()
  await server.close()
  console.log('DONE spider-crawler browser regression')
}
