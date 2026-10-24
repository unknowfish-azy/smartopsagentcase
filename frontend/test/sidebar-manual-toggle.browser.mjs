import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.addInitScript(() => {
    localStorage.setItem('smartops_preview_auth', JSON.stringify({ username: 'sidebar-test' }))
    localStorage.setItem('smartops_sidebar_collapsed', JSON.stringify(false))
  })
  await page.goto('http://127.0.0.1:5176/', { waitUntil: 'networkidle' })

  const sidebar = page.locator('.sidebar')
  const collapse = page.getByRole('button', { name: '收起主菜单' })
  const expand = page.getByRole('button', { name: '展开主菜单' })
  assert.equal(await expand.isVisible(), true)
  assert.equal(await collapse.isVisible(), true)
  const expandTop = (await expand.boundingBox())?.y
  const collapseBottom = (await collapse.boundingBox())?.y
  assert.equal(await expand.evaluate(node => getComputedStyle(node).position), 'fixed')
  assert.equal(await collapse.evaluate(node => getComputedStyle(node).position), 'fixed')
  await sidebar.evaluate(node => { node.scrollTop = node.scrollHeight })
  await page.waitForTimeout(80)
  assert.equal((await expand.boundingBox())?.y, expandTop)
  assert.equal((await collapse.boundingBox())?.y, collapseBottom)
  const expandedWidth = (await sidebar.boundingBox())?.width
  assert.ok(expandedWidth >= 240, `expected expanded sidebar, got ${expandedWidth}`)

  await collapse.click()
  await page.waitForTimeout(250)

  const collapsedWidth = (await sidebar.boundingBox())?.width
  assert.ok(collapsedWidth <= 90, `expected collapsed sidebar, got ${collapsedWidth}`)
  assert.equal(await sidebar.evaluate(node => node.classList.contains('sidebar--expanded')), false)

  assert.equal(await expand.isVisible(), true)
  await expand.click()
  await page.waitForTimeout(250)

  const reopenedWidth = (await sidebar.boundingBox())?.width
  assert.ok(reopenedWidth >= 240, `expected reopened sidebar, got ${reopenedWidth}`)
  assert.equal(await collapse.isVisible(), true)
} finally {
  await browser.close()
}
