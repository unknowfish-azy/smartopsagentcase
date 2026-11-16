import assert from 'node:assert/strict'
import { test } from 'node:test'
import { loadSnippets, removeSnippet, saveSnippets, SNIPPETS_CAP, upsertSnippet } from '../src/components/operations/snippetStore.js'

function fakeStorage() {
  const map = new Map()
  return {
    getItem: key => map.has(key) ? map.get(key) : null,
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: key => map.delete(key)
  }
}

test('loadSnippets rejects malformed payloads silently', () => {
  const storage = fakeStorage()
  assert.deepEqual(loadSnippets(storage), [])
  storage.setItem('smartops_ops_snippets:v1', '{bad json')
  assert.deepEqual(loadSnippets(storage), [])
  storage.setItem('smartops_ops_snippets:v1', JSON.stringify({ nope: 1 }))
  assert.deepEqual(loadSnippets(storage), [])
  storage.setItem('smartops_ops_snippets:v1', JSON.stringify([{ name: '  ', command: 'x' }, { name: 'ok', command: 'ls -la' }]))
  assert.deepEqual(loadSnippets(storage), [{ id: '', name: 'ok', command: 'ls -la' }])
})

test('saveSnippets caps and drops invalid entries', () => {
  const storage = fakeStorage()
  const many = Array.from({ length: SNIPPETS_CAP + 5 }, (_, index) => ({ id: `s${index}`, name: `n${index}`, command: 'uptime' }))
  assert.equal(saveSnippets(many, storage), true)
  const loaded = loadSnippets(storage)
  assert.equal(loaded.length, SNIPPETS_CAP)
  assert.equal(loaded[0].id, 's5')
})

test('upsertSnippet edits by id and appends new ones', () => {
  const list = upsertSnippet([], { name: '状态', command: 'systemctl status app' }, () => 'id-1')
  assert.equal(list.length, 1)
  const edited = upsertSnippet(list, { id: 'id-1', name: '状态-改', command: 'systemctl status app' })
  assert.equal(edited[0].name, '状态-改')
  assert.equal(upsertSnippet(list, { name: '', command: '' }).length, 1)
})

test('removeSnippet filters by id', () => {
  const list = [{ id: 'a', name: 'A', command: 'a' }, { id: 'b', name: 'B', command: 'b' }]
  assert.deepEqual(removeSnippet(list, 'a').map(item => item.id), ['b'])
})
