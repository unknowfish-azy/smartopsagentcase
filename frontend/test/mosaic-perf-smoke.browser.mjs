// 照片墙性能烟雾（T27 §6.5 补充）：真实 Edge 上测 /knowledge/space（mosaic，737 DOM 格）的
// FCP/LCP、首屏可见耗时、掉帧与堆内存。复用已验证的登录墙绕过手法（单函数 route mock /api/*，
// auth 特判返回 operator）。本环境浏览器需 --no-proxy-server，否则 127.0.0.1 被代理拦截成 JSON。
import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { spawn } from 'node:child_process'

const root = process.cwd().replace(/\\frontend$/, '')
const externalBase = process.env.SMARTOPS_BROWSER_BASE_URL
const base = externalBase || `http://127.0.0.1:${4510 + Math.floor(Math.random() * 60)}`

let vite = null
if (!externalBase) {
  const port = Number(base.split(':').pop())
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: `${root}\\frontend`,
    stdio: 'ignore'
  })
  let ready = false
  for (let i = 0; i < 150; i++) {
    try { const r = await fetch(base); if (r.ok) { ready = true; break } } catch {}
    await new Promise(res => setTimeout(res, 100))
  }
  if (!ready) { console.error('vite 未在预期时间内就绪'); process.exitCode = 1; vite.kill(); }
}

const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server', '--proxy-bypass-list=*'] })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  const errors = []
  page.on('pageerror', e => errors.push('pageerror: ' + String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()) })
  // 登录墙绕过：单函数 route，/api/auth/session 特判返回 operator，其余 /api/* 返回空（不含 /src/ 源码模块）
  await page.route(url => new URL(url).pathname.startsWith('/api/'), route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/session') {
      return route.fulfill({ json: { code: 200, data: { user: { id: 7, username: 'mosaic-perf', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'c' } } })
    }
    return route.fulfill({ json: { code: 200, data: [] } })
  })
  // 掉帧采样：相邻 rAF 间隔 > 50ms 计一次掉帧
  await page.addInitScript(() => {
    window.__frames = { total: 0, slow: 0, maxGap: 0 }
    let prev = performance.now()
    const tick = now => { const gap = now - prev; prev = now; window.__frames.total++; if (gap > 50) window.__frames.slow++; if (gap > window.__frames.maxGap) window.__frames.maxGap = Number(gap.toFixed(1)); requestAnimationFrame(tick) }
    requestAnimationFrame(tick)
  })

  const started = Date.now()
  await page.goto(`${base}/knowledge/space`, { waitUntil: 'load' })
  await page.waitForSelector('.mw-tile', { timeout: 20000 })
  const visibleMs = Date.now() - started
  // 浅色主题（延后设置，避免影响首屏 paint 采样）
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'))
  await page.waitForTimeout(150)

  const paint = await page.evaluate(() => new Promise(resolve => {
    const out = { fcp: 0, lcp: 0 }
    try {
      new PerformanceObserver(l => { for (const e of l.getEntries()) if (e.name === 'first-contentful-paint') out.fcp = e.startTime }).observe({ type: 'paint', buffered: true })
      new PerformanceObserver(l => { for (const e of l.getEntries()) out.lcp = e.startTime }).observe({ type: 'largest-contentful-paint', buffered: true })
    } catch {}
    setTimeout(() => resolve({ fcp: Number(out.fcp.toFixed(1)), lcp: Number(out.lcp.toFixed(1)) }), 1200)
  }))
  const tileCount = await page.locator('.mw-tile').count()
  const heapStart = await page.evaluate(() => performance.memory ? Number((performance.memory.usedJSHeapSize / 1048576).toFixed(2)) : null)
  // 交互：放大一档，触发 transform + LOD 切换，观察掉帧
  await page.mouse.move(720, 450); await page.mouse.wheel(0, -900)
  await page.waitForTimeout(400)
  const sizeNow = await page.locator('.mw-world').getAttribute('data-size')
  await page.waitForTimeout(1600)
  const frames = await page.evaluate(() => window.__frames)
  const heapEnd = await page.evaluate(() => performance.memory ? Number((performance.memory.usedJSHeapSize / 1048576).toFixed(2)) : null)

  const report = {
    task: 'mosaic-perf-smoke',
    viewport: '1440x1000',
    lightTheme: true,
    tileCount,
    dataSizeAfterZoom: sizeNow,
    fcpMs: paint.fcp,
    lcpMs: paint.lcp,
    firstTileVisibleMs: visibleMs,
    heapStartMb: heapStart,
    heapEndMb: heapEnd,
    heapGrowthMb: (heapStart !== null && heapEnd !== null) ? Number((heapEnd - heapStart).toFixed(2)) : null,
    frames: { total: frames.total, slow: frames.slow, slowPct: frames.total ? Number((100 * frames.slow / frames.total).toFixed(2)) : null, maxGapMs: frames.maxGap },
    pageErrors: errors
  }
  console.log(JSON.stringify(report, null, 2))
  const pass = errors.length === 0 && tileCount >= 700 && paint.fcp > 0 && paint.lcp > 0 && paint.lcp < 2500 && (frames.total === 0 || frames.slow / frames.total < 0.05)
  console.log(pass ? 'SMOKE_PASS' : 'SMOKE_FAIL')
  process.exitCode = pass ? 0 : 1
} finally {
  await browser.close()
  if (vite && !vite.killed) vite.kill()
}
