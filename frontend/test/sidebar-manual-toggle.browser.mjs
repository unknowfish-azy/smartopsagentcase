import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'sidebar-test' }))
    localStorage.setItem('smartops_sidebar_collapsed', JSON.stringify(false))
  })
  // 自带头尾 mock，不依赖真实后端或手工登录态
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/session') return route.fulfill({ json: { code: 200, data: { user: { id: 7, username: 'sidebar-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'sidebar-test-csrf' } } })
    return route.fulfill({ json: { code: 200, data: [] } })
  })
  await page.goto(`${base}/`, { waitUntil: 'networkidle' })

  const sidebar = page.locator('.sidebar')
  const collapse = page.getByRole('button', { name: '收起主菜单', exact: true })
  const expand = page.getByRole('button', { name: '展开主菜单', exact: true })

  // 展开态只出现「收起主菜单」这一个按钮；尺寸必须受控，不能退回 SVG 默认 300x150
  assert.equal(await collapse.isVisible(), true)
  assert.equal(await expand.count(), 0)
  const box = await collapse.boundingBox()
  assert.ok(box && box.width <= 40 && box.height <= 40, `toggle too large: ${box?.width}x${box?.height}`)
  assert.ok(['sticky', 'fixed'].includes(await collapse.evaluate(node => getComputedStyle(node).position)))

  // 长菜单滚到底，切换按钮仍停在原视口位置（旧版要滚回顶部才能收起）
  const topBefore = box.y
  await sidebar.evaluate(node => { node.scrollTop = node.scrollHeight })
  await page.waitForTimeout(80)
  assert.equal((await collapse.boundingBox())?.y, topBefore)

  const expandedWidth = (await sidebar.boundingBox())?.width
  assert.ok(expandedWidth >= 240, `expected expanded sidebar, got ${expandedWidth}`)

  await collapse.click()
  await page.waitForTimeout(250)

  const collapsedWidth = (await sidebar.boundingBox())?.width
  assert.ok(collapsedWidth <= 90, `expected collapsed sidebar, got ${collapsedWidth}`)
  assert.equal(await sidebar.evaluate(node => node.classList.contains('sidebar--expanded')), false)
  assert.equal(await collapse.count(), 0)
  assert.equal(await expand.isVisible(), true)

  await expand.click()
  await page.waitForTimeout(250)

  const reopenedWidth = (await sidebar.boundingBox())?.width
  assert.ok(reopenedWidth >= 240, `expected reopened sidebar, got ${reopenedWidth}`)
  assert.equal(await collapse.isVisible(), true)
} finally {
  await browser.close()
}
