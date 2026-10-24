import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts', { recursive: true })

async function checkFrame(page, selector) {
  const frame = await page.locator(selector).evaluate(element => {
    const style = getComputedStyle(element, '::before')
    return { top: style.top, left: style.left, right: style.right, bottom: style.bottom, transform: style.transform, border: style.borderTopWidth, height: Number.parseFloat(style.height), parentHeight: element.clientHeight }
  })
  assert.equal(frame.top, '0px', `${selector}: decorative frame must start at the actual edge`)
  assert.equal(frame.left, '0px')
  assert.equal(frame.right, '0px')
  assert.equal(frame.bottom, '0px')
  assert.equal(frame.transform, 'none')
  assert.equal(frame.border, '0px', 'no duplicate black border inside the menu')
  assert.ok(Math.abs(frame.height - frame.parentHeight) <= 2, JSON.stringify(frame))
}

try {
  for (const width of [375, 900, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_theme', 'light')
      localStorage.setItem('smartops_visual_mode', 'lightweight')
      localStorage.setItem('smartops_sidebar_collapsed', 'false')
    })
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) return route.continue()
      const data = path === '/api/auth/session' ? { user: { id: 81, username: 'sidebar-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'mock-csrf' } : []
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.goto(`${base}/agent`, { waitUntil: 'networkidle' })
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      await checkFrame(page, '.sidebar')
      await checkFrame(page, '.topbar')
      if (width >= 768) {
        const sidebar = page.locator('.sidebar')
        assert.equal(Math.round((await sidebar.boundingBox()).width), 252)
        await page.screenshot({ path: `test-artifacts/sidebar-${theme}-${width}-expanded.png` })
        await page.getByRole('button', { name: '收起主菜单', exact: true }).click()
        assert.equal(Math.round((await sidebar.boundingBox()).width), 72)
        await checkFrame(page, '.sidebar')
        await page.screenshot({ path: `test-artifacts/sidebar-${theme}-${width}-collapsed.png` })
        await page.getByRole('button', { name: '展开主菜单', exact: true }).click()
        assert.equal(Math.round((await sidebar.boundingBox()).width), 252)
      } else {
        await page.getByRole('button', { name: '切换导航', exact: true }).click()
        const mobile = page.locator('.personal-system-navigation--mobile')
        assert.equal(await mobile.isVisible(), true)
        assert.ok((await mobile.boundingBox()).width >= width - 40, 'mobile menu must use the available sidebar width')
        assert.equal(await mobile.locator('.navigation-group__link .nav-icon').count(), await mobile.locator('.navigation-group__link').count(), 'each menu label keeps its icon column')
        const expectedSurface = await page.evaluate(() => {
          const probe = document.createElement('div')
          probe.style.backgroundColor = 'var(--smart-surface)'
          document.body.append(probe)
          const color = getComputedStyle(probe).backgroundColor
          probe.remove()
          return color
        })
        assert.equal(await mobile.evaluate(element => getComputedStyle(element).backgroundColor), expectedSurface)
        await page.screenshot({ path: `test-artifacts/sidebar-${theme}-${width}-mobile.png` })
        await page.getByRole('button', { name: '切换导航', exact: true }).click()
      }
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    }
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS ${width}px: both themes, sidebar/topbar frame geometry and menu states`)
  }
} finally {
  await browser.close()
}
