import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5174'
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const policy = { targetCount: 2, perUserConcurrency: 2, globalConcurrency: 8, connectTimeoutMs: 3000, readTimeoutMs: 10000, maxResponseBytes: 262144, miniConfigured: true, observabilityConfigured: false, harborConfigured: false }

async function open(width, mode, admin = false) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  const errors = []
  const requests = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('request', request => requests.push(request.url()))
  await page.addInitScript(({ mode }) => {
    if (!localStorage.getItem('smartops_visual_mode')) localStorage.setItem('smartops_visual_mode', mode)
    if (!localStorage.getItem('smartops_theme')) localStorage.setItem('smartops_theme', 'light')
  }, { mode })
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    let data = []
    if (path === '/api/auth/session') data = { user: { id: 11, username: 'phase2-test', role: admin ? 'admin' : 'operator', portal: admin ? 'admin' : 'user', mustChangePassword: false }, csrfToken: 'test-only' }
    if (path.endsWith('/health')) data = { scope: admin ? 'admin' : 'user', checks: [], policy }
    if (path.includes('/readiness')) data = { unavailableTables: [], observability: [], harbor: { configured: false }, internalAuthenticationConfigured: false }
    return route.fulfill({ json: { code: 200, data } })
  })
  return { page, errors, requests }
}

const threeRequests = requests => requests.filter(url => /vendor-three|\/three(?:\.js|\/)|milky-way-scene|\/ParticleWhale(?:-|\.vue)/.test(url))
async function noOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
}

try {
  for (const width of [375, 1440]) {
    for (const mode of ['balanced', 'lightweight', 'reduced-motion']) {
      const { page, errors, requests } = await open(width, mode)
      await page.goto(`${base}/health`, { waitUntil: 'networkidle' })
      await page.locator('.health-card').waitFor()
      assert.deepEqual(threeRequests(requests), [], 'non-home must not load Three.js')
      assert.equal(await page.locator('.admin-policy-summary').count(), 0)
      await page.goto(`${base}/`, { waitUntil: 'networkidle' })
      await page.locator('.home').waitFor()
      if (mode === 'balanced') {
        await page.waitForFunction(() => performance.getEntriesByType('resource').some(entry => /vendor-three|\/three(?:\.js|\/)/.test(entry.name)))
      } else {
        await page.locator('.canvas-whale').waitFor()
        assert.deepEqual(threeRequests(requests), [], 'lightweight homepage must not load Three.js')
      }
      for (const theme of ['dark', 'light']) {
        await page.getByLabel('选择主题模式').selectOption(theme)
        assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), theme)
        await noOverflow(page)
      }
      await page.getByLabel('选择视觉模式').selectOption('reduced-motion')
      assert.ok((await page.getByLabel('选择视觉模式').boundingBox()).height >= 44, 'visual selector must be touch accessible')
      await page.locator('.canvas-whale').waitFor()
      await page.waitForTimeout(250)
      assert.equal(await page.locator('.play-control').isDisabled(), true)
      const still = await page.locator('.canvas-whale').evaluate(canvas => canvas.toDataURL())
      await page.waitForTimeout(300)
      assert.equal(await page.locator('.canvas-whale').evaluate(canvas => canvas.toDataURL()), still)
      await page.reload({ waitUntil: 'networkidle' })
      assert.equal(await page.getByLabel('选择视觉模式').inputValue(), 'reduced-motion')
      await noOverflow(page)
      assert.deepEqual(errors, [])
      await page.close()
      console.log(`PASS ${width}px ${mode}: route resource boundary, theme, reduced motion, persistence`)
    }
    const { page, errors } = await open(width, 'lightweight', true)
    await page.goto(`${base}/admin/readiness`, { waitUntil: 'networkidle' })
    await page.locator('.admin-policy-summary').waitFor()
    assert.match(await page.locator('.admin-policy-summary').innerText(), /256 KiB/)
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      await noOverflow(page)
    }
    const doc = await page.locator('.admin-policy-summary a').getAttribute('href')
    assert.equal((await page.request.get(new URL(doc, base).href)).ok(), true)
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`PASS ${width}px admin policy and documentation`)
  }
} finally { await browser.close() }
