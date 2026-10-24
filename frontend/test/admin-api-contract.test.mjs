import assert from 'node:assert/strict'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

test('admin and session clients honor frozen contracts without network requests', async context => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true }, logLevel: 'silent' })
  try {
    const { default: request } = await server.ssrLoadModule('/src/utils/request.ts')
    const session = await server.ssrLoadModule('/src/security/session.js')
    const { adminApi, AUDIT_ACTIONS, AUDIT_OUTCOMES } = await server.ssrLoadModule('/src/api/admin.ts')
    const calls = []
    let user = null
    let csrf = 'initial-csrf'
    const admin = { id: 1, username: 'test-admin', role: 'admin', portal: 'admin', mustChangePassword: false, authVersion: 3 }
    request.defaults.adapter = async config => {
      const body = config.data ? JSON.parse(config.data) : undefined
      calls.push({ url: config.url, method: config.method, body, params: config.params, csrf: config.headers.get('X-CSRF-TOKEN') })
      let data = { items: [], total: 0, page: 1, pageSize: 20 }
      if (config.url === '/api/auth/session') data = { user, csrfToken: csrf }
      if (config.url === '/api/auth/login') { user = { ...admin, portal: body.portal }; csrf = 'rotated-csrf'; data = user }
      if (config.url === '/api/auth/password' || config.url === '/api/auth/logout') { user = null; data = { reauthenticate: true } }
      return { data: { code: 200, data }, status: 200, statusText: 'OK', headers: {}, config }
    }
    await context.test('login defaults to user portal and refreshes rotated CSRF', async () => {
      await session.loginSession('test-admin', 'mock-password')
      assert.deepEqual(calls.slice(-3).map(call => call.url), ['/api/auth/session', '/api/auth/login', '/api/auth/session'])
      assert.deepEqual(calls.at(-2).body, { username: 'test-admin', password: 'mock-password', portal: 'user', humanToken: '' })
      assert.equal(calls.at(-2).csrf, 'initial-csrf')
      assert.equal(request.defaults.headers.common['X-CSRF-TOKEN'], 'rotated-csrf')
      assert.equal(session.currentSession.value.portal, 'user')
      await session.loginSession('test-admin', 'mock-password', 'admin')
      assert.equal(calls.at(-2).body.portal, 'admin')
    })
    await context.test('management API uses paginated filters and separate lifecycle endpoints', async () => {
      const query = { q: 'alice', page: 2, pageSize: 20, role: 'operator', enabled: 'true' }
      await adminApi.users(query)
      assert.deepEqual(calls.at(-1).params, query)
      await adminApi.createUser({ username: 'alice', password: 'mock-only', role: 'operator' })
      assert.deepEqual(calls.at(-1).body, { username: 'alice', password: 'mock-only', role: 'operator' })
      await adminApi.updateUser(9, { role: 'admin', enabled: false })
      assert.equal(calls.at(-1).method, 'put')
      assert.equal(calls.at(-1).url, '/api/admin/users/9')
      assert.deepEqual(calls.at(-1).body, { role: 'admin', enabled: false })
      await adminApi.resetPassword(9, 'mock-reset')
      assert.equal(calls.at(-1).url, '/api/admin/users/9/reset-password')
      assert.deepEqual(calls.at(-1).body, { password: 'mock-reset' })
      await adminApi.sessions()
      assert.equal(calls.at(-1).url, '/api/admin/sessions')
      await adminApi.revokeSession('opaque/id')
      assert.equal(calls.at(-1).url, '/api/admin/sessions/opaque%2Fid')
      assert.equal(calls.at(-1).method, 'delete')
      const audit = { q: 'alice', action: 'LOGIN', outcome: 'FAILURE', page: 2, pageSize: 50 }
      await adminApi.audit(audit)
      assert.equal(calls.at(-1).url, '/api/admin/audit')
      assert.deepEqual(calls.at(-1).params, audit)
      await adminApi.users({ q: '%', page: 1, pageSize: 100 })
      assert.equal(calls.at(-1).params.q, '%')
    })
    await context.test('audit filters expose only frozen server action and outcome values', () => {
      assert.deepEqual(AUDIT_ACTIONS?.map(item => item.value), ['LOGIN', 'LOGOUT', 'CREATE_USER', 'UPDATE_USER', 'RESET_PASSWORD', 'CHANGE_PASSWORD', 'REVOKE_SESSION', 'REGISTER', 'REGISTRATION_POLICY', 'ADMIN_VERIFY', 'HUMAN_VERIFY', 'MFA_ENABLE', 'MFA_DISABLE', 'MFA_VERIFY', 'MFA_RECOVERY_ROTATE', 'MFA_RECOVERY_USE', 'TEAM_CREATE', 'TEAM_UPDATE', 'TEAM_INVITE', 'TEAM_INVITE_RESPOND', 'TEAM_INVITE_CANCEL', 'TEAM_MEMBER_ROLE', 'TEAM_MEMBER_REMOVE', 'TEAM_STATUS', 'CHAT_CONVERSATION_CREATE', 'CHAT_CONVERSATION_DELETE', 'CHAT_ATTACHMENT_UPLOAD'])
      assert.deepEqual(AUDIT_OUTCOMES?.map(item => item.value), ['SUCCESS', 'FAILURE', 'DENIED'])
    })
    await context.test('forced password gate blocks requests before transport and allows password/logout', async () => {
      user = { ...admin, mustChangePassword: true }
      await session.loadSession()
      const count = calls.length
      for (const path of ['/api/admin/overview', '/api/auth/sessions', '/api/chat/connections/1/invoke', '/api/operations/sessions']) {
        await assert.rejects(request.get(path), /请先修改密码/)
      }
      assert.equal(calls.length, count)
      await session.changePassword('old-mock', 'new-mock')
      assert.deepEqual(calls.at(-1).body, { currentPassword: 'old-mock', newPassword: 'new-mock' })
      assert.equal(session.currentSession.value, null)
      assert.equal(request.defaults.headers.common['X-CSRF-TOKEN'], undefined)
      user = { ...admin, mustChangePassword: true }
      await session.loadSession()
      await session.logoutSession()
      assert.equal(calls.at(-1).url, '/api/auth/logout')
      assert.equal(session.currentSession.value, null)
    })
    await context.test('forced sessions can reauthenticate through the permitted login endpoint', async () => {
      user = { ...admin, mustChangePassword: true }
      await session.loadSession()
      await session.loginSession('test-admin', 'mock-password', 'user')
      assert.equal(session.currentSession.value.portal, 'user')
    })
  } finally { await server.close() }
})
