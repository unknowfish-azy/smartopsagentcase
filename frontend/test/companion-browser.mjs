import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', '{}'))
    await page.goto(process.env.COMPANION_BASE_URL || 'http://127.0.0.1:5189/agent', { waitUntil: 'networkidle' })
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('smartops:fault-detected', { detail: {
      id: 'browser-502', title: '502 Bad Gateway', severity: 'HIGH', source: 'OCR', evidence: [{ source: 'OCR', content: '502 Bad Gateway', confidence: .97 }]
    } })))
    assert.equal(await page.locator('.inquiry-drawer').count(), 0, 'fault does not interrupt with a drawer')
    await page.locator('.ops-spider-pet').hover()
    await page.locator('.fault-entry').click()
    await page.locator('.inquiry-drawer').waitFor()
    await page.locator('.options button').nth(1).click()
    await page.locator('.primary-button').click()
    await page.waitForFunction(() => document.querySelector('.question-block h3')?.textContent.includes('最近'))
    const prompt = await page.locator('.question-block h3').innerText()
    await page.locator('.knowledge-card button').first().click()
    assert.equal(await page.locator('.knowledge-card button').first().isDisabled(), true)
    await page.locator('.close-button').click()
    await page.locator('.ops-spider-pet').hover()
    await page.locator('.fault-entry').click()
    assert.equal(await page.locator('.question-block h3').innerText(), prompt)
    assert.equal(await page.locator('.knowledge-card button').first().isDisabled(), true)
    const rect = await page.locator('.inquiry-drawer').boundingBox()
    assert.ok(rect.x >= 0 && rect.x + rect.width <= width)
    assert.deepEqual(errors, [])
    await page.close()
    console.log(`Companion browser flow passed: ${width}px`)
  }
} finally { await browser.close() }
