import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { personalSystemGroups } from '../src/navigation/personalSystemNavigation.js'

const dashboardSource = await readFile(new URL('../src/views/dashboard/DashboardView.vue', import.meta.url), 'utf8')
const chatSource = await readFile(new URL('../src/views/chat/ChatView.vue', import.meta.url), 'utf8')

test('homepage keeps its carousel without a duplicate chat panel', () => {
  assert.match(dashboardSource, /<HomeOrbitCarousel/)
  assert.doesNotMatch(dashboardSource, /AiChatPanel|home-chat-section/)
})

test('chat view exposes the v0-inspired conversation controls', () => {
  assert.match(chatSource, /<AiChatPanel/)
  assert.match(chatSource, /<ChatHistory/)
})

test('navigation keeps AI chat next to the homepage entry', () => {
  const ids = personalSystemGroups.map(group => group.id)
  assert.deepEqual(ids.slice(0, 2), ['home', 'ai-chat'])
})
