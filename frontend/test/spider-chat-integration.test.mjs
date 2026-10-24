import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const spiderSource = await readFile(new URL('../src/components/common/OpsSpiderPet.vue', import.meta.url), 'utf8')
const spiderStateSource = await readFile(new URL('../src/components/common/opsSpiderState.js', import.meta.url), 'utf8')
const chatSource = await readFile(new URL('../src/components/ai/AiChatPanel.vue', import.meta.url), 'utf8')
const chatStoreSource = await readFile(new URL('../src/stores/aiChat.js', import.meta.url), 'utf8').catch(() => '')

test('spider menu exposes distributed actions and a chat handoff', () => {
  assert.match(spiderStateSource, /id:\s*'chat'/)
  assert.match(spiderStateSource, /direction:\s*'upper-left'/)
  assert.match(spiderStateSource, /direction:\s*'lower-right'/)
  assert.match(spiderSource, /action-orbit/)
  assert.match(spiderSource, /AI 对话|AI CHAT/)
})

test('spider actions avoid the navigation rail when the pet is on the left', () => {
  assert.match(spiderSource, /menu-side-left/)
  assert.match(spiderSource, /navigationSafeLeft|sidebarSafeLeft/)
})

test('dedicated chat page and spider use a shared AI conversation store', () => {
  assert.ok(chatStoreSource.length > 0, 'shared AI chat store should exist')
  assert.match(chatStoreSource, /sendMessage/)
  assert.match(chatSource, /useAiChatStore/)
  assert.match(spiderSource, /useAiChatStore/)
})
