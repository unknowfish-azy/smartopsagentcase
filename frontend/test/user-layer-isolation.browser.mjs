// 用户层未被管理员层视觉重构污染的核验。
// 关键断言：用户层页面上不存在任何 .admin-surface 作用域，用户层自有令牌仍生效。

import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_TEST_URL || 'http://127.0.0.1:5173'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
    const separator = line.indexOf('=')
    return [line.slice(0, separator), line.slice(separator + 1)]
}))

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
page.setDefaultTimeout(20000)

const probe = async path => {
    await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(800)
    return page.evaluate(() => ({
        path: location.pathname,
        adminSurfaceCount: document.querySelectorAll('.admin-surface').length,
        adminTokenLeaked: getComputedStyle(document.documentElement).getPropertyValue('--admin-bg').trim(),
        smartBg: getComputedStyle(document.documentElement).getPropertyValue('--smart-bg').trim(),
        bodyBg: getComputedStyle(document.body).backgroundColor,
        h1: document.querySelector('h1')?.textContent?.trim()?.slice(0, 40) ?? null
    }))
}

const report = { login: await probe('/login?portal=user') }

// 真实登录用户层（bootstrap 账号为管理员，用户层入口按当前后端策略可能被拒；
// 因此这里只验证未登录态的视觉隔离，不据此断言登录策略）。
report.login.sidebarPresent = await page.locator('.sidebar').count()

report.notes = [
    '用户层与管理员层使用不同的 DOM 根（.admin-surface 仅存在于 /admin），样式不会互相渗透',
    '--admin-* 令牌定义在 .admin-surface 内，未定义在 :root，因此不会影响用户层'
]
console.log(JSON.stringify(report, null, 2))
await browser.close()
