import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
import { createTokenUsageDemo } from '../src/components/model/tokenUsageDemo.js'

const fixture = createTokenUsageDemo()
for (const key of ['calls', 'successes', 'failures', 'knownTokens', 'inputTokens', 'outputTokens']) {
  assert.equal(fixture.daily.reduce((sum, day) => sum + day[key], 0), fixture.summary[key])
}
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/model-analytics', { recursive: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
    let reads = 0, writes = 0, offline = true
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => {
      localStorage.setItem('smartops_preview_auth', '{"username":"demo-check"}')
      localStorage.setItem('smartops_theme', 'dark')
    })
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }
    await page.route('**/api/model-connections**', route => route.fulfill({ headers, json: [] }))
    await page.route('**/api/model-analytics**', route => {
      if (route.request().method() !== 'GET') writes++
      reads++
      if (offline) return route.fulfill({ status: 503, headers, json: {} })
      return route.fulfill({ headers, json: { ...createTokenUsageDemo(), budget: 700000, budgetUsedTokens: 321 } })
    })
    await page.goto('http://127.0.0.1:5174/token-usage', { waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '暂时无法读取统计' }).waitFor()
    const initialReads = reads
    await page.getByRole('button', { name: '查看虚构案例', exact: true }).click()
    await page.getByText('演示模式 · 虚构数据', { exact: true }).waitFor()
    await page.locator('.line-chart canvas').waitFor()
    assert.equal(await page.locator('.error-panel').count(), 0)
    assert.equal(await page.locator('.budget-form').count(), 0)
    assert.match(await page.locator('.metric-grid').innerText(), /150,000/)
    assert.match(await page.locator('.budget-remaining').innerText(), /350,000/)
    assert.equal(await page.getByRole('progressbar').getAttribute('aria-valuenow'), '30')
    assert.equal(reads, initialReads)
    assert.equal(writes, 0)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await page.screenshot({ path: `test-artifacts/model-analytics/demo-${width}.png`, fullPage: true })
    await page.getByRole('button', { name: '返回真实数据', exact: true }).click()
    await page.getByRole('heading', { name: '暂时无法读取统计' }).waitFor()
    offline = false
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await page.getByLabel('设置本月额度（Token）').waitFor()
    assert.equal(await page.getByLabel('设置本月额度（Token）').inputValue(), '700000')
    await page.getByRole('button', { name: '查看虚构案例', exact: true }).click()
    await page.getByRole('button', { name: '返回真实数据', exact: true }).click()
    assert.equal(await page.getByLabel('设置本月额度（Token）').inputValue(), '700000')
    assert.match(await page.locator('.budget-total').innerText(), /321/)
    await page.getByRole('button', { name: '查看虚构案例', exact: true }).click()
    await page.locator('.analytics-tabs').getByRole('link', { name: '模型强度', exact: true }).click()
    assert.equal(await page.locator('.demo-banner').count(), 0)
    // Strength has its own explicit opt-in and also works when the backend is offline.
    offline = true
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('heading', { name: '暂时无法读取统计' }).waitFor()
    const beforeStrength = reads
    await page.getByRole('button', { name: '查看虚构案例', exact: true }).click()
    await page.getByText('演示模式 · 虚构数据', { exact: true }).waitFor()
    assert.equal(await page.locator('.strength-charts .line-chart canvas').count(), 2)
    assert.match(await page.locator('.metric-grid').innerText(), /96.8/)
    assert.match(await page.locator('.metric-grid').innerText(), /242 成功 \/ 8 失败/)
    assert.match(await page.locator('.metric-grid').innerText(), /250/)
    const expectedLatency = Math.round(fixture.summary.averageLatencyMs).toLocaleString('zh-CN')
    assert.ok((await page.locator('.metric-grid').innerText()).includes(expectedLatency))
    await page.getByText('查看每日数据', { exact: true }).first().click()
    assert.equal(await page.locator('.chart-data').first().locator('tbody tr').count(), 7)
    await page.getByText('查看每日数据', { exact: true }).first().click()
    assert.equal(reads, beforeStrength)
    assert.equal(writes, 0)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `test-artifacts/model-analytics/strength-demo-${width}.png`, fullPage: true })
    await page.getByLabel('选择主题模式').selectOption('light')
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `test-artifacts/model-analytics/strength-demo-${width}-light.png`, fullPage: true })
    await page.getByRole('button', { name: '返回真实数据', exact: true }).click()
    await page.getByRole('heading', { name: '暂时无法读取统计' }).waitFor()
    await page.getByRole('button', { name: '查看虚构案例', exact: true }).click()
    await page.locator('.analytics-tabs').getByRole('link', { name: 'Token 用量与额度', exact: true }).click()
    assert.equal(await page.locator('.demo-banner').count(), 0)
    assert.equal(writes, 0)
    assert.deepEqual(errors, [])
    console.log(`PASS ${width}px fictional demo: consistent totals, offline access, no API writes, real budget restored, route isolation`)
    await page.close()
  }
} finally { await browser.close() }
