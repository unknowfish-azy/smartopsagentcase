// 用户层服务（127.0.0.1:5173）门户默认值回归检查。
// 管理员层迁到 5174 后，用户层必须仍然默认落在「用户层」，外观与入口语义不变。

import { chromium } from 'playwright'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage()
const errors = []
page.on('pageerror', failure => errors.push(`pageerror: ${failure.message}`))
page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`) })

const probe = async path => {
    const response = await page.goto(`http://127.0.0.1:5173${path}`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(700)
    return {
        path,
        status: response?.status(),
        title: await page.title(),
        url: page.url(),
        activeTabId: await page.locator('[role="tab"][aria-selected="true"]').first().getAttribute('id').catch(() => null),
        activePortal: await page.locator('[role="tab"][aria-selected="true"]').first().textContent().catch(() => null)
    }
}

const results = []
for (const path of ['/', '/login', '/login?portal=admin']) {
    try { results.push(await probe(path)) } catch (failure) { results.push({ path, error: failure.message }) }
}

console.log(JSON.stringify({ results, errors: errors.slice(0, 10) }, null, 2))
await browser.close()
