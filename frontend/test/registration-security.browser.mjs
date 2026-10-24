import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer } from 'vite'

const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5189, strictPort: true }, logLevel: 'error' })
await server.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const artifacts = new URL('../test-artifacts/registration-security/', import.meta.url)
await mkdir(artifacts, { recursive: true })
const policy = { enabled: true, usernameMinLength: 3, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 }
const calls = [], errors = []
const adminPassword = 'mock-admin-verification-only'
let user = null, rejectRegister = 0, rejectAdmin = 0
const accounts = [{ id: 1, username: 'root', role: 'admin', enabled: true, mustChangePassword: false }, { id: 2, username: 'operator', role: 'operator', enabled: true, mustChangePassword: false }]
try {
  const context = await browser.newContext({ reducedMotion: 'reduce', serviceWorkers: 'block' })
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin !== 'http://127.0.0.1:5189') return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method()
    const body = request.postDataJSON(), headers = request.headers()
    calls.push({ path, method, body, adminPassword: headers['x-admin-password'] })
    const reply = (data, status = 200, message = 'success') => route.fulfill({ status, json: { code: status, message, data } })
    if (method !== 'GET') assert.equal(headers['x-csrf-token'], 'mock-csrf')
    if (path === '/api/auth/session') return reply({ user, csrfToken: 'mock-csrf' })
    if (path === '/api/auth/registration') return reply(policy)
    if (path === '/api/auth/human-verification') return reply({ enabled: false, available: true, required: false, provider: 'none', action: new URL(request.url()).searchParams.get('action') })
    if (path === '/api/auth/register') {
      assert.deepEqual(Object.keys(body).sort(), ['confirmPassword', 'humanToken', 'password', 'username'])
      if (rejectRegister) return reply(null, rejectRegister, rejectRegister === 409 ? '账号已存在' : rejectRegister === 429 ? '注册过于频繁，请稍后再试' : '注册已关闭')
      const account = { id: 3, username: body.username, role: 'operator', enabled: true, mustChangePassword: false }
      accounts.push(account)
      return reply(account)
    }
    if (path === '/api/auth/login') {
      const account = accounts.find(account => account.username === body.username)
      if (!account || account.role !== 'admin' && body.portal === 'admin') return reply(null, 403, '仅管理员可进入管理层')
      user = { ...account, portal: body.portal, authVersion: 1 }
      return reply(user)
    }
    if (path === '/api/auth/logout') { user = null; return reply(null) }
    if (!user) return reply(null, 401, '登录已失效')
    if (path.startsWith('/api/admin/') && (user.role !== 'admin' || user.portal !== 'admin')) return reply(null, 403, '管理入口受限')
    if (path.startsWith('/api/admin/') && method !== 'GET') {
      if (rejectAdmin || headers['x-admin-password'] !== adminPassword) return reply(null, rejectAdmin || 403, rejectAdmin === 429 ? '验证过于频繁，请稍后再试' : '当前管理员密码不正确')
    }
    if (path === '/api/admin/registration') { if (method === 'PUT') policy.enabled = body.enabled; return reply(policy) }
    if (path === '/api/admin/users') {
      if (method === 'POST') { accounts.push({ ...body, id: 4, enabled: true, mustChangePassword: true }); return reply(accounts.at(-1)) }
      return reply({ items: accounts, total: accounts.length, page: 1, pageSize: 20 })
    }
    if (path.startsWith('/api/admin/users/')) return reply({ reauthenticate: true })
    if (path === '/api/admin/sessions') return reply({ items: [{ id: 'session-2', username: 'operator', portal: 'user', current: false }] })
    if (path.startsWith('/api/admin/sessions/')) return reply(null)
    if (path === '/api/admin/overview') return reply({ usersTotal: accounts.length, usersEnabled: accounts.length, adminsEnabled: 1, activeSessions: 1, recentFailures: 0, pendingPasswordChanges: 0 })
    return reply(null, 503, 'mock: unsupported endpoint')
  })
  const page = await context.newPage()
  page.setDefaultTimeout(7000)
  page.on('pageerror', error => { errors.push(error.message); console.error('Browser error:', error.message) })
  const goto = path => page.goto('http://127.0.0.1:5189' + path)
  const button = name => page.getByRole('button', { name, exact: true })
  const alert = text => page.getByRole('alert').filter({ hasText: text }).waitFor()
  const fillRegistration = async (password, confirmation = password) => {
    await page.getByPlaceholder('输入运维账号').fill('new-user')
    await page.getByLabel('密码', { exact: true }).fill(password)
    await page.getByLabel('确认密码', { exact: true }).fill(confirmation)
  }
  const assertNoSecrets = async () => {
    const stored = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))
    for (const secret of [adminPassword, 'valid-user-password', 'target-new-password']) assert.equal(stored.includes(secret), false)
  }
  await goto('/login?portal=admin')
  await page.locator('.login-form').waitFor().catch(async failure => { console.error(await page.locator('body').innerText()); throw failure })
  await page.getByRole('tab', { name: '用户层', exact: true }).click()
  assert.equal(await button('注册普通账号').count(), 1, 'user login offers public registration')
  await button('注册普通账号').click()
  await page.getByRole('heading', { name: '注册普通账号', exact: true }).waitFor()
  assert.equal(await page.locator('.login-form select').count(), 0, 'no self-assigned role selector')
  assert.deepEqual(await page.locator('.login-form [aria-labelledby]').evaluateAll(elements => elements.flatMap(element => element.getAttribute('aria-labelledby').split(/\s+/).filter(id => !document.getElementById(id)))), [], 'registration accessible labels reference existing elements')
  await fillRegistration('weak')
  await button('创建普通账号').click()
  await alert('12')
  await fillRegistration('valid-user-password', 'different-password')
  await button('创建普通账号').click()
  await alert('不一致')
  await fillRegistration('密'.repeat(25))
  await button('创建普通账号').click()
  await alert('72')
  assert.equal(calls.filter(call => call.path === '/api/auth/register').length, 0)
  for (const status of [409, 429, 403]) {
    rejectRegister = status
    await fillRegistration('valid-user-password')
    await button('创建普通账号').click()
    await alert(status === 409 ? '账号已存在' : status === 429 ? '注册过于频繁' : '注册已关闭')
    assert.equal(new URL(page.url()).pathname, '/login')
    assert.equal(user, null)
  }
  rejectRegister = 0
  await fillRegistration('valid-user-password')
  await button('创建普通账号').click()
  await page.getByText('注册成功，请使用新账号登录。', { exact: true }).waitFor()
  assert.equal(await page.getByPlaceholder('输入运维账号').inputValue(), 'new-user')
  assert.equal(await page.getByPlaceholder('输入访问密码').inputValue(), '')
  assert.equal(calls.some(call => call.path === '/api/auth/login'), false)
  await assertNoSecrets()
  await page.reload()
  await page.getByRole('heading', { name: '欢迎回来' }).waitFor()
  assert.equal(await page.getByRole('tab', { name: '用户层', exact: true }).getAttribute('aria-selected'), 'true', 'registration returns to user login even after reload from an admin-entry URL')
  assert.equal(user, null)
  await page.getByPlaceholder('输入运维账号').fill('new-user')
  await page.getByPlaceholder('输入访问密码').fill('valid-user-password')
  await page.getByRole('tab', { name: '管理员层', exact: true }).click()
  assert.equal(await button('注册普通账号').count(), 0)
  await button('进入智维Agent').click()
  await alert('仅管理员')
  await page.getByRole('tab', { name: '用户层', exact: true }).click()
  await page.getByPlaceholder('输入访问密码').fill('valid-user-password')
  await button('进入智维Agent').click()
  await page.waitForURL(url => url.pathname !== '/login')
  assert.equal(user.role, 'operator')
  assert.equal(user.mustChangePassword, false)
  await goto('/admin/users')
  await page.waitForURL(url => url.pathname !== '/admin/users')
  assert.notEqual(new URL(page.url()).pathname, '/admin/users', 'operator cannot enter admin UI')
  user = null
  policy.enabled = false
  await goto('/login')
  await page.getByText('普通账号注册已关闭，请联系管理员。', { exact: true }).waitFor()
  assert.equal(await button('注册普通账号').isEnabled(), false)
  policy.enabled = true
  for (const width of [375, 1440]) for (const theme of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 })
    await page.evaluate(theme => localStorage.setItem('smartops_theme', theme), theme)
    await page.reload()
    await button('注册普通账号').click()
    await fillRegistration('valid-user-password')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
    const contrast = await button('返回登录').evaluate(element => {
      const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0)
      const style = getComputedStyle(element), foreground = luminance(style.color), background = luminance(style.backgroundColor)
      return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05)
    })
    assert.ok(contrast >= 4.5, 'registration secondary action contrast: ' + theme + ' ' + contrast)
    await page.screenshot({ path: fileURLToPath(new URL('registration-' + theme + '-' + width + '.png', artifacts)), fullPage: true })
  }
  await button('返回登录').click()
  await page.getByRole('tab', { name: '管理员层', exact: true }).click()
  await page.getByPlaceholder('输入运维账号').fill('root')
  await page.getByPlaceholder('输入访问密码').fill('old-password')
  await button('进入智维Agent').click()
  await page.waitForURL('**/admin')
  await goto('/admin/users')
  await page.getByText('普通账号注册已开放', { exact: true }).waitFor()
  const dialog = page.getByRole('dialog')
  const verify = () => dialog.getByLabel('当前管理员密码', { exact: true })
  await button('关闭注册').click()
  await verify().fill('wrong-password')
  await dialog.getByRole('button', { name: '确认变更', exact: true }).click()
  await alert('当前管理员密码不正确')
  assert.equal(await verify().inputValue(), '')
  assert.equal(await page.getByText('普通账号注册已开放', { exact: true }).isVisible(), true)
  rejectAdmin = 429
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '确认变更', exact: true }).click()
  await alert('验证过于频繁')
  assert.equal(await verify().inputValue(), '')
  rejectAdmin = 0
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '确认变更', exact: true }).click()
  await page.getByText('普通账号注册已关闭', { exact: true }).waitFor()
  await page.reload()
  await page.getByText('普通账号注册已关闭', { exact: true }).waitFor()
  await button('开放注册').click()
  assert.equal(await verify().inputValue(), '')
  await verify().fill(adminPassword)
  await page.keyboard.press('Escape')
  await button('开放注册').click()
  assert.equal(await verify().inputValue(), '')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await button('新增账号').click()
  await dialog.getByLabel('账号', { exact: true }).fill('managed-user')
  await dialog.getByLabel('初始密码', { exact: true }).fill('target-new-password')
  rejectAdmin = 403
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '创建账号', exact: true }).click()
  await alert('当前管理员密码不正确')
  assert.equal(await verify().inputValue(), '')
  assert.equal(await dialog.getByLabel('初始密码', { exact: true }).inputValue(), '')
  rejectAdmin = 429
  await dialog.getByLabel('初始密码', { exact: true }).fill('target-new-password')
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '创建账号', exact: true }).click()
  await alert('验证过于频繁')
  assert.equal(await verify().inputValue(), '')
  rejectAdmin = 0
  await dialog.getByLabel('账号角色').selectOption('admin')
  await dialog.getByLabel('初始密码', { exact: true }).fill('twelve-chars')
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '创建账号', exact: true }).click()
  await alert('16')
  assert.equal(await verify().inputValue(), '', 'client validation also clears verification password')
  await dialog.getByLabel('账号角色').selectOption('operator')
  await dialog.getByLabel('初始密码', { exact: true }).fill('target-new-password')
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '创建账号', exact: true }).click()
  await page.getByRole('cell', { name: 'managed-user', exact: true }).waitFor()
  const row = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'operator', exact: true }) })
  for (const action of ['禁用', '变更角色', '重置密码']) {
    await row.getByRole('button', { name: action, exact: true }).click()
    assert.equal(await verify().inputValue(), '')
    if (action === '变更角色') await dialog.getByText('提升为管理员后将强制修改密码，满足管理员密码策略。', { exact: true }).waitFor()
    if (action === '重置密码') await dialog.getByLabel('临时密码', { exact: true }).fill('target-new-password')
    await verify().fill(adminPassword)
    await dialog.getByRole('button', { name: action === '重置密码' ? '确认重置' : '确认变更', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
  }
  await row.getByRole('button', { name: '禁用', exact: true }).click()
  for (const width of [375, 1440]) for (const theme of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 })
    await page.evaluate(async theme => { const { setThemeMode } = await import('/src/theme.js'); setThemeMode(theme) }, theme)
    await page.screenshot({ path: fileURLToPath(new URL('admin-confirm-' + theme + '-' + width + '.png', artifacts)), fullPage: true })
  }
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await goto('/admin/sessions')
  await button('撤销会话').click()
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await button('撤销会话').click()
  assert.equal(await verify().inputValue(), '')
  rejectAdmin = 403
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '确认撤销', exact: true }).click()
  await alert('当前管理员密码不正确')
  assert.equal(await verify().inputValue(), '')
  rejectAdmin = 0
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '确认撤销', exact: true }).click()
  await dialog.waitFor({ state: 'hidden' })
  await assertNoSecrets()
  await page.evaluate(async () => {
    const { createApp } = await import('/node_modules/.vite/deps/vue.js')
    const { default: AdminAccounts } = await import('/src/components/ai/AdminAccounts.vue')
    const container = document.createElement('section')
    container.id = 'legacy-account-fixture'
    document.body.append(container)
    const app = createApp(AdminAccounts)
    app._context.provides = document.querySelector('#app').__vue_app__._context.provides
    app.mount(container)
  })
  const legacy = page.locator('#legacy-account-fixture')
  assert.equal(await legacy.getByRole('button', { name: '新增账号', exact: true }).count(), 1, 'legacy account entry uses verified lifecycle UI')
  await legacy.getByRole('button', { name: '新增账号', exact: true }).click()
  await verify().fill(adminPassword)
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await legacy.getByRole('button', { name: '新增账号', exact: true }).click()
  assert.equal(await verify().inputValue(), '')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  assert.ok(calls.filter(call => call.path.startsWith('/api/admin/') && call.method !== 'GET').every(call => call.adminPassword))
  assert.ok(calls.filter(call => call.method === 'GET').every(call => !call.adminPassword))
  assert.deepEqual(errors, [])
  console.log('PASS: isolated registration, reload, boundaries, verification errors/clearing, eight responsive screenshots')
} finally { await browser.close(); await server.close() }
