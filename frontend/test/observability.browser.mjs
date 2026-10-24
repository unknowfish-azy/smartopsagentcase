import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { mockSession } from './helpers/session.mjs'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  await mockSession(page)
  page.setDefaultTimeout(10000)
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'test' })))
  let configured = false, fail = false
  await page.route('**/api/observability/sources', route => route.fulfill({ json: {
    code: 200, data: [{ id: 'prometheus', configured }, { id: 'loki', configured }]
  } }))
  await page.route('**/api/observability/prometheus/query', async route => {
    const requestedQuery = route.request().postDataJSON().query
    assert.ok(['up', 'windows_memory_available_bytes / 1024^3'].includes(requestedQuery))
    const result = requestedQuery === 'up' ? [] : [{ metric: { job: 'windows', instance: '127.0.0.1:9182' }, values: [[1790495606, '0.82']] }]
    await route.fulfill({ json: fail ? { code: 502, message: '测试上游不可用' } : {
      code: 200, data: { traceId: 'test-trace', source: 'prometheus', start: '2026-09-27T00:00:00Z', end: '2026-09-27T00:15:00Z', response: { status: 'success', data: { resultType: 'matrix', result } } }
    } })
  })
  await page.goto('http://127.0.0.1:5173/tools/prometheus-query')
  const panel = page.locator('.observability-query')
  await panel.getByRole('status').filter({ hasText: '尚未配置' }).waitFor()
  assert.equal(await panel.getByRole('button', { name: '查询真实数据' }).isDisabled(), true)
  assert.equal(await panel.getByRole('button', { name: '可用内存' }).isDisabled(), true)
  configured = true
  await panel.getByRole('button', { name: '重新检查配置' }).click()
  await panel.getByRole('status').filter({ hasText: '地址已配置' }).waitFor()
  await panel.getByRole('button', { name: '查询真实数据' }).click()
  await panel.getByText('TraceId：test-trace').waitFor()
  await panel.getByText('当前时间范围没有返回样本').waitFor()
  await panel.getByText('原始响应').click()
  assert.match(await panel.locator('pre').innerText(), /"result": \[\]/)
  await panel.getByRole('button', { name: '可用内存' }).click()
  await panel.getByRole('cell', { name: '0.82 GiB' }).waitFor()
  assert.match(await panel.getByRole('table').innerText(), /instance=127.0.0.1:9182/)
  await page.screenshot({ path: 'test-artifacts/observability-success.png', fullPage: true })
  fail = true
  await panel.getByRole('button', { name: '可用内存' }).click()
  await panel.getByRole('alert').filter({ hasText: '测试上游不可用' }).waitFor()
  assert.equal(await panel.getByRole('table').count(), 0)
  await page.screenshot({ path: 'test-artifacts/observability.png', fullPage: true })
  console.log('PASS: unconfigured gate, host preset, empty results, error clears stale samples')
} finally { await browser.close() }
