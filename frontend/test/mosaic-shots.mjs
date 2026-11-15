// 照片墙（mosaic）答辩截图包 — 产出 5 张关键帧进 test-artifacts/mosaic/，供答辩合订本配图。
// 绕过登录墙（单函数 route mock /api/*，auth 特判），复用已验证的 --no-proxy-server 代理绕行。
// 浅色主题必须在页面初始化前写入 localStorage.smartops_theme，否则会被 theme.js 覆盖回深色。
// 用法：dev server 已在 5173 运行 → node test/mosaic-shots.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const out = 'test-artifacts/mosaic'
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server', '--proxy-bypass-list=*'] })

async function newMosaicPage(light) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' })
  if (light) await page.addInitScript(() => { try { localStorage.setItem('smartops_theme', 'light') } catch {} })
  await page.route(url => new URL(url).pathname.startsWith('/api/'), route => {
    const p = new URL(route.request().url()).pathname
    if (p === '/api/auth/session') return route.fulfill({ json: { code: 200, data: { user: { id: 7, username: 'shot', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'x' } } })
    return route.fulfill({ json: { code: 200, data: [] } })
  })
  await page.goto(`${base}/knowledge/space`, { waitUntil: 'load' })
  await page.waitForSelector('.mw-tile', { timeout: 20000 })
  await page.waitForTimeout(600)
  return page
}

// 深色页：s0 总览 / s2 放大 / 详情窗 / 搜索浮层
const dark = await newMosaicPage(false)
await dark.screenshot({ path: `${out}/01-mosaic-dark-s0.png` })
await dark.mouse.move(720, 450); await dark.mouse.wheel(0, -900); await dark.waitForTimeout(500)
await dark.screenshot({ path: `${out}/03-mosaic-dark-s2.png` })
const clickPt = await dark.evaluate(() => {
  const stage = document.querySelector('.mw-stage'); if (!stage) return null
  const sr = stage.getBoundingClientRect()
  for (const t of document.querySelectorAll('.mw-tile')) {
    const r = t.getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height / 2
    if (cx > sr.left + 20 && cx < sr.right - 20 && cy > sr.top + 20 && cy < sr.bottom - 20) return { x: cx, y: cy }
  }
  return null
})
if (clickPt) { await dark.mouse.click(clickPt.x, clickPt.y); await dark.waitForSelector('.mw-pop', { timeout: 5000 }); await dark.waitForTimeout(300) }
await dark.screenshot({ path: `${out}/04-mosaic-popover.png` })
await dark.keyboard.press('Escape'); await dark.waitForTimeout(150)
await dark.keyboard.press('Control+k'); await dark.waitForSelector('.fs-input', { timeout: 5000 }); await dark.waitForTimeout(300)
await dark.screenshot({ path: `${out}/05-mosaic-search.png` })
await dark.close()

// 浅色页：s0 总览（初始化前写入 localStorage 走浅色）
const light = await newMosaicPage(true)
await light.screenshot({ path: `${out}/02-mosaic-light-s0.png` })
await light.close()

console.log('screenshots saved to', out)
await browser.close()
