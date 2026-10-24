import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.PERSONAL_NAV_BASE_URL || 'http://127.0.0.1:5174'
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/milky-way', { recursive: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } })
    const errors = []
    page.on('pageerror', error => {
      if (error.message === '无法连接服务器，请检查后端服务是否启动') console.log('Backend offline after sign-in')
      else errors.push(error.message)
    })
    page.on('console', message => { if (/Shader Error|VALIDATE_STATUS|INVALID_OPERATION/.test(message.text())) errors.push(message.text()) })
    await page.addInitScript(() => localStorage.setItem('smartops_theme', 'dark'))
    await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
    const canvas = page.locator('.milky-way canvas')
    assert.equal(await canvas.count(), 1, 'Login must mount the GPU particle background')
    await page.waitForFunction(() => document.querySelector('.milky-way')?.dataset.state === 'ready')
    // Hide foreground organisms so their animation cannot make a static galaxy pass.
    const particleOnly = { style: 'body * { visibility: hidden !important; } .milky-way, .milky-way canvas { visibility: visible !important; } .milky-way { opacity: 1 !important; }' }
    const first = await canvas.screenshot(particleOnly)
    await page.waitForTimeout(700)
    const second = await canvas.screenshot(particleOnly)
    assert.equal(first.equals(second), false, 'Particle background must animate between frames')
    await page.locator('input[autocomplete=username]').fill('particle-check')
    await page.locator('input[autocomplete=current-password]').fill('preview-only')
    assert.equal(await page.locator('input[autocomplete=username]').inputValue(), 'particle-check')
    await page.screenshot({ path: `test-artifacts/milky-way/login-${width}.png` })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.waitForTimeout(150)
    const still = await canvas.screenshot(particleOnly)
    await page.waitForTimeout(200)
    assert.equal((await canvas.screenshot(particleOnly)).equals(still), true, 'Reduced motion must freeze the particle canvas')
    await page.locator('button[type=submit]').click()
    await page.waitForURL(`${base}/`)
    assert.equal(await page.locator('.login-shell').count(), 0, 'Login must unmount after signing in')
    assert.equal(await page.locator('.app-layout > .milky-way').count(), 1, 'Homepage must have the particle background')
    await page.waitForFunction(() => document.querySelector('.app-layout > .milky-way')?.dataset.state === 'ready')
    assert.equal(await page.locator('.milky-way').evaluate(el => getComputedStyle(el).position), 'fixed')
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    const homeCanvas = page.locator('.milky-way canvas')
    const homeFirst = await homeCanvas.screenshot(particleOnly)
    await page.waitForTimeout(500)
    assert.equal((await homeCanvas.screenshot(particleOnly)).equals(homeFirst), false, 'Homepage particles must also animate')
    await page.screenshot({ path: `test-artifacts/milky-way/home-${width}.png` })
    assert.ok((await page.locator('#main-content').innerText()).length > 40)
    await page.goto(`${base}/knowledge`, { waitUntil: 'networkidle' })
    assert.equal(await page.locator('.milky-way').count(), 0, 'Other routes must not keep the homepage renderer')
    assert.deepEqual(errors, [])
    console.log(`PASS login particles, reduced motion and sign-in at ${width}px`)
    await page.close()
  }
  const fallback = await browser.newPage()
  await fallback.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      if (this.closest('.milky-way') && type.startsWith('webgl')) return null
      return original.call(this, type, ...args)
    }
  })
  await fallback.goto(`${base}/login`, { waitUntil: 'networkidle' })
  await fallback.waitForFunction(() => document.querySelector('.milky-way')?.dataset.state === 'fallback')
  await fallback.locator('input[autocomplete=username]').fill('fallback-check')
  assert.equal(await fallback.locator('button[type=submit]').isVisible(), true)
  await fallback.close()
  console.log('PASS WebGL fallback preserves login form')
} finally { await browser.close() }
