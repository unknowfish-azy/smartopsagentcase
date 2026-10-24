import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
await mkdir('test-artifacts/extension-demo', { recursive: true })
try {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' })
    const errors = [], requests = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) requests.push(request.url()) })
    await page.addInitScript(() => { localStorage.setItem('smartops_preview_auth', '{}'); localStorage.setItem('smartops_theme', 'dark') })
    for (const route of ['plugins', 'skills']) {
      await page.goto(`http://127.0.0.1:5174/${route}`, { waitUntil: 'networkidle' })
      const before = await page.evaluate(() => [localStorage.getItem('smartops_plugin_workspace_v1'), localStorage.getItem('smartops_skills_v1')])
      const count = requests.length
      const demo = page.locator('.extension-demo')
      await demo.getByRole('button', { name: '查看虚构案例' }).click()
      await demo.getByText('演示模式 · 虚构案例', { exact: true }).waitFor()
      await demo.getByRole('button', { name: '模拟启用', exact: true }).click()
      await demo.getByText('模拟已启用（仅本案例）', { exact: true }).waitFor()
      await demo.getByRole('button', { name: '模拟停用', exact: true }).click()
      await demo.locator('summary').click()
      assert.match(await demo.locator('pre').innerText(), route === 'plugins' ? /demo-nginx-evidence/ : /demo-nginx-incident-coach/)
      assert.deepEqual(await page.evaluate(() => [localStorage.getItem('smartops_plugin_workspace_v1'), localStorage.getItem('smartops_skills_v1')]), before)
      assert.equal(requests.length, count)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      await demo.locator('summary').click()
      await page.evaluate(() => scrollTo(0, 0))
      await page.screenshot({ path: `test-artifacts/extension-demo/${route}-${width}.png`, fullPage: true })
      await page.getByLabel('选择主题模式').selectOption('light')
      await page.evaluate(() => scrollTo(0, 0))
      await page.screenshot({ path: `test-artifacts/extension-demo/${route}-${width}-light.png`, fullPage: true })
      await demo.getByRole('button', { name: '收起虚构案例' }).click()
      assert.equal(await demo.locator('.demo-content').count(), 0)
      await page.reload({ waitUntil: 'networkidle' })
      assert.equal(await page.locator('.demo-content').count(), 0)
    }
    assert.deepEqual(errors, [])
    console.log(`PASS ${width}px plugin/skill demos, simulated activation, manifest/instructions, storage and request isolation, themes`)
    await page.close()
  }
} finally { await browser.close() }
