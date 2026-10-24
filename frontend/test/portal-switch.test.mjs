// 入口（门户）切换的纯逻辑测试。
//
// 这条链路很容易写成"只改一个变量"，但两个入口现在是两个独立前端服务，
// 切换必须产生一个指向目标服务的真实地址。这里把地址推导钉死。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  PORTAL_ADMIN,
  PORTAL_USER,
  currentPortal,
  portalLoginUrl,
  portalOrigin,
  resolvePortalSwitch
} from '../src/security/portalSwitch.js'

// 用一个假 location 代替浏览器，避免依赖运行环境端口。
const here = (port, hostname = '127.0.0.1', protocol = 'http:') => ({ hostname, port: String(port), protocol })

test('administrator portal resolves to its own origin and port', () => {
  assert.equal(portalOrigin(PORTAL_ADMIN, here(5173)), 'http://127.0.0.1:5174')
  assert.equal(portalOrigin(PORTAL_USER, here(5174)), 'http://127.0.0.1:5173')
})

test('switching from the user layer to the administrator layer is cross-origin', () => {
  const decision = resolvePortalSwitch(PORTAL_ADMIN, {}, here(5173))
  assert.equal(decision.crossOrigin, true, '5173 -> 5174 must be a full navigation')
  assert.equal(decision.url, 'http://127.0.0.1:5174/login?portal=admin')
})

test('switching from the administrator layer back to the user layer is cross-origin', () => {
  const decision = resolvePortalSwitch(PORTAL_USER, {}, here(5174))
  assert.equal(decision.crossOrigin, true)
  assert.equal(decision.url, 'http://127.0.0.1:5173/login?portal=user')
})

test('a switch on the same port stays a same-origin SPA navigation', () => {
  const decision = resolvePortalSwitch(PORTAL_USER, {}, here(5173))
  assert.equal(decision.crossOrigin, false, 'same service must not reload the whole page')
  assert.equal(decision.url, 'http://127.0.0.1:5173/login?portal=user')
})

test('the target portal is always explicit so the destination does not have to guess', () => {
  // 管理员层服务默认把登录页锁到 admin；带 portal=user 才能停在用户层。
  assert.match(portalLoginUrl(PORTAL_USER, {}, here(5174)), /[?&]portal=user(&|$)/)
  assert.match(portalLoginUrl(PORTAL_ADMIN, {}, here(5173)), /[?&]portal=admin(&|$)/)
})

test('query values survive the switch and portal is not duplicated', () => {
  const url = portalLoginUrl(PORTAL_ADMIN, { query: { redirect: '/admin/users', portal: 'user' } }, here(5173))
  assert.match(url, /redirect=%2Fadmin%2Fusers/)
  assert.equal((url.match(/portal=/g) ?? []).length, 1, 'portal must appear exactly once')
  assert.match(url, /portal=admin/)
})

test('empty query values are dropped instead of producing noise', () => {
  const url = portalLoginUrl(PORTAL_ADMIN, { query: { redirect: '', reason: null } }, here(5173))
  assert.equal(url, 'http://127.0.0.1:5174/login?portal=admin')
})

test('unknown portals resolve to null rather than a bogus URL', () => {
  assert.equal(portalLoginUrl('nobody', {}, here(5173)), '')
  assert.equal(resolvePortalSwitch('nobody', {}, here(5173)), null)
})

test('current portal prefers what the service declares over the port number', () => {
  // 管理员层入口会设置 __SMARTOPS_PORTAL_SURFACE__；端口是可配置的，不能当唯一事实来源。
  globalThis.__SMARTOPS_PORTAL_SURFACE__ = 'admin'
  try {
    assert.equal(currentPortal(here(5173)), 'admin', 'declared surface wins over the port heuristic')
  } finally {
    delete globalThis.__SMARTOPS_PORTAL_SURFACE__
  }
})

test('current portal falls back to the port when nothing is declared', () => {
  assert.equal(currentPortal(here(5174)), 'admin')
  assert.equal(currentPortal(here(5173)), 'user')
  // 未知端口按用户层处理，不把访问者误判成管理员。
  assert.equal(currentPortal(here(9999)), 'user')
})
