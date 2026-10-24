import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'browser-test' })))
  let fail = true
  await page.route('**/api/operations/capabilities', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 200, data: [{ protocol: 'SSH', status: 'SUPPORTED' }, { protocol: 'RDP', status: 'REQUIRES_NATIVE_BRIDGE' }] }) }))
  await page.route('**/api/operations/sessions', route => route.fulfill({ status: fail ? 500 : 200, contentType: 'application/json', body: JSON.stringify(fail ? { code: 500, message: 'diagnostic failure' } : { code: 200, data: [] }) }))
  await page.goto('http://127.0.0.1:5180/connections', { waitUntil: 'networkidle' })
  assert.equal(await page.locator('.connections-page').count(), 1)
  assert.match(await page.locator('[role="alert"]').innerText(), /连接资源加载失败/)
  fail = false
  await page.getByRole('button', { name: '重试' }).click()
  await page.waitForTimeout(100)
  assert.equal(await page.locator('.session-empty').count(), 1)
  await page.screenshot({ path: 'test-artifacts/connection-center-empty.png', fullPage: true })
} finally { await browser.close() }
