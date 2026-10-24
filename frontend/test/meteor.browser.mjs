import assert from 'node:assert/strict'
import { chromium } from 'playwright'
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto('http://127.0.0.1:5174/login', { waitUntil: 'networkidle' })
  assert.equal(await page.locator('.meteor-flight').count(), 6)
  // Start inside the flight phase, not the intentional gap between meteors.
  await page.locator('.meteor-flight').first().evaluate(el => {
    const animation = el.getAnimations()[0]
    animation.currentTime = 0
  })
  const read = () => page.locator('.meteor-flight').first().evaluate(el => getComputedStyle(el).transform)
  const before = await read()
  await page.waitForTimeout(1400)
  assert.notEqual(await read(), before)
  await page.screenshot({ path: 'test-artifacts/home-orbit/login-organisms.png' })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  assert.equal(await page.locator('.meteor-shower').evaluate(el => getComputedStyle(el).display), 'none')
  assert.deepEqual(errors, [])
  console.log('PASS login rendering, six meteors, movement, reduced motion, no runtime errors')
} finally { await browser.close() }
