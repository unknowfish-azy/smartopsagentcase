import assert from 'node:assert/strict'
import test from 'node:test'

import { navigationGroupView, personalSystemGroups } from '../src/navigation/personalSystemNavigation.js'

test('marks an expanded child group as toggleable while direct groups stay direct links', () => {
  const agent = navigationGroupView(personalSystemGroups.find(group => group.id === 'agent'), ['agent'])
  const knowledge = navigationGroupView(personalSystemGroups.find(group => group.id === 'knowledge'), ['agent'])

  assert.deepEqual(agent, { expandable: true, expanded: true })
  // 知识中心已收纳图谱与科研助手，成为展开组；团队协作入口已收敛至顶部切换器，不在侧栏。
  assert.deepEqual(knowledge, { expandable: true, expanded: false })
})
