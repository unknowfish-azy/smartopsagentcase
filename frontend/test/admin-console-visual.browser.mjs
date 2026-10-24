// 管理员层系统控制台视觉核验：在独立服务 127.0.0.1:5174 上真实登录并截图。
// 只读浏览，不执行任何写操作（不新建账号、不改角色、不重置密码）。

import { mkdir, readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_ADMIN_BASE_URL || 'http://127.0.0.1:5174'
const outDir = 'test-artifacts/admin-console-visual'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
    const separator = line.indexOf('=')
    return [line.slice(0, separator), line.slice(separator + 1)]
}))

await mkdir(outDir, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
page.setDefaultTimeout(20000)
const errors = []
page.on('pageerror', error => errors.push(`pageerror: ${error.message}`))
page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`) })

const report = {}

// 1) 管理员层服务默认落在管理员门户
await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' })
await page.locator('.login-form').waitFor()
report.landingUrl = page.url()
report.landingPortal = await page.locator('[role="tab"][aria-selected="true"]').first().textContent()
await page.screenshot({ path: `${outDir}/01-admin-login.png`, fullPage: true })

// 2) 真实管理员登录
await page.getByPlaceholder('输入运维账号').fill(credentials.SMARTOPS_BOOTSTRAP_USERNAME)
await page.getByPlaceholder('输入访问密码').fill(credentials.SMARTOPS_BOOTSTRAP_PASSWORD)
await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
await page.locator('.admin-layout').waitFor()
report.overviewUrl = page.url()

// 3) 逐页截图
const pages = [
    ['管理总览', '/admin', '02-admin-overview'],
    ['账户管理', '/admin/users', '03-admin-users'],
    ['管理员与授权', '/admin/governance', '04-admin-governance'],
    ['团队管理', '/admin/teams', '05-admin-teams'],
    ['活动会话', '/admin/sessions', '06-admin-sessions'],
    ['审计记录', '/admin/audit', '07-admin-audit'],
    ['二次认证', '/admin/security', '08-admin-security'],
    ['服务接入检查', '/admin/readiness', '09-admin-readiness']
]
report.pages = []
for (const [label, path, name] of pages) {
    await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' })
    await page.locator('.admin-main').waitFor()
    await page.waitForTimeout(600)
    const metrics = await page.evaluate(() => {
        const root = document.querySelector('.admin-surface')
        const sidebar = document.querySelector('.admin-sidebar')
        const topbar = document.querySelector('.admin-topbar')
        const style = getComputedStyle(root)
        return {
            sidebarWidth: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : null,
            topbarHeight: topbar ? Math.round(topbar.getBoundingClientRect().height) : null,
            panelBg: style.getPropertyValue('--admin-panel').trim(),
            pageBg: style.getPropertyValue('--admin-bg').trim(),
            accent: style.getPropertyValue('--admin-accent').trim(),
            currentNav: document.querySelectorAll('.admin-sidebar a.is-current').length,
            ariaCurrent: document.querySelectorAll('.admin-sidebar a[aria-current="page"]').length
        }
    })
    report.pages.push({ label, path, ...metrics })
    await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: true })
}

// 4) 深色主题下的总览
await page.goto(`${base}/admin`, { waitUntil: 'domcontentloaded' })
await page.locator('.admin-main').waitFor()
await page.selectOption('.admin-theme select', 'dark')
await page.waitForTimeout(500)
report.darkThemeAttribute = await page.evaluate(() => document.documentElement.dataset.theme)
await page.screenshot({ path: `${outDir}/10-admin-overview-dark.png`, fullPage: true })

// 5) 移动端
await page.setViewportSize({ width: 375, height: 900 })
await page.selectOption('.admin-theme select', 'light')
await page.waitForTimeout(500)
report.mobile = await page.evaluate(() => ({
    theme: document.documentElement.dataset.theme,
    horizontalOverflow: document.documentElement.scrollWidth - window.innerWidth
}))
await page.screenshot({ path: `${outDir}/11-admin-overview-mobile.png`, fullPage: true })

report.errors = errors.slice(0, 15)
console.log(JSON.stringify(report, null, 2))
await browser.close()
