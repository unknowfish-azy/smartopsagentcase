import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const baseUrl = process.env.SMARTOPS_VISUAL_BASE_URL || 'http://127.0.0.1:5173'
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const viewports = [375, 768, 1024, 1440, 1920]
const browser = await chromium.launch({ executablePath: edgePath, headless: true })
await mkdir('test-artifacts', { recursive: true })

try {
  for (const width of viewports) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
    assert.equal(await page.locator('.login-shell').count(), 1)
    const loginTitle = page.locator('.login-copy h1')
    assert.equal(await loginTitle.innerText(), '智驭系统\n维系上下文')
    assert.notEqual(await loginTitle.evaluate((element) => getComputedStyle(element).fontFamily), '')
    // 登录页背景动效按 T11 性能基线在 <1024 视口整层不挂载（LoginView isMobile），
    // 因此 canvas 只在桌面视口存在；窄屏改为校验静态封面图，避免把设计上的零动效误判成渲染失败。
    if (width >= 1024) {
      await page.waitForFunction(() => document.querySelectorAll('canvas.canvas-ambient-field').length > 0, null, { timeout: 5000 })
      assert.equal(await page.locator('canvas.canvas-ambient-field').count(), 1)
    } else {
      assert.equal(await page.locator('canvas').count(), 0)
      assert.equal(await page.locator('.login-cover-image').count(), 1)
    }
    await page.screenshot({ path: `test-artifacts/login-${width}.png`, fullPage: true })
    // 首页会并发拉取 servers / inspector / sentinel 等业务数据；未 mock 时 401 会被前端判为会话失效
    // 并踢回登录页（smartops:unauthorized），导致仪表盘永远渲染不出来。先铺一层空数据兜底，
    // 再由下一条更精确的 session 路由覆盖鉴权应答。
    await page.route(url => url.pathname.startsWith('/api/'), (route) => route.fulfill({ json: { code: 200, data: null } }))
    await page.route('**/api/auth/session', (route) => route.fulfill({ json: {
      code: 200,
      data: { user: { id: 1, username: 'visual-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'visual-csrf' }
    } }))
    await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'visual-test' })))
    await page.goto(baseUrl, { waitUntil: 'networkidle' })
    assert.equal(await page.locator('.bento-dashboard').count(), 1)
    assert.ok(await page.locator('canvas').count() >= 1)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    await page.screenshot({ path: `test-artifacts/home-${width}.png`, fullPage: true })
    await page.close()
  }
  const reduced = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await reduced.emulateMedia({ reducedMotion: 'reduce' })
  await reduced.route(url => url.pathname.startsWith('/api/'), (route) => route.fulfill({ json: { code: 200, data: null } }))
  await reduced.route('**/api/auth/session', (route) => route.fulfill({ json: {
    code: 200,
    data: { user: { id: 1, username: 'visual-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'visual-csrf' }
  } }))
  await reduced.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'visual-test' })))
  await reduced.goto(baseUrl, { waitUntil: 'networkidle' })
  assert.equal(await reduced.locator('.bento-dashboard').count(), 1)
  // 减少动态档下首页不产生任何 canvas（背景动效与图表都走静态降级，且空数据下图表不挂载），
  // 这里改为校验「仍能完整渲染 + 无横向溢出」，与上方各视口的可读性契约保持一致。
  assert.equal(await reduced.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  await reduced.screenshot({ path: 'test-artifacts/home-reduced-motion.png', fullPage: true })
  await reduced.close()
} finally {
  await browser.close()
}
