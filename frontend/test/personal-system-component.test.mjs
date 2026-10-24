import assert from 'node:assert/strict'
import test from 'node:test'

import { navigationGroupView, personalSystemGroups } from '../src/navigation/personalSystemNavigation.js'

test('marks an expanded child group as toggleable while direct groups stay direct links', () => {
  const agent = navigationGroupView(personalSystemGroups.find(group => group.id === 'agent'), ['agent'])
  const knowledge = navigationGroupView(personalSystemGroups.find(group => group.id === 'knowledge'), ['agent'])

  assert.deepEqual(agent, { expandable: true, expanded: true })
  assert.deepEqual(knowledge, { expandable: false, expanded: false })
})
