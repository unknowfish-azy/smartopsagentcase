import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/login-glass', { recursive: true })

try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    const errors = [], requests = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => requests.push(request.url()))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_theme', 'light')
      localStorage.setItem('smartops_visual_mode', 'balanced')
    })
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname
      if (!path.startsWith('/api/')) return route.continue()
      assert.equal(route.request().method(), 'GET')
      const data = path === '/api/auth/session' ? { user: null, csrfToken: 'mock-csrf' } : path === '/api/auth/human-verification' ? { enabled: false, available: true, required: false, provider: 'none', action: new URL(route.request().url()).searchParams.get('action') } : { enabled: true, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 }
      return route.fulfill({ json: { code: 200, data } })
    })
    await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
    const card = page.locator('.login-form')
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      const style = await card.evaluate(element => {
        const card = getComputedStyle(element), glow = getComputedStyle(element, '::before'), flow = getComputedStyle(element, '::after')
        return { blur: card.backdropFilter, background: card.backgroundColor, transform: card.transform, filter: card.filter, glowPointerEvents: glow.pointerEvents, flowPointerEvents: flow.pointerEvents, inset: [glow.top, glow.right, glow.bottom, glow.left] }
      })
      assert.match(style.blur, /blur\(/, 'login card restores its glass material')
      assert.match(style.background, /rgba\(/, 'glass surface is translucent')
      assert.equal(style.transform, 'none', 'form never tilts or shifts with the highlight')
      assert.equal(style.filter, 'none', 'text and controls are not blurred')
      assert.equal(style.glowPointerEvents, 'none')
      assert.equal(style.flowPointerEvents, 'none')
      assert.deepEqual(style.inset, ['0px', '0px', '0px', '0px'])
      const before = await card.boundingBox()
      await card.hover({ position: { x: 30, y: 30 } })
      await page.waitForTimeout(60)
      const first = await card.evaluate(element => element.style.getPropertyValue('--login-light-x'))
      await card.hover({ position: { x: before.width - 30, y: 50 } })
      await page.waitForTimeout(60)
      const second = await card.evaluate(element => element.style.getPropertyValue('--login-light-x'))
      assert.notEqual(first, second, 'desktop pointer moves the decorative light')
      assert.deepEqual(await card.boundingBox(), before)
      await page.getByPlaceholder('输入运维账号').fill('visual-check-only')
      await page.getByPlaceholder('输入访问密码').fill('not-a-real-credential')
      await page.getByRole('button', { name: '显示密码', exact: true }).click()
      assert.equal(await page.getByPlaceholder('输入访问密码').getAttribute('type'), 'text')
      await page.getByRole('button', { name: '隐藏密码', exact: true }).click()
      await page.getByPlaceholder('输入访问密码').fill('')
      await page.getByPlaceholder('输入运维账号').fill('')
      await page.mouse.move(0, 0)
      await page.screenshot({ path: `test-artifacts/login-glass/${theme}-${width}.png`, fullPage: true })
    }
    for (const mode of ['lightweight', 'reduced-motion']) {
      await page.getByLabel('选择视觉模式').selectOption(mode)
      await page.locator(`.login-shell[data-visual-mode="${mode}"]`).waitFor()
      assert.equal(await card.evaluate(element => getComputedStyle(element, '::after').animationName), 'none')
      const fixed = await card.evaluate(element => element.style.getPropertyValue('--login-light-x'))
      await card.hover({ position: { x: 20, y: 20 } })
      await page.waitForTimeout(60)
      assert.equal(await card.evaluate(element => element.style.getPropertyValue('--login-light-x')), fixed)
    }
    await page.getByLabel('选择视觉模式').selectOption('balanced')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.waitForTimeout(100)
    assert.equal(await card.evaluate(element => getComputedStyle(element, '::after').animationName), 'none')
    const fixed = await card.evaluate(element => element.style.getPropertyValue('--login-light-x'))
    await card.hover({ position: { x: 50, y: 50 } })
    await page.waitForTimeout(60)
    assert.equal(await card.evaluate(element => element.style.getPropertyValue('--login-light-x')), fixed)
    assert.equal(requests.some(url => /vendor-three|\/three(?:\.js|\/)|milky-way-scene/.test(url)), false)
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS ${width}px: glass, light/dark, stable controls, decorative-only pointer light and motion preferences`)
  }
} finally {
  await browser.close()
}
