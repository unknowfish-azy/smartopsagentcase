import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import { createServer } from 'vite'

const base = process.env.SMARTOPS_BROWSER_BASE_URL || 'http://127.0.0.1:5194'
const server = process.env.SMARTOPS_BROWSER_BASE_URL ? null : await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { host: '127.0.0.1', port: 5194, strictPort: true }, logLevel: 'error' })
await server?.listen()
const browser = await chromium.launch({ channel: 'msedge', headless: true })
await mkdir('test-artifacts/human-verification', { recursive: true })
const errors = [], submissions = []
let rejectToken = false, policyUnavailable = false
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.hostname === 'challenges.cloudflare.com') return route.fulfill({ contentType: 'application/javascript', body: `
      window.turnstile = {
        render(container, options) {
          window.verificationOptions = options;
          const button = document.createElement('button');
          button.type = 'button'; button.textContent = '模拟完成验证';
          button.onclick = () => options.callback('mock-token-' + options.action);
          container.replaceChildren(button); return 'test-widget';
        }, remove() {}, reset() {}
      };
    ` })
    if (url.origin !== base) return route.abort()
    if (!url.pathname.startsWith('/api/')) return route.continue()
    const reply = (data, status = 200, message = 'success') => route.fulfill({ status, json: { code: status, message, data } })
    if (url.pathname === '/api/auth/session') return reply({ user: null, csrfToken: 'mock-csrf' })
    if (url.pathname === '/api/auth/registration') return reply({ enabled: true, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 })
    if (url.pathname === '/api/auth/human-verification') {
      if (policyUnavailable) return reply(null, 503, '验证服务暂时不可用')
      const action = url.searchParams.get('action')
      return reply({ enabled: true, available: true, required: action !== 'login', provider: 'turnstile', siteKey: 'browser-test-key', action, challenge: 'browser-session-challenge' })
    }
    if (['/api/auth/register', '/api/auth/login'].includes(url.pathname)) {
      assert.equal(route.request().headers()['x-csrf-token'], 'mock-csrf')
      submissions.push({ path: url.pathname, body: route.request().postDataJSON() })
      return reply(null, rejectToken ? 428 : 401, rejectToken ? '请重新完成人机验证' : '账号或密码错误')
    }
    return reply({})
  })
  await page.goto(`${base}/login?portal=admin`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '模拟完成验证' }).waitFor({ timeout: 5000 })
  await page.getByPlaceholder('输入运维账号').fill('not-a-real-account')
  await page.getByPlaceholder('输入访问密码').fill('not-a-real-password')
  assert.equal(await page.locator('.login-submit').isDisabled(), true)
  await page.getByRole('button', { name: '模拟完成验证' }).click()
  assert.equal(await page.locator('.login-submit').isEnabled(), true)
  await page.locator('.login-submit').click()
  await page.getByText('账号或密码错误', { exact: true }).waitFor()
  assert.equal(submissions[0].body.humanToken, 'mock-token-admin_login')
  await page.waitForFunction(() => document.querySelector('.login-submit').disabled)
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.waitForFunction(expected => window.verificationOptions.size === expected, width < 420 ? 'compact' : 'flexible')
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('选择主题模式').selectOption(theme)
      await page.waitForFunction(expected => window.verificationOptions.theme === expected, theme)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
      await page.screenshot({ path: `test-artifacts/human-verification/${theme}-${width}.png`, fullPage: true })
    }
  }
  await page.getByRole('button', { name: '模拟完成验证' }).click()
  await page.evaluate(() => window.verificationOptions['expired-callback']())
  assert.equal(await page.locator('.login-submit').isDisabled(), true)
  await page.evaluate(() => { window.staleVerificationCallback = window.verificationOptions.callback })
  await page.getByRole('tab', { name: '用户层', exact: true }).click()
  await page.waitForFunction(() => !document.querySelector('.login-submit').disabled)
  rejectToken = true
  await page.locator('.login-submit').click()
  await page.getByRole('button', { name: '模拟完成验证' }).waitFor()
  assert.equal(await page.locator('.login-submit').isDisabled(), true)
  await page.getByRole('button', { name: '注册普通账号', exact: true }).click()
  await page.waitForFunction(() => window.verificationOptions.action === 'register')
  await page.evaluate(() => window.staleVerificationCallback('stale-admin-token'))
  assert.equal(await page.locator('.login-submit').isDisabled(), true)
  await page.evaluate(() => window.verificationOptions['error-callback']('network-error'))
  await page.getByRole('button', { name: '重试验证' }).click()
  await page.getByRole('button', { name: '模拟完成验证' }).waitFor()
  policyUnavailable = true
  await page.getByRole('button', { name: '返回登录', exact: true }).click()
  await page.getByText('验证服务暂时不可用', { exact: true }).waitFor()
  assert.equal(await page.locator('.login-submit').isDisabled(), true)
  assert.deepEqual(errors, [])
  console.log('PASS human verification: gating, token forwarding, reset, risk escalation, theme/mobile, expiry, outage')
} finally {
  await browser.close()
  await server?.close()
}
