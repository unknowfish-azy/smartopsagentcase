import assert from 'node:assert/strict'
import test from 'node:test'

import {
  ARCHITECTURE_LAYERS,
  TRAINING_WAVES,
  canAccess,
  getSessionRole,
  getVisibleNavigationGroups,
  ROLE_CAPABILITIES
} from '../src/security/accessModel.js'

test('falls back to operator for missing or malformed sessions', () => {
  assert.equal(getSessionRole(null), 'operator')
  assert.equal(getSessionRole('{bad json'), 'operator')
  assert.equal(getSessionRole(JSON.stringify({ username: 'alice' })), 'operator')
})

test('admin capability matrix includes management domains while operator stays scoped', () => {
  assert.equal(canAccess('operator', 'operations.read'), true)
  assert.equal(canAccess('operator', 'admin.audit'), false)
  assert.equal(canAccess('admin', 'admin.audit'), true)
  assert.equal(canAccess('admin', 'admin.security'), true)
  assert.deepEqual(ROLE_CAPABILITIES.admin.includes('admin.config'), true)
})

test('architecture catalog maps seven layers to eight training waves', () => {
  assert.equal(ARCHITECTURE_LAYERS.length, 7)
  assert.equal(TRAINING_WAVES.length, 8)
  assert.equal(TRAINING_WAVES[0].layerId, 'infrastructure')
  assert.equal(TRAINING_WAVES[7].id, 8)
})

test('navigation visibility is role aware', () => {
  const groups = [{ id: 'user', roles: ['operator', 'admin'] }, { id: 'admin', roles: ['admin'] }]
  assert.deepEqual(getVisibleNavigationGroups(groups, 'operator').map(item => item.id), ['user'])
  assert.deepEqual(getVisibleNavigationGroups(groups, 'admin').map(item => item.id), ['user', 'admin'])
})
