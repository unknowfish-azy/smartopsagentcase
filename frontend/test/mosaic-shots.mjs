import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
const base = 'http://127.0.0.1:5173'
const out = 'test-artifacts/mosaic'
mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true, args: ['--no-proxy-server', '--proxy-bypass-list=*'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.route(url => new URL(url).pathname.startsWith('/api/'), route => {
  const p = new URL(route.request().url()).pathname
  if (p === '/api/auth/session') return route.fulfill({ json: { code: 200, data: { user: { id: 7, username: 'shot', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'x' } } })
  return route.fulfill({ json: { code: 200, data: [] } })
})
await page.goto(`${base}/knowledge/space`, { waitUntil: 'load' })
await page.waitForSelector('.mw-tile', { timeout: 20000 })
await page.waitForTimeout(600)
await page.screenshot({ path: `${out}/01-mosaic-dark-s0.png` })
// 切浅色主题
await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'))
await page.waitForTimeout(400)
await page.screenshot({ path: `${out}/02-mosaic-light-s0.png` })
// 放大一档看细节（S2）
await page.evaluate(() => document.documentElement.removeAttribute('data-theme'))
await page.mouse.move(720, 450); await page.mouse.wheel(0, -900); await page.waitForTimeout(400)
await page.screenshot({ path: `${out}/03-mosaic-dark-s2.png` })
console.log('screenshots saved to', out)
await browser.close()
