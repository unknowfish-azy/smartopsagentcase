import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  PORTAL_REGISTRY,
  PORTAL_IDS,
  PUBLIC_PORTALS,
  portalSpec,
  portalLabel,
  portalRole,
  isPublicPortal,
  isSensitivePortal,
  portalHome
} from '../src/security/portalCatalog.js'

const EXPECTED = [
  { id: 'user', label: '用户层', role: 'operator', port: 5173, idle: 1800, public: true, sensitive: false },
  { id: 'admin', label: '管理层', role: 'admin', port: 5174, idle: 600, public: false, sensitive: true },
  { id: 'enterprise', label: '企业管理层', role: 'enterprise', port: 5175, idle: 900, public: false, sensitive: false },
  { id: 'audit', label: '审计合规层', role: 'auditor', port: 5176, idle: 600, public: false, sensitive: true },
  { id: 'command', label: '决策指挥层', role: 'commander', port: 5177, idle: 600, public: false, sensitive: true },
  { id: 'open', label: '开放生态层', role: 'partner', port: 5178, idle: 1800, public: false, sensitive: false }
]

test('registry registers exactly six parallel portals in declaration order', () => {
  assert.deepEqual(PORTAL_IDS, EXPECTED.map(p => p.id))
  assert.equal(PORTAL_IDS.length, 6)
})

test('every portal exposes a complete, consistent spec', () => {
  for (const want of EXPECTED) {
    const got = PORTAL_REGISTRY[want.id]
    assert.ok(got, `missing portal ${want.id}`)
    assert.equal(got.id, want.id)
    assert.equal(got.label, want.label)
    assert.equal(got.role, want.role)
    assert.equal(got.port, want.port)
    assert.equal(got.idle, want.idle)
    assert.equal(got.public, want.public)
    assert.equal(got.sensitive, want.sensitive)
    assert.ok(typeof got.purpose === 'string' && got.purpose.trim().length > 0, `purpose missing for ${want.id}`)
  }
})

test('ports are unique so each portal serves on its own address', () => {
  const ports = PORTAL_IDS.map(id => PORTAL_REGISTRY[id].port)
  assert.equal(new Set(ports).size, ports.length)
})

test('only the user portal is public; everything else is concealed from the login page', () => {
  assert.deepEqual(PUBLIC_PORTALS, ['user'])
  for (const id of PORTAL_IDS) {
    assert.equal(isPublicPortal(id), id === 'user')
  }
})

test('sensitive portals are exactly admin / audit / command (MFA + strict throttling)', () => {
  const sensitive = PORTAL_IDS.filter(id => isSensitivePortal(id)).sort()
  assert.deepEqual(sensitive, ['admin', 'audit', 'command'])
})

test('helper accessors fail closed for unknown portals', () => {
  assert.equal(portalSpec('ghost'), null)
  assert.equal(portalLabel('ghost'), 'ghost')
  assert.equal(portalRole('ghost'), null)
  assert.equal(isPublicPortal('ghost'), false)
  assert.equal(isSensitivePortal('ghost'), false)
  assert.equal(isPublicPortal(null), false)
})

test('portal home is derived from the registry, never hardcoded', () => {
  assert.equal(portalHome('user'), '/')
  assert.equal(portalHome('admin'), '/admin')
  assert.equal(portalHome('enterprise'), '/enterprise')
  assert.equal(portalHome('audit'), '/audit')
  assert.equal(portalHome(undefined), '/')
  assert.equal(portalHome(null), '/')
})

test('frontend registry stays isomorphic with backend PortalCatalog.java', async () => {
  // 单一事实来源：前端 portalCatalog.js 必须与后端 PortalCatalog.REGISTRY 在
  // id / role / idle / public / sensitive 上完全一致，否则会出现「前端放行、后端拒绝」
  // 或「前端隐藏、后端其实不敏感」的鉴权裂口。
  const source = await readFile(
    new URL('../../backend/src/main/java/com/smartops/security/PortalCatalog.java', import.meta.url),
    'utf8'
  )
  const pattern = /new PortalSpec\("(\w+)",\s*"([^"]*)",\s*"(\w+)",\s*"(ROLE_\w+)",\s*(\d+),\s*(true|false),\s*(true|false)/g
  const parsed = new Map()
  let match
  while ((match = pattern.exec(source)) !== null) {
    const [, id, , role, authority, idle, pub, sensitive] = match
    parsed.set(id, { role, authority, idle: Number(idle), public: pub === 'true', sensitive: sensitive === 'true' })
  }
  assert.equal(parsed.size, 6, `expected 6 backend portal specs, parsed ${parsed.size}`)

  // 后端 authority 由注册中心显式声明（非简单派生），必须一一唯一、与角色对应，
  // 防止 AuthController.establish 的授权派生漂移。
  const expectedAuthority = {
    user: 'ROLE_OPERATOR', admin: 'ROLE_ADMIN', enterprise: 'ROLE_ENTERPRISE',
    audit: 'ROLE_AUDIT', command: 'ROLE_COMMAND', open: 'ROLE_OPEN'
  }
  const seenAuthorities = new Set()
  for (const id of PORTAL_IDS) {
    const back = parsed.get(id)
    assert.ok(back, `backend registry missing portal ${id}`)
    const front = PORTAL_REGISTRY[id]
    assert.equal(front.role, back.role, `role mismatch on ${id}`)
    assert.equal(front.idle, back.idle, `idle mismatch on ${id}`)
    assert.equal(front.public, back.public, `public mismatch on ${id}`)
    assert.equal(front.sensitive, back.sensitive, `sensitive mismatch on ${id}`)
    assert.equal(back.authority, expectedAuthority[id], `authority drift on ${id}`)
    assert.match(back.authority, /^ROLE_[A-Z_]+$/)
    assert.ok(!seenAuthorities.has(back.authority), `authority ${back.authority} reused across portals`)
    seenAuthorities.add(back.authority)
  }
})
