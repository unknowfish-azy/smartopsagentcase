import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const base = process.env.PERSONAL_NAV_BASE_URL || 'http://127.0.0.1:5174'
await mkdir('test-artifacts/sidebar-repair', { recursive: true })
try {
  for (const width of [1440, 900, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', error => {
      // The local backend may be offline; keep layout failures distinct.
      if (error.message === '无法连接服务器，请检查后端服务是否启动') console.log('Backend offline during tools check')
      else errors.push(error.message)
    })
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'layout-check' }))
      localStorage.setItem('smartops_theme', 'dark')
    })
    for (const route of ['/', '/knowledge', '/agent', '/tools/processes']) {
      await page.goto(`${base}${route}`, { waitUntil: 'networkidle' })
      const metrics = await page.evaluate(() => {
        const layout = document.querySelector('.app-layout')
        const main = document.querySelector('.main-area')
        const content = document.querySelector('#main-content')
        return { layout: layout.getBoundingClientRect().toJSON(), main: main.getBoundingClientRect().toJSON(), display: getComputedStyle(layout).display, text: content.innerText.length }
      })
      console.log(JSON.stringify({ width, route, ...metrics }))
      assert.notEqual(metrics.display, 'none', 'Application must remain visible')
      assert.ok(metrics.layout.width >= width - 1, 'Application must fill viewport')
      assert.ok(metrics.main.width >= width * (route.startsWith('/tools') ? .65 : .8), 'Main content must retain usable width')
      assert.ok(metrics.main.x >= 0 && metrics.main.right <= width + 1, 'Content must stay inside viewport')
      assert.ok(metrics.text > 40, 'Main content must remain populated')
      await page.screenshot({ path: `test-artifacts/sidebar-repair/${width}-${route.replaceAll('/', '_') || 'home'}.png` })
      if (width >= 768 && !route.startsWith('/tools')) {
        const sidebar = page.locator('.sidebar')
        assert.equal(Math.round((await sidebar.boundingBox()).width), 72)
        await sidebar.hover()
        await page.waitForTimeout(250)
        assert.equal(Math.round((await sidebar.boundingBox()).width), 252)
        assert.equal(await page.locator('.personal-system-navigation .nav-copy').first().isVisible(), true)
        assert.equal((await page.locator('.main-area').boundingBox()).width, metrics.main.width)
        await page.mouse.move(width - 10, 450)
        await page.waitForTimeout(250)
        assert.equal(Math.round((await sidebar.boundingBox()).width), 72)
        await page.locator('.navigation-group__link').first().focus()
        await page.waitForTimeout(250)
        assert.equal(Math.round((await sidebar.boundingBox()).width), 252)
        await page.locator('#main-content').focus()
      }
    }
    if (width < 768) {
      await page.goto(`${base}/agent`, { waitUntil: 'networkidle' })
      await page.locator('.menu-button').click()
      const traceLink = page.locator('#personal-nav-agent a[href="/agent/trace"]')
      await traceLink.click()
      await page.waitForURL('**/agent/trace')
      assert.equal(await page.locator('.menu-button').getAttribute('aria-expanded'), 'false')
    }
    assert.deepEqual(errors, [])
    await page.close()
  }
} finally { await browser.close() }
