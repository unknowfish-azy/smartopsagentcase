import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/home-orbit', { recursive: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', '{}'); localStorage.setItem('smartops_theme', 'dark') })
    await page.goto('http://127.0.0.1:5174/', { waitUntil: 'networkidle' })
    const home = page.locator('.home-orbital')
    const active = home.locator('.orbit-card[aria-hidden="false"]')
    await home.waitFor()
    assert.equal(await home.locator('.orbit-card').count(), 7)
    assert.match(await active.innerText(), /我的系统，/)
    assert.equal(await home.locator('.section').count(), 0)
    await page.screenshot({ path: `test-artifacts/home-orbit/home-${width}.png`, fullPage: true })
    for (let i = 0; i < 7; i++) {
      assert.equal(await active.count(), 1)
      assert.equal(await home.locator('.orbit-card[inert]').count(), 6)
      const fits = await active.evaluate(el => {
        const card = el.getBoundingClientRect()
        return [...el.querySelectorAll('a')].every(link => { const r = link.getBoundingClientRect(); return r.bottom <= card.bottom + 4 && r.right <= card.right + 4 })
      })
      assert.equal(fits, true, `links fit card ${i}, width ${width}`)
      await home.getByRole('button', { name: '下一张', exact: true }).click()
    }
    assert.match(await active.innerText(), /我的系统，/)
    await home.getByRole('button', { name: '显示模型中心', exact: true }).click()
    assert.equal(await active.getByRole('link', { name: '用量与额度' }).getAttribute('href'), '/token-usage')
    await home.getByRole('button', { name: '上一张', exact: true }).press('ArrowLeft')
    assert.match(await active.innerText(), /重要的经验/)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    await page.getByLabel('选择主题模式').selectOption('light')
    await home.getByRole('button', { name: '显示个人系统' }).click()
    await page.evaluate(() => scrollTo(0, 0))
    await page.screenshot({ path: `test-artifacts/home-orbit/home-${width}-light.png`, fullPage: true })
    assert.deepEqual(errors, [])
    console.log(`PASS ${width}px seven sections, navigation, keyboard, wraparound, inactive focus isolation, card fit, themes`)
    await page.close()
  }
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  await page.addInitScript(() => localStorage.setItem('smartops_preview_auth', '{}'))
  await page.goto('http://127.0.0.1:5174/', { waitUntil: 'networkidle' })
  await page.mouse.move(0, 0)
  const ring = page.locator('.orbit-ring')
  const initial = await ring.getAttribute('style')
  await page.waitForTimeout(4800)
  assert.notEqual(await ring.getAttribute('style'), initial)
  await page.locator('.orbit-stage').hover()
  const stopped = await ring.getAttribute('style')
  await page.waitForTimeout(4700)
  assert.equal(await ring.getAttribute('style'), stopped)
  console.log('PASS automatic rotation and hover pause')
} finally { await browser.close() }
