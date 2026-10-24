import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/heartbeat', { recursive: true })
try {
  for (const theme of ['dark', 'light']) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(theme => {
      localStorage.setItem('smartops_theme', theme)
      localStorage.setItem('smartops_visual_mode', 'reduced-motion')
    }, theme)
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) return route.continue()
      let data = []
      if (path === '/api/auth/session') data = { user: { id: 7, username: 'heartbeat-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'fixture' }
      if (path === '/api/sentinel/tasks') data = [
        { id: 1, name: '测试数据 · 未采样', kind: 'system', target: 'cpu', intervalSec: 60, enabled: false },
        { id: 2, name: '测试数据 · 历史展示', kind: 'system', target: 'cpu', intervalSec: 60, enabled: false,
          heartbeats: Array.from({ length: 30 }, (_, index) => ({ status: ['up', 'down', 'degraded', 'maintenance', 'unknown'][index % 5], timestamp: `2026-10-17 12:${String(index).padStart(2, '0')}` })) }
      ]
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.goto(`${process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5188'}/sentinel`, { waitUntil: 'networkidle' })
    await page.locator('.heartbeat').first().waitFor()
    assert.equal(await page.locator('.heartbeat__cell').count(), 60)
    assert.equal(await page.locator('.heartbeat').first().innerText(), '暂无采样')
    assert.equal(await page.locator('.heartbeat').first().locator('.heartbeat__cell--unknown').count(), 30)
    assert.equal(await page.locator('.heartbeat__cell--down').count(), 6)
    assert.match(await page.locator('.heartbeat').nth(1).locator('.heartbeat__cell').first().getAttribute('title'), /12:00 · 正常/)
    assert.equal(await page.locator('.heartbeat__cell').first().evaluate(el => getComputedStyle(el).animationName), 'none')
    await page.locator('.sentinel-table-wrap').screenshot({ path: `test-artifacts/heartbeat/${theme}.png` })
    assert.deepEqual(errors, [])
    console.log(`${theme}: 30-slot empty/history, labels, reduced motion, no page errors OK`)
    await page.close()
  }
} finally { await browser.close() }
