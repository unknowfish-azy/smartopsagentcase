// 菜单健康徽章 + 收起态子菜单浮出 的浏览器回归验证。
// 运行前提：dev server（默认 http://127.0.0.1:5173）在线；playwright + msedge 可用。
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts', { recursive: true })

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))

  await page.addInitScript(() => {
    localStorage.setItem('smartops_theme', 'dark')
    localStorage.setItem('smartops_visual_mode', 'lightweight')
    localStorage.setItem('smartops_sidebar_collapsed', 'true')
  })
  // 与既有浏览器测试一致：glob `**/api/**` 会误伤 src/api/*.js 源码模块，
  // 必须按 pathname 前缀放行非 API 请求（route.continue）。
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/session') {
      return route.fulfill({ json: { code: 200, data: { user: { id: 7, username: 'menu-verify', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'menu-verify-csrf' } } })
    }
    await route.fulfill({ json: { code: 200, data: [] } })
  })

  await page.goto(`${base}/`, { waitUntil: 'networkidle' })
  const nav = page.locator('.personal-system-navigation')
  await nav.waitFor({ state: 'visible' })

  // 1) 收起态：SENTINEL 与 HEALTH 两个分组带健康徽章，且徽章在图标轨上可见
  const badges = page.locator('.nav-health-badge-slot')
  assert.ok(await badges.count() >= 2, `expected sentinel+health badges in rail, got ${await badges.count()}`)
  await page.screenshot({ path: 'test-artifacts/menu-rail-badges.png' })

  // 2) 悬停 SENTINEL 分组唤出子菜单浮层，包含 3 个子页
  const sentinelRow = page.locator('.navigation-group', { has: page.locator('a[title*="哨兵"]') }).first()
  await sentinelRow.hover()
  const flyout = page.locator('.navigation-flyout')
  await flyout.waitFor({ state: 'visible' })
  assert.equal(await flyout.locator('a').count(), 3)
  await page.screenshot({ path: 'test-artifacts/menu-rail-flyout.png' })

  // 3) 浮层内跳转可达子页面
  await flyout.getByText('告警中心').click()
  await page.waitForURL('**/sentinel/alerts')
  await page.waitForTimeout(300)
  assert.equal(await page.locator('.navigation-flyout').count(), 0, 'flyout must close after navigation')

  // 4) 展开侧栏（点左上角展开钮）后徽章仍在（贴链接右下角），浮层不再出现
  await page.click('.sidebar-expand-control')
  await page.waitForTimeout(400)
  assert.ok(await page.locator('.nav-health-badge-slot').count() >= 2)
  await sentinelRow.hover()
  await page.waitForTimeout(250)
  assert.equal(await page.locator('.navigation-flyout').count(), 0, 'flyout is desktop-rail only')
  await page.screenshot({ path: 'test-artifacts/menu-expanded-badges.png' })

  assert.deepEqual(errors, [], `page errors: ${errors.join(' | ')}`)
  console.log('menu health badge + rail flyout: OK')
} finally {
  await browser.close()
}
