import test from 'node:test'
import assert from 'node:assert/strict'
import { initialWorkspace, changePlugin, importManifest, decodeWorkspace } from '../src/domain/plugins/workspace.js'
const manifest = { id: 'my-test', name: '我的排障', description: '测试清单', version: '1.0.0', entry: 'knowledge', category: '知识与记忆', dependencies: ['ops-knowledge'] }
test('workspace dependency lifecycle protects dependents and persists custom metadata', () => {
  let state = initialWorkspace()
  state = importManifest(state, JSON.stringify(manifest))
  state = changePlugin(state, 'my-test', 'add')
  assert.throws(() => changePlugin(state, 'ops-knowledge', 'disable'), /依赖/)
  state = changePlugin(state, 'my-test', 'disable')
  state = changePlugin(state, 'ops-knowledge', 'disable')
  assert.throws(() => changePlugin(state, 'my-test', 'enable'), /先添加并启用/)
  assert.throws(() => changePlugin(state, 'ops-knowledge', 'remove'), /依赖/)
  state = changePlugin(state, 'my-test', 'remove')
  state = changePlugin(state, 'my-test', 'delete')
  assert.equal(state.custom.length, 0)
  assert.deepEqual(decodeWorkspace(JSON.stringify(state)), state)
})
test('manifest rejects scripts, external entrypoints, duplicates and invalid dependencies', () => {
  for (const overrides of [{ entry: 'https://example.com' }, { command: 'run' }, { dependencies: ['missing'] }, { id: 'ops-knowledge' }, { id: '__proto__' }, { entry: 'constructor' }, { version: 'latest' }]) {
    assert.throws(() => importManifest(initialWorkspace(), JSON.stringify({ ...manifest, ...overrides })))
  }
  assert.throws(() => importManifest(initialWorkspace(), 'not json'))
  const state = importManifest(initialWorkspace(), JSON.stringify(manifest))
  assert.deepEqual(decodeWorkspace(JSON.stringify(state)), state)
  assert.throws(() => changePlugin(initialWorkspace(), 'ops-knowledge', 'delete'))
})
