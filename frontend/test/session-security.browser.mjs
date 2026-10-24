import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'

const base = process.env.SMARTOPS_TEST_URL || 'http://127.0.0.1:5173'
const bootstrap = await readFile(new URL('../../.runtime/secrets/bootstrap.env', import.meta.url), 'utf8')
const credentials = Object.fromEntries(bootstrap.trim().split(/\r?\n/).map(line => {
  const separator = line.indexOf('=')
  return [line.slice(0, separator), line.slice(separator + 1)]
}))
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.setDefaultTimeout(15000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('security-check')) {
      localStorage.setItem('smartops_preview_auth', JSON.stringify({ id: 1, username: 'forged-admin', role: 'admin' }))
      localStorage.setItem('smartops_theme', 'light')
      sessionStorage.setItem('security-check', 'true')
    }
  })
  await page.goto(`${base}/admin`, { waitUntil: 'domcontentloaded' })
  await page.locator('.login-form').waitFor()
  assert.equal(new URL(page.url()).pathname, '/login')
  const registration = (await (await page.request.get(`${base}/api/auth/registration`)).json()).data
  assert.equal(typeof registration.enabled, 'boolean')
  assert.equal(registration.userPasswordMinLength, 12)
  assert.equal(registration.adminPasswordMinLength, 16)
  assert.equal(registration.passwordMaxBytes, 72)
  assert.equal((await page.request.get(`${base}/api/admin/users`)).status(), 401)
  const beforeLogin = (await page.context().cookies()).find(cookie => cookie.name === 'JSESSIONID')?.value
  await page.getByPlaceholder('输入运维账号').fill(credentials.SMARTOPS_BOOTSTRAP_USERNAME)
  await page.getByRole('tab', { name: '管理员层', exact: true }).click()
  await page.locator('.login-form__footer').filter({ hasText: '10 分钟' }).waitFor()
  assert.equal(await page.getByRole('button', { name: '注册普通账号', exact: true }).count(), 0)
  await page.getByPlaceholder('输入访问密码').fill('deliberately-wrong-password')
  await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
  await page.locator('.login-form__error').filter({ hasText: '账号或密码错误' }).waitFor()
  await page.getByPlaceholder('输入访问密码').fill(credentials.SMARTOPS_BOOTSTRAP_PASSWORD)
  await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
  await page.locator('.admin-layout').waitFor()
  await page.getByRole('heading', { name: '管理总览', exact: true }).waitFor()
  await page.getByRole('link', { name: '账户管理', exact: true }).click()
  await page.locator('.admin-main tbody tr').first().waitFor()
  const sessionCookie = (await page.context().cookies()).find(cookie => cookie.name === 'JSESSIONID')
  assert.ok(sessionCookie?.httpOnly)
  assert.equal(sessionCookie.sameSite, 'Lax')
  assert.notEqual(sessionCookie.value, beforeLogin)
  const session = (await (await page.request.get(`${base}/api/auth/session`)).json()).data
  assert.equal(session.user.role, 'admin')
  assert.equal(session.user.portal, 'admin')
  assert.equal(session.user.id, 1)
  const adminRegistration = (await (await page.request.get(`${base}/api/admin/registration`)).json()).data
  assert.deepEqual(adminRegistration, registration)
  for (const path of ['/api/operations/sessions', '/api/knowledge/candidates']) {
    const response = await page.request.get(`${base}${path}`)
    assert.equal(response.status(), 200, path)
    assert.equal((await response.json()).code, 200, path)
  }
  const models = await (await page.request.get(`${base}/api/model-connections`)).json()
  assert.equal(models.length, 2, 'existing model records must remain intact')
  const forged = await (await page.request.get(`${base}/api/model-connections`, { headers: { 'X-User-Id': '999999' } })).json()
  assert.deepEqual(forged.map(model => model.id), models.map(model => model.id))
  const missingCsrf = await page.request.post(`${base}/api/chat/connections/-1/invoke`, { data: { prompt: 'security-check' } })
  assert.equal(missingCsrf.status(), 403)
  const missingConnection = await page.request.post(`${base}/api/chat/connections/-1/invoke`, {
    headers: { 'X-CSRF-TOKEN': session.csrfToken }, data: { prompt: 'security-check' }
  })
  assert.equal(missingConnection.status(), 404)
  const readiness = (await (await page.request.get(`${base}/api/admin/readiness`)).json()).data
  assert.deepEqual(readiness.unavailableTables, [])
  const terminalMessage = await page.evaluate(() => new Promise((resolve, reject) => {
    const socket = new WebSocket(`${location.origin.replace(/^http/, 'ws')}/ws/operations/terminal`)
    const timer = setTimeout(() => { socket.close(); reject(new Error('Terminal handshake timed out')) }, 5000)
    socket.onopen = () => socket.send(JSON.stringify({ type: 'OPEN', runtimeId: 'nonexistent-security-check' }))
    socket.onmessage = event => { clearTimeout(timer); socket.close(); resolve(JSON.parse(event.data)) }
    socket.onerror = () => { clearTimeout(timer); reject(new Error('Authenticated terminal handshake failed')) }
  }))
  assert.equal(terminalMessage.type, 'ERROR')
  assert.ok(terminalMessage.data.includes('RUNTIME'), terminalMessage.data)
  await page.getByRole('link', { name: '服务接入检查', exact: true }).click()
  await page.locator('.readiness').getByText('检查通过', { exact: true }).waitFor()
  await page.screenshot({ path: 'test-artifacts/remediation-admin-light.png', fullPage: true })
  await page.locator('.admin-user-trigger').click()
  await page.getByRole('button', { name: '返回用户层（重新登录）', exact: true }).click()
  await page.locator('.login-form').waitFor()
  await page.getByRole('tab', { name: '用户层', exact: true }).click()
  await page.locator('.login-form__footer').filter({ hasText: '30 分钟' }).waitFor()
  await page.getByPlaceholder('输入运维账号').fill(credentials.SMARTOPS_BOOTSTRAP_USERNAME)
  await page.getByPlaceholder('输入访问密码').fill(credentials.SMARTOPS_BOOTSTRAP_PASSWORD)
  await page.getByRole('button', { name: '进入智维Agent', exact: true }).click()
  await page.waitForURL(`${base}/`)
  const userSession = (await (await page.request.get(`${base}/api/auth/session`)).json()).data
  assert.equal(userSession.user.role, 'admin')
  assert.equal(userSession.user.portal, 'user')
  assert.equal((await page.request.get(`${base}/api/admin/users`)).status(), 403)
  const userSessionCookie = (await page.context().cookies()).find(cookie => cookie.name === 'JSESSIONID')
  for (const path of ['/knowledge', '/connections', '/plugins']) {
    await page.goto(`${base}${path}`, { waitUntil: 'domcontentloaded' })
    await page.locator('.main-area h1').first().waitFor()
    const geometry = await page.evaluate(() => ({
      title: document.querySelector('.main-area h1').getBoundingClientRect().left,
      navigation: document.querySelector('.sidebar').getBoundingClientRect().right
    }))
    assert.ok(geometry.title >= geometry.navigation, `${path}: navigation overlaps title`)
  }
  await page.goto(`${base}/connections`, { waitUntil: 'domcontentloaded' })
  await page.locator('.connections-page h1').waitFor()
  for (const theme of ['light', 'dark']) {
    await page.getByLabel('选择主题模式').selectOption(theme)
    await page.waitForFunction(theme => document.documentElement.dataset.theme === theme, theme)
    await page.waitForFunction(theme => {
      const channels = getComputedStyle(document.querySelector('.connections-page h1')).color.match(/\d+/g).slice(0, 3).map(Number)
      return theme === 'light' ? Math.max(...channels) < 160 : Math.min(...channels) > 160
    }, theme)
    const color = await page.locator('.connections-page h1').evaluate(element => getComputedStyle(element).color)
    const channels = color.match(/\d+/g).slice(0, 3).map(Number)
    assert.ok(theme === 'light' ? Math.max(...channels) < 160 : Math.min(...channels) > 160, `${theme}: ${color}`)
    if (theme === 'light') {
      for (const selector of ['.capability-row > span', '.capability-row .supported']) {
        const textColor = await page.locator(selector).first().evaluate(element => getComputedStyle(element).color)
        assert.ok(Math.max(...textColor.match(/\d+/g).slice(0, 3).map(Number)) < 160, `${selector}: ${textColor}`)
      }
    }
    await page.screenshot({ path: `test-artifacts/remediation-connections-${theme}.png`, fullPage: true })
    await page.setViewportSize({ width: 375, height: 900 })
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)
    assert.equal(overflow, false, `${theme}: mobile viewport overflows`)
    await page.screenshot({ path: `test-artifacts/remediation-connections-${theme}-mobile.png`, fullPage: true })
    await page.setViewportSize({ width: 1440, height: 1000 })
  }
  await page.evaluate(() => new Promise((resolve, reject) => {
    const socket = new WebSocket(`${location.origin.replace(/^http/, 'ws')}/ws/operations/terminal`)
    window.securitySocketClosed = new Promise(closed => { socket.onclose = event => closed(event.code) })
    socket.onopen = resolve
    socket.onerror = () => reject(new Error('Cannot establish logout test socket'))
  }))
  await page.locator('.account-menu-trigger').click()
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await page.locator('.login-form').waitFor()
  assert.equal(await page.evaluate(() => Promise.race([window.securitySocketClosed, new Promise(resolve => setTimeout(() => resolve(-1), 5000))])), 1008)
  assert.equal((await page.request.get(`${base}/api/admin/users`)).status(), 401)
  const replay = await browser.newContext()
  await replay.addCookies([userSessionCookie])
  assert.equal((await replay.request.get(`${base}/api/admin/users`)).status(), 401)
  await replay.close()
  assert.deepEqual(errors, [])
  console.log('PASS real session: forged local auth, invalid login, rotation, CSRF, trusted identity, schema, model preservation, admin entry, desktop/mobile themes, logout and cookie replay')
} finally {
  await browser.close()
}
