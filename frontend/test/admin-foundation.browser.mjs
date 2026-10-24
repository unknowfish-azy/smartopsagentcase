import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer } from 'vite'

// 两层前端拆分后，默认配置的 dev server 对 /admin 返回 admin.html（管理员层应用）、
// 对其他路径返回 index.html（用户层应用）。把两个门户端口都解析到本次测试服务器，
// 门户切换（location.assign）就落在同一个 dev server 上，由各自的入口 HTML 分流，
// 无需真的再起一个用户层服务。
process.env.VITE_SMARTOPS_USER_PORT = '5187'
process.env.VITE_SMARTOPS_ADMIN_PORT = '5187'
const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5187, strictPort: true } })
await server.listen()
const base = 'http://127.0.0.1:5187'
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const artifacts = new URL('../test-artifacts/admin-foundation/', import.meta.url)
await mkdir(artifacts, { recursive: true })
let user = null, failUsers = false, lastAdmin = false, failPassword = false, csrf = 'mock-csrf-1'
const calls = [], errors = []
const visualChecks = [], visualFailures = []
const checkVisual = (passed, message, details = {}) => {
  visualChecks.push({ passed, message, ...details })
  if (!passed) visualFailures.push(message)
}
const readContrast = (locator, pseudo = null) => locator.evaluate((element, pseudo) => {
  const parse = color => {
    const channels = color.match(/[\d.]+/g).map(Number)
    return [...channels.slice(0, 3), channels[3] ?? 1]
  }
  const composite = (foreground, background) => foreground.slice(0, 3).map((channel, index) => channel * foreground[3] + background[index] * (1 - foreground[3]))
  const luminance = color => color.map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0)
  const ancestors = []
  for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) ancestors.unshift(ancestor)
  let backgrounds = [[255, 255, 255]]
  for (const ancestor of ancestors) {
    const style = getComputedStyle(ancestor)
    backgrounds = backgrounds.map(background => composite(parse(style.backgroundColor), background))
    if (style.backgroundImage !== 'none') {
      const layers = style.backgroundImage.match(/(?:linear|radial)-gradient\((?:[^()]|\([^()]*\))*\)/g) || []
      if (!layers.length) throw new Error('Unsupported computed background: ' + style.backgroundImage)
      for (const layer of layers.reverse()) {
        const stops = [...layer.matchAll(/rgba?\([^)]+\)/g)].map(match => parse(match[0]))
        if (!stops.length) throw new Error('Missing computed gradient stops: ' + layer)
        backgrounds = backgrounds.flatMap(background => stops.map(stop => composite(stop, background)))
      }
    }
  }
  const style = getComputedStyle(element, pseudo)
  const foreground = parse(style.color)
  foreground[3] *= Number(style.opacity)
  const ratios = backgrounds.map(background => {
    const backgroundLight = luminance(background), foregroundLight = luminance(composite(foreground, background))
    return (Math.max(backgroundLight, foregroundLight) + .05) / (Math.min(backgroundLight, foregroundLight) + .05)
  })
  return { ratio: Math.min(...ratios), color: style.color, backgrounds }
}, pseudo)
const finishTransitions = page => page.evaluate(() => document.getAnimations().filter(animation => animation.constructor.name === 'CSSTransition').forEach(animation => animation.finish()))
const checkMobileSessions = async (page, label) => {
  const wrapper = page.locator('.admin-table-wrap')
  const metrics = await wrapper.evaluate(element => {
    const singleLine = target => {
      const range = document.createRange()
      range.selectNodeContents(target)
      return range.getClientRects().length === 1
    }
    return { scrollWidth: element.scrollWidth, clientWidth: element.clientWidth, tableWidth: element.querySelector('table').getBoundingClientRect().width, badgeSingleLine: singleLine(element.querySelector('.admin-badge')), actionSingleLine: singleLine(element.querySelector('tbody button')) }
  })
  checkVisual(metrics.scrollWidth > metrics.clientWidth && metrics.tableWidth >= 900 && metrics.badgeSingleLine && metrics.actionSingleLine, label + ': uncompressed session table and labels', metrics)
  const hint = page.getByText('左右滑动查看完整列表及操作；键盘可聚焦列表后使用左右方向键。', { exact: true })
  checkVisual(await hint.isVisible(), label + ': visible horizontal scroll guidance')
  if (await hint.isVisible()) checkVisual(await wrapper.getAttribute('aria-describedby') === await hint.getAttribute('id'), label + ': scroll guidance associated with table')
  if (metrics.scrollWidth > metrics.clientWidth) {
    await wrapper.focus()
    await page.keyboard.press('ArrowRight')
    await page.waitForFunction(() => document.querySelector('.admin-table-wrap').scrollLeft > 0)
    await wrapper.evaluate(element => { element.scrollLeft = element.scrollWidth })
    const action = page.getByRole('row').filter({ hasText: '当前会话' }).getByRole('button', { name: '撤销会话' })
    const bounds = await action.boundingBox(), viewport = await wrapper.boundingBox()
    checkVisual(bounds.x >= viewport.x && bounds.x + bounds.width <= viewport.x + viewport.width, label + ': revoke reachable after scrolling')
    await action.click()
    await page.getByRole('dialog').getByText(/这是当前会话/).waitFor()
    await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
    await page.evaluate(() => document.activeElement?.blur())
    await page.screenshot({ path: fileURLToPath(new URL(label + '-scrolled.png', artifacts)), fullPage: true })
    await wrapper.evaluate(element => { element.scrollLeft = 0 })
  }
}
const checkLoginContrast = async (page, label) => {
  const measure = async (selector, state, pseudo = null) => {
    await finishTransitions(page)
    const details = await readContrast(page.locator(selector), pseudo)
    checkVisual(details.ratio >= 4.5, label + ' ' + selector + ' ' + state + ': ' + details.ratio.toFixed(2) + ':1 (minimum 4.5:1)', details)
  }
  for (const selector of ['input[autocomplete="username"]', 'input[autocomplete="current-password"]']) {
    await measure(selector, 'placeholder', '::placeholder')
    await page.locator(selector).focus()
    await measure(selector, 'focused placeholder', '::placeholder')
    await page.locator(selector).fill('contrast-mock-only')
    await measure(selector, 'entered text')
    await page.locator(selector).fill('')
    await page.locator(selector).blur()
  }
  for (const selector of ['.login-form__footer', '.login-form__options .login-form__policy', '.login-submit']) await measure(selector, 'default')
  await page.locator('.login-submit').hover()
  await measure('.login-submit', 'hover')
  await page.mouse.move(0, 0)
  await page.locator('.login-submit').focus()
  await measure('.login-submit', 'focus')
  await page.locator('.login-submit').blur()
}
const checkMobileUsers = async (page, label) => {
  const wrapper = page.locator('.admin-table-wrap')
  const metrics = await wrapper.evaluate(element => {
    const cell = [...element.querySelectorAll('tbody td:first-child')].find(cell => cell.textContent === 'operator-1')
    const range = document.createRange()
    range.selectNodeContents(cell)
    return { scrollWidth: element.scrollWidth, clientWidth: element.clientWidth, tableWidth: element.querySelector('table').getBoundingClientRect().width, nameLines: range.getClientRects().length }
  })
  checkVisual(metrics.scrollWidth > metrics.clientWidth && metrics.tableWidth >= 900 && metrics.nameLines === 1, label + ': uncompressed account table', metrics)
  const hint = page.getByText('左右滑动查看完整列表及操作；键盘可聚焦列表后使用左右方向键。', { exact: true })
  checkVisual(await hint.isVisible(), label + ': visible horizontal scroll guidance')
  if (await hint.isVisible()) {
    const contrast = await readContrast(hint)
    checkVisual(contrast.ratio >= 4.5, label + ': scroll guidance contrast ' + contrast.ratio.toFixed(2) + ':1', contrast)
    checkVisual(await wrapper.getAttribute('aria-describedby') === await hint.getAttribute('id'), label + ': scroll guidance associated with table')
  }
  if (metrics.scrollWidth > metrics.clientWidth) {
    await wrapper.focus()
    await page.keyboard.press('ArrowRight')
    await page.waitForFunction(() => document.querySelector('.admin-table-wrap').scrollLeft > 0)
    await wrapper.evaluate(element => { element.scrollLeft = element.scrollWidth })
    // 先一次性测量三个按钮的可达性：Playwright 的 click() 自带 scrollIntoViewIfNeeded，
    // 会把容器横向滚动带偏（实测 605→424），混在循环里会让后两个按钮测到错位几何。
    for (const name of ['禁用', '变更角色', '重置密码']) {
      const action = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'operator-1', exact: true }) }).getByRole('button', { name, exact: true })
      const bounds = await action.boundingBox(), viewport = await wrapper.boundingBox()
      checkVisual(bounds.x >= viewport.x && bounds.x + bounds.width <= viewport.x + viewport.width, label + ': ' + name + ' reachable after scrolling')
    }
    for (const name of ['禁用', '变更角色', '重置密码']) {
      const action = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'operator-1', exact: true }) }).getByRole('button', { name, exact: true })
      await action.click()
      await page.getByRole('dialog').waitFor()
      await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
    }
  }
  await page.evaluate(() => document.activeElement?.blur())
  await page.screenshot({ path: fileURLToPath(new URL(label + '-scrolled.png', artifacts)), fullPage: true })
  await wrapper.evaluate(element => { element.scrollLeft = 0 })
  await wrapper.focus()
  await page.keyboard.press('Tab')
  checkVisual(await page.locator('tbody .admin-actions button').first().evaluate(element => element === document.activeElement), label + ': keyboard reaches first action')
  await page.keyboard.press('Enter')
  await page.getByRole('dialog').waitFor()
  await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click()
  await wrapper.evaluate(element => { element.scrollLeft = 0 })
}
const users = Array.from({ length: 23 }, (_, index) => ({ id: index + 1, username: index === 0 ? 'root' : `operator-${index}`, role: index === 0 ? 'admin' : 'operator', enabled: true, mustChangePassword: false, createdAt: '2026-10-01T08:00:00Z' }))
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin !== base) return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const method = route.request().method(), body = route.request().postDataJSON(), path = url.pathname
    calls.push({ path, method, body, query: url.searchParams.toString() })
    const reply = (data, status = 200, message = 'success') => route.fulfill({ status, json: { code: status, message, data } })
    if (method !== 'GET') assert.equal(route.request().headers()['x-csrf-token'], csrf)
    if (path === '/api/auth/registration') return reply({ enabled: true, usernameMinLength: 3, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 })
    if (path === '/api/auth/human-verification') return reply({ enabled: false, available: true, required: false, provider: 'none', action: url.searchParams.get('action') })
    if (path === '/api/auth/session') return reply({ user, csrfToken: csrf })
    if (path === '/api/auth/login') {
      if (body.username === 'operator' && body.portal === 'admin') return reply(null, 403, '仅管理员可进入管理层')
      user = { id: 1, username: body.username, role: body.username === 'operator' ? 'operator' : 'admin', portal: body.portal, mustChangePassword: body.username === 'forced', authVersion: 1 }
      csrf = `mock-csrf-${calls.length}`
      return reply(user)
    }
    if (path === '/api/auth/password' && failPassword) return reply(null, 400, '当前密码不正确')
    if (path === '/api/auth/logout' || path === '/api/auth/password') { user = null; return reply({ reauthenticate: true }) }
    if (!user) return reply(null, 401, '登录已失效')
    if (user.mustChangePassword) return reply(null, 403, '必须修改密码')
    if (path.startsWith('/api/admin/') && (user.role !== 'admin' || user.portal !== 'admin')) return reply(null, 403, '管理入口受限')
    if (path.startsWith('/api/admin/') && method !== 'GET') assert.equal(route.request().headers()['x-admin-password'], 'mock-admin-verification-only')
    if (path === '/api/admin/registration') return reply({ enabled: true, usernameMinLength: 3, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 })
    if (path === '/api/admin/overview') return reply({ usersTotal: users.length, usersEnabled: 23, adminsEnabled: 1, activeSessions: 2, recentFailures: 3, pendingPasswordChanges: 4 })
    if (path === '/api/admin/users' && method === 'GET') {
      if (failUsers) return reply(null, 503, '模拟列表不可用')
      const page = Number(url.searchParams.get('page')), pageSize = Number(url.searchParams.get('pageSize'))
      assert.ok(page > 0 && pageSize > 0, 'paginated endpoint required')
      const filtered = users.filter(account => account.username.includes(url.searchParams.get('q') || '') && (!url.searchParams.get('role') || account.role === url.searchParams.get('role')) && (!url.searchParams.get('enabled') || String(account.enabled) === url.searchParams.get('enabled')))
      return reply({ items: filtered.slice((page - 1) * pageSize, page * pageSize), total: filtered.length, page, pageSize })
    }
    if (path === '/api/admin/users' && method === 'POST') {
      const account = { id: users.length + 1, username: body.username, role: body.role, enabled: true, mustChangePassword: true }
      users.push(account); return reply(account)
    }
    if (/\/api\/admin\/users\/\d+$/.test(path) && method === 'PUT') {
      if (lastAdmin) return reply(null, 409, '不能禁用或降权最后一个启用管理员')
      const account = users.find(item => item.id === Number(path.split('/').at(-1)))
      Object.assign(account, body); return reply(account)
    }
    if (path.endsWith('/reset-password')) {
      if (body.password === 'same-as-old-mock') return reply(null, 400, '新密码不能与旧密码相同')
      if (path === '/api/admin/users/1/reset-password') user = null
      return reply({ reauthenticate: true })
    }
    if (path === '/api/admin/sessions') return reply({ items: [{ id: 'public-session-id', userId: 2, username: 'operator-1', portal: 'user', createdAt: '2026-10-01T08:00:00Z', lastSeenAt: '2026-10-01T09:00:00Z', current: false }, { id: 'current-public-id', userId: 1, username: user.username, portal: 'admin', current: true }] })
    if (path.startsWith('/api/admin/sessions/') && method === 'DELETE') { if (path.endsWith('/current-public-id')) user = null; return reply(null) }
    if (path === '/api/admin/audit') return reply({ items: [{ id: 1, actorId: 1, actorUsername: '<img src=x onerror=alert(1)>', action: 'LOGIN', targetId: 1, outcome: 'SUCCESS', createdAt: '2026-10-01T08:00:00Z' }], total: 1, page: 1, pageSize: 20 })
    if (path === '/api/admin/readiness') return reply({ unavailableTables: [], internalAuthenticationConfigured: false, observability: [], harbor: { configured: false } })
    // 服务接入页的策略区（含对比度检查用的 .admin-muted）由诊断接口的 policy 驱动
    if (path === '/api/diagnostics/admin/health') return reply({ policy: { targetCount: 4, perUserConcurrency: 2, globalConcurrency: 8, connectTimeoutMs: 5000, readTimeoutMs: 15000, maxResponseBytes: 1048576, miniConfigured: true, observabilityConfigured: false, harborConfigured: false }, checks: [] })
    return reply(null, 503, 'mock boundary: unsupported endpoint')
  })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => { localStorage.setItem('smartops_theme', 'light'); localStorage.setItem('smartops_preview_auth', JSON.stringify({ role: 'admin', portal: 'admin' })) })
  const button = name => page.getByRole('button', { name, exact: true })
  const confirm = async name => {
    await page.getByRole('dialog').getByLabel('当前管理员密码', { exact: true }).fill('mock-admin-verification-only')
    await page.getByRole('dialog').getByRole('button', { name, exact: true }).click()
  }
  const login = async (username, portal) => {
    await page.goto(`${base}/login`)
    await page.getByRole('tab', { name: portal === 'admin' ? '管理员层' : '用户层', exact: true }).click()
    await page.getByPlaceholder('输入运维账号').fill(username)
    await page.getByPlaceholder('输入访问密码').fill('mock-only-password')
    await button('进入智维Agent').click()
  }
  await page.goto(`${base}/admin`)
  await page.locator('.login-form').waitFor()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      for (const portal of ['用户层', '管理员层']) {
        await page.getByRole('tab', { name: portal, exact: true }).click()
        // 跨门户切换是整页导航（两个入口各自加载 HTML），落地后要重新套主题
        await page.locator('.login-form').waitFor()
        await page.evaluate(theme => { document.documentElement.dataset.theme = theme; document.documentElement.style.colorScheme = theme }, theme)
        assert.equal(await page.getByRole('tab', { name: portal, exact: true }).getAttribute('aria-selected'), 'true')
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
        if (theme === 'light') await checkLoginContrast(page, 'login-' + portal + '-' + theme + '-' + width)
        await page.screenshot({ path: fileURLToPath(new URL(`login-${portal === '用户层' ? 'user' : 'admin'}-${theme}-${width}.png`, artifacts)), fullPage: true })
      }
    }
  }
  await login('operator', 'admin')
  await page.getByRole('alert').filter({ hasText: '仅管理员' }).waitFor()
  await login('root', 'admin')
  await page.locator('.admin-layout').waitFor()
  assert.equal(new URL(page.url()).pathname, '/admin')
  await page.getByRole('link', { name: '账户管理', exact: true }).click()
  await page.getByRole('cell', { name: 'operator-1', exact: true }).waitFor()
  await button('下一页').click()
  await page.getByRole('cell', { name: 'operator-22', exact: true }).waitFor()
  await page.getByLabel('每页条数').selectOption('50')
  await page.getByRole('cell', { name: 'operator-1', exact: true }).waitFor()
  assert.equal(await page.locator('tbody tr').count(), 23)
  await page.getByLabel('每页条数').selectOption('20')
  await page.getByLabel('搜索账号', { exact: true }).fill('operator-1')
  await button('查询').click()
  const row = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'operator-1', exact: true }) })
  await row.waitFor()
  assert.equal(await page.getByRole('button', { name: '上一页', exact: true }).isDisabled(), true)
  await button('新增账号').click()
  await page.getByRole('dialog').getByLabel('账号', { exact: true }).fill('created-mock')
  await page.getByRole('dialog').getByLabel('初始密码', { exact: true }).fill('temporary-mock-only')
  await confirm('创建账号')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.ok(calls.some(call => call.method === 'POST' && call.path === '/api/admin/users' && call.body.username === 'created-mock'))
  await row.getByRole('button', { name: '禁用', exact: true }).click()
  await page.getByRole('dialog').getByText(/旧会话.*终端/).waitFor()
  await confirm('取消')
  assert.equal(calls.filter(call => call.method === 'PUT').length, 0)
  await row.getByRole('button', { name: '禁用', exact: true }).click()
  await confirm('确认变更')
  await row.getByRole('button', { name: '启用', exact: true }).waitFor()
  await row.getByRole('button', { name: '变更角色', exact: true }).click()
  await page.getByRole('dialog').getByLabel('新角色').selectOption('admin')
  await confirm('确认变更')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await row.getByRole('button', { name: '重置密码', exact: true }).click()
  await page.getByRole('dialog').getByLabel('临时密码').fill('same-as-old-mock')
  await confirm('确认重置')
  await page.getByRole('dialog').getByRole('alert').filter({ hasText: '新密码不能与旧密码相同' }).waitFor()
  await page.getByRole('dialog').getByLabel('临时密码').fill('reset-mock-only-password')
  await confirm('确认重置')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.ok(calls.some(call => call.path.endsWith('/reset-password')))
  await row.getByRole('button', { name: '重置密码', exact: true }).click()
  assert.equal(await page.getByRole('dialog').getByLabel('临时密码').inputValue(), '')
  await confirm('取消')
  lastAdmin = true
  await row.getByRole('button', { name: '启用', exact: true }).click()
  await confirm('确认变更')
  await page.getByRole('dialog').getByRole('alert').filter({ hasText: '最后一个启用管理员' }).waitFor()
  await confirm('取消'); lastAdmin = false; failUsers = true
  await button('查询').click()
  await page.getByRole('alert').filter({ hasText: '模拟列表不可用' }).waitFor()
  assert.equal(await page.locator('tbody tr').count(), 0)
  failUsers = false
  await button('查询').click(); await row.waitFor()
  await row.getByRole('button', { name: '启用', exact: true }).click()
  await confirm('确认变更')
  await row.getByRole('button', { name: '禁用', exact: true }).waitFor()
  await page.getByLabel('搜索账号', { exact: true }).fill('no-such-account')
  await button('查询').click()
  await page.getByText('没有匹配的账户，请调整查询条件。', { exact: true }).waitFor()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      // 管理台主题是 ☀/☾ 切换按钮（不是下拉框）：按当前实际主题决定是否点一次
      if (await page.evaluate(() => document.documentElement.dataset.theme) !== theme) {
        await page.getByRole('button', { name: /切到(浅色|深色)/ }).click()
      }
      await page.waitForFunction(theme => document.documentElement.dataset.theme === theme, theme)
      for (const path of ['/admin', '/admin/users', '/admin/sessions', '/admin/audit', '/admin/readiness']) {
        await page.getByRole('navigation', { name: '管理导航' }).locator(`a[href="${path}"]`).click()
        await page.locator('.admin-main h1').waitFor()
        await page.getByText(/^正在加载/).waitFor({ state: 'hidden' })
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${path} ${theme} ${width}`)
        assert.equal(await page.locator('.whale-host, .ops-spider-pet, canvas').count(), 0)
        const contrast = await page.evaluate(() => {
          const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0)
          const background = luminance(getComputedStyle(document.querySelector('.admin-layout')).backgroundColor)
          return ['.admin-main h1', '.admin-muted'].map(selector => {
            const foreground = luminance(getComputedStyle(document.querySelector(selector)).color)
            return (Math.max(background, foreground) + .05) / (Math.min(background, foreground) + .05)
          })
        })
        assert.ok(contrast.every(value => value >= 4.5), `${path}: text contrast ${contrast}`)
        await page.screenshot({ path: fileURLToPath(new URL(`${path.split('/').at(-1)}-${theme}-${width}.png`, artifacts)), fullPage: true })
        if (path === '/admin/users' && width === 375) await checkMobileUsers(page, `users-${theme}-${width}`)
        if (path === '/admin/sessions' && width === 375) await checkMobileSessions(page, `sessions-${theme}-${width}`)
        if (width === 375) {
          const sidebarGap = await page.locator('.admin-sidebar').evaluate(element => element.getBoundingClientRect().bottom - element.querySelector('nav').getBoundingClientRect().bottom)
          checkVisual(sidebarGap <= 24, path + ' ' + theme + ': mobile sidebar avoids stretched empty row (' + sidebarGap + 'px)')
        }
      }
    }
  }
  await page.getByRole('link', { name: '审计记录', exact: true }).click()
  await page.getByLabel('搜索审计账号').fill('root')
  await page.getByLabel('审计动作').selectOption('LOGIN')
  await page.getByLabel('审计结果').selectOption('SUCCESS')
  await button('查询').click()
  await page.getByRole('cell', { name: '<img src=x onerror=alert(1)>', exact: true }).waitFor()
  assert.equal(await page.locator('tbody img').count(), 0)
  assert.ok(calls.some(call => call.path === '/api/admin/audit' && call.query.includes('q=root') && call.query.includes('action=LOGIN')))
  await page.getByRole('link', { name: '活动会话', exact: true }).click()
  await page.getByRole('row').filter({ hasText: 'operator-1' }).getByRole('button', { name: '撤销会话' }).click()
  await confirm('确认撤销')
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.ok(calls.some(call => call.method === 'DELETE' && call.path.endsWith('/public-session-id')))
  await page.locator('.admin-user-trigger').click()
  await button('返回用户层（重新登录）').click()
  await page.locator('.login-form').waitFor(); assert.equal(user, null)
  await login('root', 'user'); await page.waitForURL(`${base}/`)
  const boundary = calls.length
  await page.goto(`${base}/admin/users`); await page.waitForURL(url => url.pathname === '/')
  assert.equal(calls.slice(boundary).some(call => call.path.startsWith('/api/admin/')), false)
  assert.equal(await page.getByRole('link', { name: '账户管理', exact: true }).count(), 0)
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `user workspace width ${width}`)
  }
  await page.locator('.account-menu-trigger').click()
  await page.getByRole('link', { name: '账户安全', exact: true }).click()
  await button('退出登录').click(); await page.locator('.login-form').waitFor()
  const forcedStart = calls.length
  await login('forced', 'admin'); await page.waitForURL(`${base}/account/security`)
  await page.goto(`${base}/admin`); await page.waitForURL(`${base}/account/security`)
  assert.equal(calls.slice(forcedStart).some(call => !call.path.startsWith('/api/auth/')), false)
  assert.equal(await page.getByRole('link').count(), 0)
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false)
      await page.screenshot({ path: fileURLToPath(new URL(`security-${theme}-${width}.png`, artifacts)), fullPage: true })
    }
  }
  const passwordRequestsBeforeValidation = calls.filter(call => call.path === '/api/auth/password').length
  await page.getByLabel('当前密码', { exact: true }).fill('mock-only-password')
  await page.getByLabel('新密码', { exact: true }).fill('twelve-chars!')
  await page.getByLabel('确认新密码', { exact: true }).fill('twelve-chars!')
  await button('更新密码并退出').click()
  await page.getByRole('alert').filter({ hasText: '16' }).waitFor()
  await page.getByLabel('新密码', { exact: true }).fill('密'.repeat(25))
  await page.getByLabel('确认新密码', { exact: true }).fill('密'.repeat(25))
  await button('更新密码并退出').click()
  await page.getByRole('alert').filter({ hasText: '72' }).waitFor()
  assert.equal(calls.filter(call => call.path === '/api/auth/password').length, passwordRequestsBeforeValidation)
  await page.getByLabel('新密码', { exact: true }).fill('new-mock-only-password')
  await page.getByLabel('确认新密码', { exact: true }).fill('different')
  await button('更新密码并退出').click()
  await page.getByRole('alert').filter({ hasText: '两次输入' }).waitFor()
  await page.getByLabel('确认新密码', { exact: true }).fill('new-mock-only-password')
  await button('更新密码并退出').click(); await page.locator('.login-form').waitFor()
  assert.equal(user, null)
  assert.equal(await page.evaluate(() => localStorage.getItem('smartops_preview_auth')), null)
  await login('root', 'admin')
  await page.getByRole('link', { name: '活动会话', exact: true }).click()
  await page.getByRole('row').filter({ hasText: '当前会话' }).getByRole('button', { name: '撤销会话' }).click()
  await page.getByRole('dialog').getByText(/这是当前会话/).waitFor()
  await confirm('确认撤销')
  await page.locator('.login-form').waitFor(); assert.equal(user, null)
  await login('root', 'admin')
  await page.getByRole('link', { name: '账户管理', exact: true }).click()
  await page.getByRole('row').filter({ hasText: '本人' }).getByRole('button', { name: '重置密码', exact: true }).click()
  await page.getByRole('dialog').getByText(/这是你当前使用的账号/).waitFor()
  await page.getByRole('dialog').getByLabel('临时密码').fill('self-reset-mock-password')
  await confirm('确认重置')
  await page.locator('.login-form').waitFor(); assert.equal(user, null)
  await login('root', 'admin')
  await page.locator('.admin-user-trigger').click()
  await page.getByRole('link', { name: '账户安全', exact: true }).click()
  await page.getByLabel('当前密码', { exact: true }).fill('wrong-mock')
  await page.getByLabel('新密码', { exact: true }).fill('new-mock-password-16')
  await page.getByLabel('确认新密码', { exact: true }).fill('new-mock-password-16')
  failPassword = true
  await button('更新密码并退出').click()
  await page.getByRole('alert').filter({ hasText: '当前密码不正确' }).waitFor()
  assert.ok(user)
  failPassword = false
  await page.getByLabel('当前密码', { exact: true }).fill('correct-mock')
  await button('更新密码并退出').click()
  await page.locator('.login-form').waitFor(); assert.equal(user, null)
  assert.deepEqual(errors, [])
  await writeFile(new URL('visual-report.json', artifacts), JSON.stringify({ checks: visualChecks, failures: visualFailures }, null, 2))
  assert.deepEqual(visualFailures, [], 'computed contrast and mobile account regression checks')
  console.log(`PASS ${visualChecks.length} computed contrast and mobile account checks; visual-report.json saved`)
  console.log('PASS admin mock: portals, guards, CSRF, password gate, paginated CRUD, confirmations, failures, sessions, audit, 375/1440 light/dark; all API traffic intercepted')
} finally { await browser.close(); await server.close() }
