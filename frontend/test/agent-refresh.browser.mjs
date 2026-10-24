import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts', { recursive: true })

async function assertReadable(locator) {
  const result = await locator.evaluate(element => {
    const style = getComputedStyle(element)
    const channels = color => color.match(/[\d.]+/g).slice(0, 3).map(Number)
    const luminance = color => channels(color).map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0)
    const foreground = luminance(style.color), background = luminance(style.backgroundColor)
    return { foreground: style.color, background: style.backgroundColor, ratio: (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05) }
  })
  assert.ok(result.ratio >= 4.5, `button must remain legible: ${JSON.stringify(result)}`)
}

try {
  for (const width of [375, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } })
    const errors = []
    let requests = 0, fail = false, respond = null
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_theme', 'dark')
      localStorage.setItem('smartops_visual_mode', 'lightweight')
    })
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) return route.continue()
      let data = []
      if (path === '/api/auth/session') data = { user: { id: 81, username: 'refresh-test', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'mock-csrf' }
      if (path === '/api/inspector/events') {
        requests++
        if (requests > 1) await new Promise(resolve => { respond = resolve })
        if (fail) return route.fulfill({ status: 503, json: { code: 503, message: '刷新测试：服务暂不可用' } })
      }
      await route.fulfill({ json: { code: 200, data } })
    })
    await page.goto(`${base}/agent`, { waitUntil: 'networkidle' })
    const button = page.locator('.page > header > button')
    for (const theme of ['dark', 'light']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      assert.equal(await button.innerText(), '刷新')
      await assertReadable(button)
      await button.hover()
      await assertReadable(button)
      await button.focus()
      await assertReadable(button)
      await page.screenshot({ path: `test-artifacts/agent-refresh-${theme}-${width}.png` })
    }
    for (const failed of [false, true]) {
      fail = failed
      await button.click()
      await page.waitForFunction(() => document.querySelector('.page > header > button').disabled)
      assert.equal(await button.innerText(), '刷新中…')
      await assertReadable(button)
      while (!respond) await new Promise(resolve => setTimeout(resolve, 20))
      respond()
      respond = null
      await page.waitForFunction(() => !document.querySelector('.page > header > button').disabled)
      assert.equal(await button.innerText(), '刷新')
      if (failed) await page.locator('.page .el-alert').waitFor()
    }
    assert.equal(requests, 3)
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS ${width}px: refresh light/dark, hover/focus, loading, successful and failed requests`)
  }
} finally {
  await browser.close()
}
