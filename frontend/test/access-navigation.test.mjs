import assert from 'node:assert/strict'
import test from 'node:test'

import { personalSystemGroups, routeMetaFor } from '../src/navigation/personalSystemNavigation.js'
import { getVisibleNavigationGroups } from '../src/security/accessModel.js'

test('admin navigation exposes management and architecture entries', () => {
  const groups = getVisibleNavigationGroups(personalSystemGroups, 'admin')
  assert.deepEqual(groups.filter(group => group.roles?.includes('admin')).map(group => group.id), ['admin', 'architecture'])
  assert.deepEqual(routeMetaFor('AdminControlCenter').roles, ['admin'])
})

test('operator navigation does not expose management entries', () => {
  const groups = getVisibleNavigationGroups(personalSystemGroups, 'operator')
  assert.equal(groups.some(group => group.id === 'admin'), false)
  assert.equal(groups.some(group => group.id === 'architecture'), false)
})
