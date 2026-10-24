import assert from 'node:assert/strict'
import { access, mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const baseUrl = process.env.PERSONAL_NAV_BASE_URL || 'http://127.0.0.1:5173'
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const browser = await chromium.launch({ executablePath: edgePath, headless: true })
await mkdir('test-artifacts/personal-navigation', { recursive: true })

try {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await desktop.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'navigation-test' })))
  await desktop.goto(`${baseUrl}/agent`, { waitUntil: 'networkidle' })
  const agentToggle = desktop.locator('[aria-controls="personal-nav-agent"]')
  assert.equal(await agentToggle.getAttribute('aria-expanded'), 'true')
  await desktop.screenshot({ path: 'test-artifacts/personal-navigation/agent-desktop.png', fullPage: true })
  await desktop.locator('[aria-label="Next page: EXECUTION TRACE"]').click()
  await desktop.waitForURL('**/agent/trace')
  assert.equal(await desktop.locator('.page-stepper__button--next').isDisabled(), true)
  await desktop.close()

  const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } })
  await mobile.addInitScript(() => localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'navigation-test' })))
  await mobile.goto(`${baseUrl}/agent`, { waitUntil: 'networkidle' })
  const menuButton = mobile.locator('.menu-button')
  assert.equal(await menuButton.getAttribute('aria-expanded'), 'false')
  await menuButton.click()
  assert.equal(await menuButton.getAttribute('aria-expanded'), 'true')
  const traceLink = mobile.locator('#personal-nav-agent a[href="/agent/trace"]')
  assert.equal(await traceLink.count(), 1)
  await traceLink.click()
  await mobile.waitForURL('**/agent/trace')
  assert.equal(await menuButton.getAttribute('aria-expanded'), 'false')
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
  await mobile.screenshot({ path: 'test-artifacts/personal-navigation/agent-mobile.png', fullPage: true })
  await access('test-artifacts/personal-navigation/agent-mobile.png')
  await mobile.close()
} finally {
  await browser.close()
}
