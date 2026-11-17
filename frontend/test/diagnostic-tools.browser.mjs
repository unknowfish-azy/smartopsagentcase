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
    // 全局外壳（MainLayout）会并发拉 inspector/summary 等数据；未 mock 时 401 会被前端判为会话失效
    // 并踢回 /login?redirect=/health，导致健康中心永远渲染不出来。先铺空数据兜底，再按具体接口覆盖。
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: { code: 200, data: null } }))
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

    // ① 结论带 + 分组列表：通过组默认折叠，展开后才可见检查项摘要。
    await page.goto(`${base}/health`, { waitUntil: 'networkidle' })
    await page.locator('.hc-page').waitFor()
    await page.getByRole('heading', { name: '健康诊断' }).waitFor()
    assert.match(await page.locator('.hc-verdict').innerText(), /全部通过 · 1 项检查/)
    assert.equal(await page.locator('.hc-v-count').count(), 4)
    const passGroup = page.locator('.hc-group').filter({ hasText: '通过' }).first()
    await passGroup.locator('.hc-group-head').click()
    await page.locator('.hc-row-sum').first().waitFor()
    assert.match(await page.locator('.hc-row-sum').first().innerText(), /授权目标已配置/)
    assert.equal(await page.locator('.hc-row .hc-st--healthy').count(), 1)

    // ② 重新检查失败：只暴露归一化后的中文结论，不透出后端原始报文；旧快照标记为可能过期。
    await page.locator('.hc-verdict .hc-btn-primary').click()
    await page.locator('.hc-error').waitFor()
    assert.match(await page.locator('.hc-error').innerText(), /连接失败|重试/)
    assert.equal(await page.locator('.hc-stale-bar').count(), 1)
    assert.match(await page.locator('.hc-stale-bar').innerText(), /结果可能已过期/)
    assert.doesNotMatch(await page.locator('.hc-page').innerText(), /private backend/)

    // ③ 过期条内重试成功：错误与过期提示一起消失。
    await page.locator('.hc-stale-bar button').first().click()
    await page.locator('.hc-stale-bar').waitFor({ state: 'detached' })
    assert.equal(await page.locator('.hc-error').count(), 0)

    await page.getByLabel('选择主题模式').selectOption('dark')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    await page.getByLabel('选择主题模式').selectOption('light')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
    const healthCalls = calls.length

    // ④ 内嵌的三个旧工具仍在：HTTP 探测保留输入态、重试载荷一致、错误不透出后端报文。
    assert.equal(await page.locator('.network-card').count(), 2)
    const card = page.locator('.network-card').first()
    const target = card.locator('select').first()
    const assertionInput = card.locator('input').first()
    await target.selectOption('web')
    await assertionInput.fill('status')
    await card.getByRole('button', { name: /开始检查/ }).click()
    await card.getByRole('alert').waitFor()
    assert.equal(await target.inputValue(), 'web')
    assert.equal(await assertionInput.inputValue(), 'status')
    await card.getByRole('button', { name: /重试检查|开始检查/ }).click()
    await card.getByRole('alert').waitFor()
    assert.deepEqual(probePayloads[0], probePayloads[1])
    assert.doesNotMatch(await card.innerText(), /private probe/)

    // ⑤ 配置差异：完全本地计算，不发起任何请求，且不执行输入里的 HTML。
    assert.equal(await page.locator('.diff-card').count(), 1)
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

    // ⑥ 独立工具页仍可直达（运维工具路由未随健康中心改版下线）。
    await page.goto(`${base}/tools/service-http-check`, { waitUntil: 'networkidle' })
    await page.locator('.tools-page').waitFor()
    assert.equal(await page.locator('.diagnostic-card').count() > 0, true)

    assert.ok(healthCalls > 0)
    assert.deepEqual(errors, [])
    console.log(`PASS ${width}px health center, inline diagnostic tools, local diff, theme sync and no HTML execution`)
    await page.close()
  }
} finally {
  await browser.close()
}
