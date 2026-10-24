import assert from 'node:assert/strict'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

test('MFA pending login never becomes an authenticated client session', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true }, logLevel: 'silent' })
  try {
    const { default: request } = await server.ssrLoadModule('/src/utils/request.ts')
    const session = await server.ssrLoadModule('/src/security/session.js')
    const calls = []
    let user = null
    request.defaults.adapter = async config => {
      calls.push({ url: config.url, body: config.data ? JSON.parse(config.data) : undefined, csrf: config.headers.get('X-CSRF-TOKEN') })
      if (config.url === '/api/auth/mfa/complete') user = { id: 81, username: 'mock-admin', role: 'admin', portal: 'admin' }
      const data = config.url === '/api/auth/session' ? { user, csrfToken: user ? 'rotated-csrf' : 'pending-csrf' } : config.url === '/api/auth/login' ? { mfaRequired: true, challenge: 'mock-challenge', expiresIn: 300 } : user
      return { data: { code: 200, data }, status: 200, statusText: 'OK', headers: {}, config }
    }
    const challenge = await session.loginSession('mock-admin', 'mock-password', 'user')
    assert.equal(challenge.mfaRequired, true)
    assert.equal(challenge.challenge, 'mock-challenge')
    assert.equal(session.currentSession.value, null)
    assert.deepEqual(calls.map(call => call.url), ['/api/auth/session', '/api/auth/login'])
    const authenticated = await session.completeMfa('mock-challenge', '123456')
    assert.equal(authenticated.role, 'admin')
    assert.deepEqual(calls.at(-2).body, { challenge: 'mock-challenge', code: '123456' })
    assert.equal(calls.at(-2).csrf, 'pending-csrf')
    assert.equal(request.defaults.headers.common['X-CSRF-TOKEN'], 'rotated-csrf')
    await session.cancelMfa()
    assert.equal(calls.at(-1).url, '/api/auth/mfa/cancel')
  } finally { await server.close() }
})
