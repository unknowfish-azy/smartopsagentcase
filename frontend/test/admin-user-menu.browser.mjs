// 管理台用户菜单（AdminLayout .admin-user）交互契约回归。
//
// 背景：菜单曾是纯 :hover 实现（display:none + top:calc(100% + 8px)），芯片与菜单之间
// 有 8px 鼠标死区，用户移向菜单时中途 mouseleave → 菜单闪烁消失，退出登录/返回用户层
// 根本点不中。现改为点击开关（userMenuOpen 单一数据源 + 外部点击/Esc/路由关闭）。
//
// 覆盖：默认关闭 → 点击打开 → 鼠标往复移动不闪掉 → 外部点击关闭 → Esc 关闭且焦点归位 →
//       退出登录（POST /api/auth/logout + 同源 SPA 跳登录页 ?portal=admin）→
//       返回用户层（登出 + 跨门户整页导航到用户层登录页）→ 375px 移动端可开可点且无横向溢出。
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

// 门户端口解析到本测试服务器：跨门户切换（location.assign）才能落在同一个 dev server 上，
// 由 /admin → admin.html、/login → index.html 两个入口分流，无需真的再起一个用户层服务。
process.env.VITE_SMARTOPS_USER_PORT = '5191'
process.env.VITE_SMARTOPS_ADMIN_PORT = '5191'
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5191, strictPort: true }, logLevel: 'error' })
await server.listen()
const base = 'http://127.0.0.1:5191'
const artifacts = new URL('../test-artifacts/admin-user-menu/', import.meta.url)
await mkdir(artifacts, { recursive: true })
const browser = await chromium.launch({ channel: 'msedge', headless: true })
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
    if (url.pathname === '/api/auth/login') { user = { id: 1, username: 'root', role: 'admin', portal: 'admin', mustChangePassword: false }; return reply(user) }
    if (url.pathname === '/api/auth/logout') { user = null; return reply({ reauthenticate: true }) }
    if (url.pathname === '/api/admin/overview') return reply({ usersTotal: 3, usersEnabled: 3, adminsEnabled: 1, activeSessions: 1, recentFailures: 0, pendingPasswordChanges: 0 })
    return reply({ items: [], total: 0 })
  })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))
  await page.addInitScript(() => localStorage.setItem('smartops_theme', 'light'))
  await page.goto(`${base}/login?portal=admin`)
  await page.getByPlaceholder('输入运维账号').fill('root')
  await page.getByPlaceholder('输入访问密码').fill('mock-only-password')
  await page.getByRole('button', { name: '进入智维Agent' }).click()
  await page.locator('.admin-layout').waitFor()
  const trigger = page.locator('.admin-user-trigger')
  const menu = page.locator('.admin-user-menu')

  // 1) 默认关闭
  check(await trigger.getAttribute('aria-expanded') === 'false', '默认 aria-expanded=false')
  check(await menu.isVisible() === false, '默认菜单不可见')

  // 2) 点击打开
  await trigger.click()
  check(await trigger.getAttribute('aria-expanded') === 'true', '点击后 aria-expanded=true')
  check(await menu.isVisible() === true, '点击后菜单可见')
  check(await menu.getByRole('button', { name: '返回用户层（重新登录）' }).isVisible(), '返回用户层按钮可见')
  check(await menu.getByRole('button', { name: '退出登录', exact: true }).isVisible(), '退出登录按钮可见')
  await page.screenshot({ path: fileURLToPath(new URL('menu-open-light.png', artifacts)) })
  // 深色主题同样截图（菜单用令牌着色，深浅双主题都应正常）
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; document.documentElement.style.colorScheme = 'dark' })
  await page.screenshot({ path: fileURLToPath(new URL('menu-open-dark.png', artifacts)) })
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; document.documentElement.style.colorScheme = 'light' })

  // 3) 防闪掉：鼠标在芯片→菜单之间往复穿行 + 悬停别处再回来，菜单必须保持打开
  await page.mouse.move(0, 0)
  for (const point of [[700, 30], [700, 60], [700, 100], [700, 130], [700, 30], [400, 400], [700, 100]]) {
    await page.mouse.move(point[0], point[1])
    await page.waitForTimeout(60)
  }
  check(await menu.isVisible() === true, '鼠标往复移动后菜单不闪掉（旧 hover 实现在此消失）')

  // 4) 外部点击关闭
  await page.mouse.click(400, 500)
  check(await menu.isVisible() === false, '外部点击后菜单关闭')

  // 5) Esc 关闭
  await trigger.click()
  check(await menu.isVisible() === true, '再次点击打开')
  await page.keyboard.press('Escape')
  check(await menu.isVisible() === false, 'Escape 后菜单关闭')
  check(await page.evaluate(() => document.activeElement?.classList.contains('admin-user-trigger')), 'Escape 后焦点回到触发器')

  // 6) 退出登录：POST /api/auth/logout + 同源 SPA 跳转登录页（管理员层）
  await trigger.click()
  await menu.getByRole('button', { name: '退出登录', exact: true }).click()
  await page.locator('.login-form').waitFor()
  check(calls.some(call => call.path === '/api/auth/logout' && call.method === 'POST'), '退出登录发出 POST /api/auth/logout')
  check(new URL(page.url()).searchParams.get('portal') === 'admin', '退出后落在登录页 ?portal=admin')

  // 7) 返回用户层：登出 + 跨门户整页导航到用户层入口登录页
  await page.goto(`${base}/login?portal=admin`)
  await page.getByPlaceholder('输入运维账号').fill('root')
  await page.getByPlaceholder('输入访问密码').fill('mock-only-password')
  await page.getByRole('button', { name: '进入智维Agent' }).click()
  await page.locator('.admin-layout').waitFor()
  await trigger.click()
  await menu.getByRole('button', { name: '返回用户层（重新登录）' }).click()
  await page.locator('.login-form').waitFor()
  check(new URL(page.url()).searchParams.get('portal') === 'user', '返回用户层落在用户层登录页 ?portal=user')
  check(await page.getByRole('tab', { name: '用户层', exact: true }).getAttribute('aria-selected') === 'true', '用户层 tab 处于选中态')

  // 8) 移动端 375：菜单可开可点
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto(`${base}/login?portal=admin`)
  await page.getByPlaceholder('输入运维账号').fill('root')
  await page.getByPlaceholder('输入访问密码').fill('mock-only-password')
  await page.getByRole('button', { name: '进入智维Agent' }).click()
  await page.locator('.admin-layout').waitFor()
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
