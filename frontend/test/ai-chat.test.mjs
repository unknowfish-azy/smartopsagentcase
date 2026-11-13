import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { personalSystemGroups } from '../src/navigation/personalSystemNavigation.js'

const dashboardSource = await readFile(new URL('../src/views/dashboard/DashboardView.vue', import.meta.url), 'utf8')
const chatSource = await readFile(new URL('../src/views/chat/ChatView.vue', import.meta.url), 'utf8')
const panelSource = await readFile(new URL('../src/components/ai/AiChatPanel.vue', import.meta.url), 'utf8')

test('homepage uses Bento dashboard without a duplicate chat panel (T19 D1 裁决变更为采纳 Bento)', () => {
  assert.match(dashboardSource, /<DashboardBento/)
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

test('chat panel makes provider degradation and inspector rejection visible', () => {
  assert.match(panelSource, /降级模式/)
  assert.match(panelSource, /REJECTED/)
})

test('chat panel exposes safe run correlation diagnostics for support', () => {
  assert.match(panelSource, /运行诊断/)
  assert.match(panelSource, /request_id/)
  assert.match(panelSource, /task_id/)
  assert.match(panelSource, /run_id/)
  assert.match(panelSource, /message\.metadata\?\.run_event/)
})
