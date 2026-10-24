import assert from 'node:assert/strict'
import { chromium } from 'playwright'

// 被测页面（/health、/tools/*）都在用户层 5173；5174 是 admin 层，没有这些路由。
// 曾因默认写 5174 导致 goto networkidle 超时（与 model-analytics.browser.mjs 同坑）。
const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })

try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
    const errors = []
    const calls = []
    let healthAttempts = 0
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_theme', 'light')
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 11, username: 'diagnostic-user', role: 'operator', portal: 'user' }))
    })
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) calls.push(request.url()) })
    await page.route('**/api/auth/session', route => route.fulfill({ json: { code: 200, data: { user: { id: 11, username: 'diagnostic-user', role: 'operator', portal: 'user', mustChangePassword: false }, csrfToken: 'browser-csrf' } } }))
    await page.route('**/api/diagnostics/health', route => {
      healthAttempts += 1
      if (healthAttempts === 2) return route.fulfill({ status: 503, json: { code: 503, message: 'private backend detail' } })
      return route.fulfill({ json: { code: 200, data: { scope: 'user', checks: [{ id: 'authorized-targets', label: '授权诊断目标', status: 'HEALTHY', scope: 'user', checkKind: 'CONFIGURATION', checkedAt: new Date().toISOString(), durationMs: 0, summary: '授权目标已配置', nextAction: '手动检查' }] } } })
    })
    await page.route('**/api/diagnostics/targets', route => route.fulfill({ json: { code: 200, data: [{ id: 'web', label: 'Web API', scheme: 'https' }] } }))
    const probePayloads = []
    await page.route('**/api/diagnostics/http', route => {
      probePayloads.push(route.request().postDataJSON())
      return route.fulfill({ status: 503, json: { code: 503, message: 'private probe detail' } })
    })

    await page.goto(`${base}/health`, { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: /配置|可用|服务/ }).first().waitFor()
    assert.match(await page.locator('.health-center').innerText(), /授权目标已配置/)
    await page.locator('.health-card button').click()
    await page.locator('.health-card [role="alert"]').waitFor()
    assert.equal(await page.locator('.health-card .health-status--healthy').count(), 0)
    assert.match(await page.locator('.diagnostic-stale').innerText(), /结果可能已过期/)
    assert.doesNotMatch(await page.locator('.health-card').innerText(), /private backend/)
    await page.getByLabel('选择主题模式').selectOption('dark')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    await page.locator('.health-card button').click()
    await page.locator('.health-card .health-status--healthy').waitFor()
    assert.equal(await page.locator('.diagnostic-stale').count(), 0)
    await page.getByLabel('选择主题模式').selectOption('light')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    const healthCalls = calls.length

    for (const toolId of ['service-http-check', 'service-certificate-check', 'config-diff']) {
      await page.goto(`${base}/tools/${toolId}`, { waitUntil: 'networkidle' })
      await page.locator('.tools-page').waitFor()
      assert.equal(await page.locator('.diagnostic-card').count() > 0, true)
      if (toolId === 'service-http-check') {
        const card = page.locator('.network-card').first()
        const target = card.locator('select').first()
        const assertion = card.locator('input').first()
        await target.selectOption('web')
        await assertion.fill('status')
        await card.getByRole('button', { name: '开始检查' }).click()
        await card.getByRole('alert').waitFor()
        assert.equal(await target.inputValue(), 'web')
        assert.equal(await assertion.inputValue(), 'status')
        await card.getByRole('button', { name: '重试检查' }).click()
        await card.getByRole('alert').waitFor()
        assert.deepEqual(probePayloads[0], probePayloads[1])
        assert.doesNotMatch(await card.innerText(), /private probe/)
      }
    }

    await page.goto(`${base}/tools/config-diff`, { waitUntil: 'networkidle' })
    const beforeDiff = calls.length
    const textareas = page.locator('.diff-inputs textarea')
    await textareas.nth(0).fill('<img src=x onerror=window.__diffInjected=1>\npassword=old-secret')
    await textareas.nth(1).fill('<img src=x onerror=window.__diffInjected=2>\npassword=new-secret')
    assert.equal(await page.evaluate(() => window.__diffInjected || false), false)
    assert.match(await page.locator('.diff-summary').innerText(), /敏感值|新增|删除/)
    assert.equal(calls.length, beforeDiff)
    await page.getByRole('button', { name: '清空', exact: true }).click()
    assert.equal(await textareas.nth(0).inputValue(), '')
    assert.equal(await textareas.nth(1).inputValue(), '')
    assert.equal(await page.locator('.diff-summary').count(), 0)

    await page.getByLabel('选择主题模式').selectOption('dark')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    assert.ok(healthCalls > 0)
    assert.deepEqual(errors, [])
    console.log(`PASS ${width}px health center, diagnostic tools, local diff, theme sync and no HTML execution`)
    await page.close()
  }
} finally {
  await browser.close()
}
