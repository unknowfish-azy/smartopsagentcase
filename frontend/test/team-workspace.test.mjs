import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

test('team permissions and API keep platform and team identities separate', async () => {
  const server = await createServer({ root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true }, logLevel: 'silent' })
  try {
    const { assignableRoles, canManageMember, isTeamManager } = await server.ssrLoadModule('/src/domain/team/permissions.js')
    assert.deepEqual(assignableRoles('owner'), ['admin', 'member', 'viewer'])
    assert.deepEqual(assignableRoles('admin'), ['member', 'viewer'])
    assert.deepEqual(assignableRoles('viewer'), [])
    assert.equal(isTeamManager('member'), false)
    assert.equal(canManageMember('owner', 'owner', false), false)
    assert.equal(canManageMember('admin', 'admin', false), false)
    assert.equal(canManageMember('owner', 'member', true), false)
    assert.equal(canManageMember('admin', 'viewer', false), true)
    const { default: request } = await server.ssrLoadModule('/src/utils/request.js')
    const { teamApi, adminTeamsApi } = await server.ssrLoadModule('/src/api/teams.js')
    const calls = []
    request.defaults.adapter = async config => {
      calls.push({ url: config.url, method: config.method, body: config.data ? JSON.parse(config.data) : undefined, password: config.headers.get('X-Admin-Password') })
      return { data: { code: 200, data: { items: [], total: 0 } }, status: 200, statusText: 'OK', headers: {}, config }
    }
    await teamApi.create({ name: 'team', description: '' })
    assert.deepEqual(calls.at(-1).body, { name: 'team', description: '' })
    await teamApi.respond(7, false)
    assert.equal(calls.at(-1).url, '/api/teams/invitations/7/respond')
    assert.deepEqual(calls.at(-1).body, { accept: false })
    await teamApi.removeMember(4, 9)
    assert.equal(calls.at(-1).url, '/api/teams/4/members/9')
    assert.equal(calls.at(-1).method, 'delete')
    await adminTeamsApi.setStatus(4, 'frozen', 'mock-only')
    assert.equal(calls.at(-1).password, 'mock-only')
    assert.deepEqual(calls.at(-1).body, { status: 'frozen' })
    await teamApi.list()
    assert.equal(calls.at(-1).password, undefined)
    assert.equal(request.defaults.headers.common['X-Admin-Password'], undefined)
  } finally { await server.close() }
})
