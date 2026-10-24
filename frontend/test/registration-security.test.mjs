import assert from 'node:assert/strict'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

test('registration and administrator verification contracts', async context => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true }, logLevel: 'silent' })
  try {
    const { default: request } = await server.ssrLoadModule('/src/utils/request.js')
    const session = await server.ssrLoadModule('/src/security/session.js')
    const { adminApi } = await server.ssrLoadModule('/src/api/admin.js')
    const calls = []
    const policy = { enabled: true, usernameMinLength: 3, userPasswordMinLength: 12, adminPasswordMinLength: 16, passwordMaxBytes: 72 }
    request.defaults.adapter = async config => {
      calls.push({ url: config.url, method: config.method, body: config.data && JSON.parse(config.data), adminPassword: config.headers.get('X-Admin-Password'), csrf: config.headers.get('X-CSRF-TOKEN') })
      const data = config.url === '/api/auth/session' ? { user: null, csrfToken: 'anonymous-csrf' } : config.url.endsWith('/registration') ? policy : { id: 9, username: 'new-user', role: 'operator', mustChangePassword: false }
      return { data: { code: 200, data }, status: 200, statusText: 'OK', headers: {}, config }
    }
    await context.test('public policy and registration obtain CSRF without logging in or accepting a role', async () => {
      assert.equal(typeof session.registrationPolicy, 'function')
      assert.deepEqual(await session.registrationPolicy(), policy)
      const account = await session.registerAccount({ username: 'new-user', password: 'safe-user-password', confirmPassword: 'safe-user-password', role: 'admin', enabled: true })
      assert.deepEqual(calls.at(-1), { url: '/api/auth/register', method: 'post', body: { username: 'new-user', password: 'safe-user-password', confirmPassword: 'safe-user-password', humanToken: '' }, csrf: 'anonymous-csrf', adminPassword: undefined })
      assert.equal(account.role, 'operator')
      assert.equal(session.currentSession.value, null)
      assert.equal(calls.some(call => call.url === '/api/auth/login'), false)
    })
    await context.test('all admin mutations send only a per-request verification header', async () => {
      const password = 'current-administrator-password'
      await adminApi.createUser({ username: 'new-user', password: 'target-password', role: 'operator' }, password)
      assert.equal(calls.at(-1).adminPassword, password)
      assert.equal(calls.at(-1).body.password, 'target-password')
      await adminApi.updateUser(9, { role: 'admin', enabled: true }, password)
      assert.equal(calls.at(-1).adminPassword, password)
      await adminApi.resetPassword(9, 'target-reset-password', password)
      assert.equal(calls.at(-1).adminPassword, password)
      assert.deepEqual(calls.at(-1).body, { password: 'target-reset-password' })
      await adminApi.revokeSession('opaque/id', password)
      assert.equal(calls.at(-1).adminPassword, password)
      await adminApi.updateRegistration(false, password)
      assert.deepEqual(calls.at(-1).body, { enabled: false })
      assert.equal(calls.at(-1).adminPassword, password)
      assert.equal(calls.at(-1).method, 'put')
      assert.equal(calls.at(-1).url, '/api/admin/registration')
      await adminApi.registration()
      assert.equal(calls.at(-1).adminPassword, undefined)
      assert.equal(request.defaults.headers.common['X-Admin-Password'], undefined)
    })
    await context.test('password validation is role-aware and uses UTF-8 bytes', async () => {
      const { passwordError, registrationError } = await server.ssrLoadModule('/src/security/passwordPolicy.js')
      assert.match(passwordError('short', 'operator'), /12/)
      assert.equal(passwordError('abcdefghijkl', 'operator'), '')
      assert.match(passwordError('abcdefghijkl', 'admin'), /16/)
      assert.equal(passwordError('abcdefghijklmnop', 'admin'), '')
      assert.equal(passwordError('密'.repeat(24)), '')
      assert.match(passwordError('密'.repeat(25)), /72/)
      assert.match(registrationError({ username: 'bad name', password: 'abcdefghijkl', confirmPassword: 'abcdefghijkl' }), /账号/)
      assert.match(registrationError({ username: 'valid', password: 'abcdefghijkl', confirmPassword: 'different' }), /不一致/)
    })
    await context.test('HTTP 429 preserves the actionable server error', async () => {
      request.defaults.adapter = async config => { throw { config, response: { status: 429, data: { message: '验证过于频繁，请稍后再试' }, config } } }
      await assert.rejects(request.get('/api/admin/users'), /验证过于频繁/)
    })
  } finally { await server.close() }
})
