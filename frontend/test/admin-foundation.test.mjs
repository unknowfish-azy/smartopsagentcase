import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

const policy = await import('../src/security/portalPolicy.js').catch(() => ({}))
const admin = { id: 1, role: 'admin', portal: 'admin', mustChangePassword: false }

test('management requires both the server role and current portal', () => {
  assert.equal(typeof policy.isAdminSession, 'function')
  assert.equal(policy.isAdminSession(admin), true)
  for (const session of [null, { ...admin, portal: 'user' }, { ...admin, role: 'operator' }, { role: 'admin' }, { ...admin, mustChangePassword: true }]) {
    assert.equal(policy.isAdminSession(session), false)
  }
})

test('per-portal surfaces render their own login page instead of bouncing', () => {
  for (const id of ['enterprise', 'audit', 'command', 'open']) {
    // 未登录访问登录页：必须放行，否则守卫会自我重定向成空白页。
    assert.equal(policy.sessionRouteDecision(null, { path: '/login', query: {} }, id), true)
    // 未登录访问门户内页：退回本门户登录页，并带上门户标记。
    const denied = policy.sessionRouteDecision(null, { path: `/${id}`, query: {}, fullPath: `/${id}` }, id)
    assert.equal(denied.path, '/login')
    assert.equal(denied.query.portal, id)
    assert.equal(denied.query.redirect, `/${id}`)
  }
})

test('forced password change gates all pages except account security', () => {
  assert.equal(typeof policy.sessionRouteDecision, 'function')
  const forced = { ...admin, mustChangePassword: true }
  for (const path of ['/', '/admin', '/admin/users', '/chat', '/login', '/portfolio']) {
    assert.deepEqual(policy.sessionRouteDecision(forced, { path }), { path: '/account/security' })
  }
  assert.equal(policy.sessionRouteDecision(forced, { path: '/account/security' }), true)
})

test('user portal cannot enter management even with an admin account', () => {
  assert.equal(typeof policy.sessionRouteDecision, 'function')
  const user = { ...admin, portal: 'user' }
  assert.deepEqual(policy.sessionRouteDecision(user, { path: '/admin/users' }), { path: '/', query: { denied: 'portal' } })
  assert.deepEqual(policy.sessionRouteDecision(user, { path: '/architecture', meta: { roles: ['admin'] } }), { path: '/', query: { denied: 'portal' } })
  assert.equal(policy.sessionRouteDecision(admin, { path: '/admin/users' }), true)
})

test('management session cannot fall through to the user console', () => {
  assert.deepEqual(policy.sessionRouteDecision(admin, { path: '/' }), { path: '/admin' })
  assert.deepEqual(policy.sessionRouteDecision(admin, { path: '/chat' }), { path: '/admin' })
  assert.equal(policy.sessionRouteDecision(admin, { path: '/admin' }), true)
})

test('login landing respects forced change, entry and safe local redirect', () => {
  assert.equal(typeof policy.sessionLanding, 'function')
  assert.equal(policy.sessionLanding(admin), '/admin')
  assert.equal(policy.sessionLanding({ ...admin, portal: 'user' }, '/admin/users'), '/')
  assert.equal(policy.sessionLanding(admin, '//evil.example'), '/admin')
  assert.equal(policy.sessionLanding(admin, '/login'), '/admin')
  assert.equal(policy.sessionLanding({ ...admin, portal: 'user' }, '/knowledge'), '/knowledge')
  assert.equal(policy.sessionLanding({ ...admin, mustChangePassword: true }, '/admin'), '/account/security')
})

test('login sends portal and password changes invalidate the local session', async () => {
  const source = await readFile(new URL('../src/security/session.js', import.meta.url), 'utf8')
  assert.match(source, /loginSession\(username, password, portal/)
  assert.match(source, /username, password, portal, humanToken\s*}/)
  assert.match(source, /function changePassword\(/)
  assert.match(source, /\/api\/auth\/password/)
})

test('management routes are independent and readiness reuses the existing component', async () => {
  const source = await readFile(new URL('../src/router/index.js', import.meta.url), 'utf8')
  // 用户层服务不得注册任何管理路由/布局：管理页面只存在于独立的 5174 服务。
  assert.equal(source.includes("import AdminLayout from '../layouts/AdminLayout.vue'"), false)
  assert.equal(source.includes("component: () => import('../layouts/AdminLayout.vue')"), false)
  assert.equal(source.includes("'../views/admin/"), false)
  const adminSource = await readFile(new URL('../src/router/admin.js', import.meta.url), 'utf8')
  assert.equal(adminSource.includes("component: () => import('../layouts/AdminLayout.vue')"), true)
  assert.match(source, /sessionRouteDecision/)
  assert.match(source, /account\/security/)
  const readiness = await readFile(new URL('../src/views/admin/AdminReadinessView.vue', import.meta.url), 'utf8')
  assert.match(readiness, /components\/ai\/AdminReadiness.vue/)
})

test('account and audit search respect the 64-character literal substring contract', async () => {
  for (const path of ['../src/views/admin/AdminUsersView.vue', '../src/views/admin/AdminAuditView.vue']) {
    const source = await readFile(new URL(path, import.meta.url), 'utf8')
    assert.match(source, /v-model.trim="filters.q"[^>]*maxlength="64"/)
  }
})
