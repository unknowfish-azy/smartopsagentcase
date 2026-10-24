import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer } from 'vite'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5196'
// 两层前端拆分后门户切换是跨源整页导航；把两个门户端口都解析到 base 的端口，
// 让目标入口（/login → index.html）由同一个 dev server 提供，否则 assign 会跳到无人监听的默认端口。
const basePort = new URL(base).port || (base.startsWith('https:') ? '443' : '80')
process.env.VITE_SMARTOPS_USER_PORT = basePort
process.env.VITE_SMARTOPS_ADMIN_PORT = basePort
const server = process.env.SMARTOPS_BROWSER_BASE_URL ? null : await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5196, strictPort: true }, logLevel: 'error' })
await server?.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/admin-mfa', { recursive: true })
const identity = { id: 81, username: 'mock-mfa-admin', role: 'admin', portal: 'admin', mustChangePassword: false }
const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', password = 'mock-password-not-a-real-account'
let user = identity, enabled = false, batch = 0, codes = []
const calls = [], errors = []
const notices = [{ id: 1, message: '二次认证失败，请确认是否本人操作。', createdAt: '2026-10-03T00:00:00Z', read: false }]
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', serviceWorkers: 'block' })
  await context.routeWebSocket('**/*', socket => socket.close())
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method()
    if (url.origin !== base) return route.abort()
    if (!path.startsWith('/api/')) return route.continue()
    const body = request.postDataJSON(), headers = request.headers()
    calls.push({ path, method, body })
    const reply = (data, status = 200, message = 'success') => route.fulfill({ status, json: { code: status, message, data } })
    if (method !== 'GET') assert.equal(headers['x-csrf-token'], 'mock-csrf')
    if (path === '/api/auth/session') return reply({ user, csrfToken: 'mock-csrf' })
    if (path === '/api/auth/registration') return reply({ enabled: true, userPasswordMinLength: 12 })
    if (path === '/api/auth/human-verification') return reply({ action: url.searchParams.get('action'), enabled: false, available: true, required: false })
    if (path === '/api/auth/login') { assert.equal(body.password, password); return reply({ mfaRequired: true, challenge: 'login-challenge', expiresIn: 300 }) }
    if (path === '/api/auth/mfa/complete') {
      assert.equal(body.challenge, 'login-challenge')
      if (body.code === '999999') return reply(null, 429, '尝试过多，请返回密码登录')
      if (body.code !== '654321' && !codes.includes(body.code)) return reply(null, 400, '动态码或恢复码无效、已使用，请重试')
      codes = codes.filter(code => code !== body.code); user = identity; return reply(user)
    }
    if (path === '/api/auth/mfa/cancel') return reply(null)
    if (path === '/api/auth/logout') { user = null; return reply(null) }
    if (path === '/api/admin/mfa') return reply({ enabled, recoveryCodesRemaining: codes.length })
    if (path === '/api/admin/mfa/notices') return reply(notices)
    if (path === '/api/auth/mfa/notices/1/read') { assert.equal(headers['x-admin-password'], undefined); notices[0].read = true; return reply(null) }
    if (path.startsWith('/api/admin/mfa/') && method === 'POST') {
      assert.equal(headers['x-admin-password'], password)
      if (path.endsWith('/setup')) return reply({ secret, challenge: 'setup-challenge', expiresIn: 300, account: identity.username, issuer: 'SmartOpsAgent' })
      if (path.endsWith('/enable')) { assert.deepEqual(body, { challenge: 'setup-challenge', code: '123456' }); enabled = true }
      if (path.endsWith('/disable')) { enabled = false; codes = []; return reply({ recoveryCodes: [] }) }
      codes = Array.from({ length: 10 }, (_, index) => `${String(++batch).padStart(8, '0')}-aaaaaaaa-bbbbbbbb-${String(index).padStart(8, '0')}`)
      return reply({ version: 1, recoveryCodes: codes })
    }
    return reply({ items: [], total: 0 })
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(`${base}/admin/security`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '管理员二次认证', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '开始绑定认证器' }).isDisabled(), true)
  const start = async () => { await page.getByLabel('当前密码', { exact: true }).fill(password); await page.getByRole('button', { name: '开始绑定认证器' }).click(); await page.getByLabel('绑定密钥（仅本次显示）', { exact: true }).waitFor() }
  await start()
  assert.equal(await page.getByLabel('当前密码', { exact: true }).inputValue(), '')
  await page.getByRole('button', { name: '取消绑定', exact: true }).click()
  assert.equal(await page.getByLabel('绑定密钥（仅本次显示）', { exact: true }).count(), 0)
  await start()
  await page.getByLabel('认证器动态码', { exact: true }).fill('123456')
  await page.getByLabel('当前密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '确认绑定', exact: true }).click()
  await page.getByLabel('一次性恢复码', { exact: true }).waitFor()
  const recoveryCode = codes[0]
  assert.equal((await page.getByLabel('一次性恢复码', { exact: true }).inputValue()).split('\n').length, 10)
  assert.equal(await page.getByRole('button', { name: '完成并隐藏恢复码' }).isDisabled(), true)
  for (const sensitive of [secret, recoveryCode, password]) assert.equal(await page.evaluate(value => JSON.stringify(localStorage).includes(value) || JSON.stringify(sessionStorage).includes(value), sensitive), false)
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      // 管理台主题是 ☀/☾ 切换按钮（不是下拉框）：按当前实际主题决定是否点一次
      if (await page.evaluate(() => document.documentElement.dataset.theme) !== theme) {
        await page.getByRole('button', { name: /切到(浅色|深色)/ }).click()
      }
      await page.waitForFunction(theme => document.documentElement.dataset.theme === theme, theme)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      await page.screenshot({ path: `test-artifacts/admin-mfa/recovery-${theme}-${width}.png`, fullPage: true })
    }
  }
  await page.getByLabel('我已离线保存全部恢复码').check()
  await page.getByRole('button', { name: '完成并隐藏恢复码' }).click()
  await page.getByRole('button', { name: '标记已读', exact: true }).click()
  await page.getByText('已读', { exact: true }).waitFor()
  await page.locator('.admin-user-trigger').click()
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await page.waitForURL('**/login?portal=admin')
  const enterPassword = async () => {
    await page.getByPlaceholder('输入运维账号').fill(identity.username)
    await page.getByPlaceholder('输入访问密码').fill(password)
    await page.locator('.login-submit').click()
    await page.getByRole('heading', { name: '二次认证', exact: true }).waitFor()
    assert.equal(await page.getByPlaceholder('输入访问密码').count(), 0)
  }
  await enterPassword()
  await page.getByRole('button', { name: '返回密码登录', exact: true }).click()
  await page.getByPlaceholder('输入访问密码').waitFor()
  assert.equal(await page.getByPlaceholder('输入访问密码').inputValue(), '')
  await enterPassword()
  await page.getByPlaceholder('输入认证器中的 6 位动态码').fill('999999')
  await page.getByRole('button', { name: '验证并登录', exact: true }).click()
  await page.getByText('尝试过多，请返回密码登录', { exact: true }).waitFor()
  await page.waitForTimeout(1200)
  assert.equal(await page.getByRole('button', { name: '验证并登录', exact: true }).isDisabled(), true)
  assert.equal(await page.getByPlaceholder('输入认证器中的 6 位动态码').isDisabled(), true)
  await page.getByRole('button', { name: '返回密码登录', exact: true }).click()
  await enterPassword()
  const boundary = calls.length
  await page.getByPlaceholder('输入认证器中的 6 位动态码').fill('000000')
  await page.getByRole('button', { name: '验证并登录', exact: true }).click()
  await page.getByText('动态码或恢复码无效、已使用，请重试', { exact: true }).waitFor()
  assert.equal(calls.slice(boundary).some(call => call.path.startsWith('/api/admin/')), false)
  assert.equal(await page.getByPlaceholder('输入认证器中的 6 位动态码').inputValue(), '')
  await page.getByLabel('使用恢复码', { exact: true }).check()
  await page.getByPlaceholder('输入一枚未使用的恢复码').fill(recoveryCode)
  await page.getByRole('button', { name: '验证并登录', exact: true }).click()
  await page.waitForURL('**/admin')
  await page.getByRole('link', { name: '二次认证', exact: true }).click()
  await page.getByRole('heading', { name: '二次认证已启用', exact: true }).waitFor()
  await page.getByLabel('当前密码', { exact: true }).fill(password)
  await page.getByLabel('动态码或恢复码', { exact: true }).fill('654321')
  assert.equal(await page.getByRole('button', { name: '关闭二次认证', exact: true }).isDisabled(), true)
  await page.getByLabel('我确认关闭二次认证会降低账号安全性').check()
  await page.getByRole('button', { name: '关闭二次认证', exact: true }).click()
  await page.getByRole('heading', { name: '尚未绑定认证器', exact: true }).waitFor()
  assert.equal(await page.getByLabel('当前密码', { exact: true }).inputValue(), '')
  assert.deepEqual(errors, [])
  console.log('PASS admin MFA: setup, recovery display/cleanup, pending/cancel/limit, recovery login, notices, protected disable, 375/1440 light/dark; APIs intercepted')
} finally { await browser.close(); await server?.close() }
