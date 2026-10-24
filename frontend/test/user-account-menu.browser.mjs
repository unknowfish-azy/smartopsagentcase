// 用户层个人账户菜单（MainLayout .account-menu）交互契约回归。
//
// 背景：退出登录原来埋在侧栏底部 .system-status，顶栏只有裸的「账户安全」链接。
// 用户要求把退出登录收进顶栏「个人账户」小窗口（对齐管理台用户菜单），且点击后
// 不能闪掉。管理台旧菜单的教训：纯 :hover + 8px 死区 → 移向菜单途中 mouseleave
// → 菜单 display:none 复现 → 点不中；项目契约另禁止 pointerenter/leave/focus-within
// 驱动浮层（sidebar-manual-toggle.test.mjs）。故用点击开关：userMenuOpen 单一数据源。
//
// 覆盖：默认关闭 → 点击打开 → 鼠标往复穿行不闪掉 → 外部点击关闭 → Esc 关闭且焦点归位 →
//       路由切换关闭 → 退出登录（POST /api/auth/logout + 同源 SPA 跳登录页 ?redirect=/）→
//       375px 移动端可开可点且无横向溢出。
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

// 两层前端拆分：默认 dev server 对 /admin 返回 admin.html、其余路径返回 index.html。
// 把两个门户端口都解析到本测试服务器，跨门户 location.assign 才能落在同一个源上。
process.env.VITE_SMARTOPS_USER_PORT = '5205'
process.env.VITE_SMARTOPS_ADMIN_PORT = '5205'
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5205, strictPort: true }, logLevel: 'error' })
await server.listen()
const base = 'http://127.0.0.1:5205'
const artifacts = new URL('../test-artifacts/user-account-menu/', import.meta.url)
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', headless: true })
const failures = []
const check = (passed, message) => { console.log((passed ? 'PASS' : 'FAIL') + ' ' + message); if (!passed) failures.push(message) }
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  let user = null
  const calls = []
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin !== base) return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    calls.push({ path: url.pathname, method: route.request().method() })
    const reply = (data, status = 200) => route.fulfill({ status, json: { code: status, message: 'success', data } })
    if (url.pathname === '/api/auth/session') return reply({ user, csrfToken: 'mock-csrf' })
    if (url.pathname === '/api/auth/human-verification') return reply({ enabled: false, available: true, required: false, provider: 'none', action: url.searchParams.get('action') })
    if (url.pathname === '/api/auth/registration') return reply({ enabled: true, usernameMinLength: 3, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 })
    if (url.pathname === '/api/auth/login') { user = { id: 11, username: 'ops-user', role: 'operator', portal: 'user', mustChangePassword: false }; return reply(user) }
    if (url.pathname === '/api/auth/logout') { user = null; return reply({ reauthenticate: true }) }
    if (url.pathname === '/api/diagnostics/health') return reply({ scope: 'user', checks: [{ id: 'authorized-targets', label: '授权诊断目标', status: 'HEALTHY', scope: 'user', checkKind: 'CONFIGURATION', checkedAt: new Date().toISOString(), durationMs: 0, summary: '授权目标已配置', nextAction: '手动检查' }] })
    if (url.pathname === '/api/diagnostics/targets') return reply([{ id: 'web', label: 'Web API', scheme: 'https' }])
    return reply({ items: [], total: 0 })
  })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.addInitScript(() => localStorage.setItem('smartops_theme', 'dark'))
  await page.goto(`${base}/login`)
  await page.getByPlaceholder('输入运维账号').fill('ops-user')
  await page.getByPlaceholder('输入访问密码').fill('mock-only-password')
  await page.getByRole('button', { name: '进入智维Agent' }).click()
  await page.locator('.account-menu-trigger').waitFor()
  await page.goto(`${base}/health`, { waitUntil: 'networkidle' })
  await page.locator('.account-menu-trigger').waitFor()
  const trigger = page.locator('.account-menu-trigger')
  const menu = page.locator('.account-menu-dropdown')

  // 1) 默认关闭
  check(await trigger.getAttribute('aria-expanded') === 'false', '默认 aria-expanded=false')
  check(await menu.isVisible() === false, '默认菜单不可见')
  check((await trigger.innerText()).includes('个人账户'), '触发器标签为「个人账户」')

  // 2) 点击打开
  await trigger.click()
  check(await trigger.getAttribute('aria-expanded') === 'true', '点击后 aria-expanded=true')
  check(await menu.isVisible() === true, '点击后菜单可见')
  check(await menu.getByRole('link', { name: '账户安全', exact: true }).isVisible(), '账户安全入口可见')
  check(await menu.getByRole('button', { name: '管理入口（重新登录）' }).isVisible(), '管理入口按钮可见')
  check(await menu.getByRole('button', { name: '退出登录', exact: true }).isVisible(), '退出登录按钮可见')
  check(await menu.locator('.account-menu-header strong').innerText() === 'ops-user', '菜单头部显示当前用户名')
  // 防裁切：下拉按钮中心点的命中目标必须是按钮本身。lggc 包给顶栏设过 overflow:hidden，
  // 面板被裁后 elementFromPoint 会落到页面内容上——桌面端菜单看得见的位置点不中。
  const hit = await page.evaluate(() => {
    const button = [...document.querySelectorAll('.account-menu-dropdown button')].find(element => element.textContent.trim() === '退出登录')
    const rect = button.getBoundingClientRect()
    const top = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
    return top === button || button.contains(top)
  })
  check(hit === true, '退出登录按钮中心可命中（面板未被顶栏 overflow 裁切）')
  await page.screenshot({ path: fileURLToPath(new URL('menu-open-dark.png', artifacts)) })
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; document.documentElement.style.colorScheme = 'light' })
  await page.screenshot({ path: fileURLToPath(new URL('menu-open-light.png', artifacts)) })
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; document.documentElement.style.colorScheme = 'dark' })

  // 3) 防闪掉：鼠标在芯片→菜单之间往复穿行 + 悬停别处再回来，菜单必须保持打开
  await page.mouse.move(0, 0)
  for (const point of [[900, 30], [900, 60], [900, 100], [900, 140], [900, 60], [500, 500], [900, 100]]) {
    await page.mouse.move(point[0], point[1])
    await page.waitForTimeout(60)
  }
  check(await menu.isVisible() === true, '鼠标往复移动后菜单不闪掉（旧 hover 实现在此消失）')

  // 4) 外部点击关闭
  await page.mouse.click(500, 600)
  check(await menu.isVisible() === false, '外部点击后菜单关闭')

  // 5) Esc 关闭且焦点归位
  await trigger.click()
  check(await menu.isVisible() === true, '再次点击打开')
  await page.keyboard.press('Escape')
  check(await menu.isVisible() === false, 'Escape 后菜单关闭')
  check(await page.evaluate(() => document.activeElement?.classList.contains('account-menu-trigger')), 'Escape 后焦点回到触发器')

  // 6) 路由切换关闭：点「账户安全」导航后菜单应收起
  await trigger.click()
  await menu.getByRole('link', { name: '账户安全', exact: true }).click()
  await page.waitForURL(/\/account\/security/)
  check(await menu.isVisible() === false, '路由切换后菜单关闭')

  // 7) 退出登录：POST /api/auth/logout + 同源 SPA 跳转登录页 ?redirect=/
  await page.goto(`${base}/health`, { waitUntil: 'networkidle' })
  await trigger.click()
  await menu.getByRole('button', { name: '退出登录', exact: true }).click()
  await page.locator('.login-form').waitFor()
  check(calls.some(call => call.path === '/api/auth/logout' && call.method === 'POST'), '退出登录发出 POST /api/auth/logout')
  check(new URL(page.url()).searchParams.get('redirect') === '/', '退出后落在登录页 ?redirect=/')

  // 8) 移动端 375：菜单可开可点
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto(`${base}/login`)
  await page.getByPlaceholder('输入运维账号').fill('ops-user')
  await page.getByPlaceholder('输入访问密码').fill('mock-only-password')
  await page.getByRole('button', { name: '进入智维Agent' }).click()
  await page.locator('.account-menu-trigger').waitFor()
  await page.goto(`${base}/health`, { waitUntil: 'networkidle' })
  await trigger.click()
  check(await menu.isVisible() === true, '375px 下菜单可打开')
  check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), '375px 下无横向溢出')
  await page.screenshot({ path: fileURLToPath(new URL('menu-open-mobile.png', artifacts)) })
  await menu.getByRole('button', { name: '退出登录', exact: true }).click()
  await page.locator('.login-form').waitFor()
  check(true, '375px 下可点中退出登录')

  check(pageErrors.length === 0, '无页面级运行时错误' + (pageErrors.length ? '：' + pageErrors.join('；') : ''))
  console.log(failures.length ? `FAIL ${failures.length} 项` : 'ALL PASS')
} finally {
  await browser.close()
  await server.close()
}
process.exit(failures.length ? 1 : 0)
