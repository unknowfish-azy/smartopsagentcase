// 管理员层独立服务（127.0.0.1:5174）冒烟检查。
// 只验证：服务可访问、渲染的是管理员层入口、门户默认落在管理员层、无页面级运行时错误。
// 不提交登录、不注册、不重置密码；后端缺失导致的会话读取失败在预期内。

import { chromium } from 'playwright'

const base = process.env.SMARTOPS_ADMIN_BASE_URL || 'http://127.0.0.1:5174'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext()
const page = await context.newPage()
const errors = []
page.on('pageerror', failure => errors.push(`pageerror: ${failure.message}`))
page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`) })

const probe = async path => {
    const response = await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(800)
    return {
        path,
        status: response?.status(),
        title: await page.title(),
        url: page.url(),
        activePortal: await page.locator('[role="tab"][aria-selected="true"]').first().textContent().catch(() => null),
        activeTabId: await page.locator('[role="tab"][aria-selected="true"]').first().getAttribute('id').catch(() => null),
        sessionHint: await page.locator('.login-form__footer').first().textContent().catch(() => null),
        portalTabs: await page.locator('[role="tab"]').allTextContents().catch(() => []),
        hasLoginForm: await page.locator('form').count()
    }
}

const results = []
for (const path of ['/', '/login', '/admin', '/admin/users']) {
    try { results.push(await probe(path)) }
    catch (failure) { results.push({ path, error: failure.message }) }
}

// 关键回归：深链被重定向到登录页后，门户必须仍停在管理员层，而不是回落到用户层。
await page.goto(`${base}/admin/users`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(800)
const deepLink = {
    url: page.url(),
    activeTabId: await page.locator('[role="tab"][aria-selected="true"]').first().getAttribute('id').catch(() => null),
    activePortal: await page.locator('[role="tab"][aria-selected="true"]').first().textContent().catch(() => null),
    sessionHint: await page.locator('.login-form__footer').first().textContent().catch(() => null)
}

console.log(JSON.stringify({ base, results, deepLink, errors: errors.slice(0, 20) }, null, 2))
await browser.close()
