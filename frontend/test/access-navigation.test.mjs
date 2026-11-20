import assert from 'node:assert/strict'
import test from 'node:test'

import { personalSystemGroups, routeMetaFor } from '../src/navigation/personalSystemNavigation.js'
import { getVisibleNavigationGroups } from '../src/security/accessModel.js'

test('user-layer navigation exposes no management entries for any role', () => {
  // 管理控制台与架构总览已迁到独立的 5174 服务：用户层侧栏对任何角色都不再出现管理入口。
  for (const role of ['operator', 'admin']) {
    const groups = getVisibleNavigationGroups(personalSystemGroups, role)
    assert.equal(groups.some(group => group.id === 'admin'), false)
    assert.equal(groups.some(group => group.id === 'architecture'), false)
    assert.equal(groups.some(group => group.roles?.includes('admin')), false)
  }
})

test('management route metadata stays administrator-only', () => {
  assert.deepEqual(routeMetaFor('AdminControlCenter').roles, ['admin'])
})
