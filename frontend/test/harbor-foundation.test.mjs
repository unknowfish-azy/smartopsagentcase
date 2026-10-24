import test from 'node:test'
import assert from 'node:assert/strict'
import { connectionPresentation, createRequestGate, repositoryWithinProject, filterArtifacts } from '../src/components/operations/harborState.js'

test('configuration and old successful checks never imply current health', () => {
  assert.equal(connectionPresentation(null, false, 1000).state, 'UNCHECKED')
  const check = { state: 'READABLE', checkedAt: new Date(1000).toISOString() }
  assert.equal(connectionPresentation(check, true, 1000).state, 'CHECKING')
  assert.equal(connectionPresentation(check, false, 301001).state, 'STALE')
  assert.equal(connectionPresentation(check, false, 1000).state, 'READABLE')
  assert.equal(connectionPresentation({ state: 'AUTHORIZATION' }, false, 1000).state, 'AUTHORIZATION')
})

test('request gate rejects stale responses and invalidation after target change', () => {
  const gate = createRequestGate()
  const old = gate.begin()
  assert.equal(gate.current(old), true)
  const latest = gate.begin()
  assert.equal(gate.current(old), false)
  assert.equal(gate.current(latest), true)
  gate.invalidate()
  assert.equal(gate.current(latest), false)
})

test('repository identity retains nested path and never strips unrelated prefixes', () => {
  assert.equal(repositoryWithinProject('demo', 'demo/team/image'), 'team/image')
  assert.equal(repositoryWithinProject('demo', 'other/image'), '')
  assert.equal(repositoryWithinProject('demo', 'demo/../image'), '')
})

test('artifact page filter matches tags or digest and does not claim server search', () => {
  const artifacts = [{ digest: 'sha256:abc', tags: ['release-v1'] }, { digest: 'sha256:def', tags: [] }]
  assert.equal(filterArtifacts(artifacts, 'RELEASE').length, 1)
  assert.equal(filterArtifacts(artifacts, 'def')[0].digest, 'sha256:def')
})
