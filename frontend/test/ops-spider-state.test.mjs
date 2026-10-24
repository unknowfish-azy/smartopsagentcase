import test from 'node:test'
import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'

import { calculateOpsSpiderDragPosition, cornerPosition, getOpsSpiderActions, resolveOpsSpiderSize, resolveOpsSpiderState, snapOpsSpiderPosition, snapOpsSpiderToNearbyEdge } from '../src/components/common/opsSpiderState.js'
import { useOpsSpiderStore } from '../src/stores/opsSpider.js'

test('sleeps after thirty minutes but keeps a real route state before then', () => {
  assert.equal(resolveOpsSpiderState({ routeName: 'AgentCommandCenter', agentState: 'thinking', inactiveMs: 1799999 }), 'thinking')
  assert.equal(resolveOpsSpiderState({ routeName: 'AgentCommandCenter', agentState: 'thinking', inactiveMs: 1800000 }), 'sleeping')
})

test('uses observing state in Connections without inventing cluster status', () => {
  assert.equal(resolveOpsSpiderState({ routeName: 'Connections', agentState: 'idle', inactiveMs: 0 }), 'observing')
})

test('snaps a released pet to the closest safe corner', () => {
  assert.deepEqual(snapOpsSpiderPosition({ x: 1200, y: 750, viewportWidth: 1280, viewportHeight: 800, size: 68, inset: 20 }), { x: 1192, y: 712 })
})

test('chooses the requested corner without persisting a free-form coordinate', () => {
  assert.deepEqual(cornerPosition('top-left', { viewportWidth: 1024, viewportHeight: 768, size: 60, inset: 20 }), { x: 20, y: 20 })
})

test('keeps terminal priority with a compact Connections pet', () => {
  assert.equal(resolveOpsSpiderSize({ width: 1440, routeName: 'Connections' }), 52)
  assert.equal(resolveOpsSpiderSize({ width: 1440, routeName: 'Dashboard' }), 68)
  assert.equal(resolveOpsSpiderSize({ width: 600, routeName: 'Dashboard' }), 52)
})

test('stores a requested corner placement preference', () => {
  setActivePinia(createPinia())
  const store = useOpsSpiderStore()
  store.setCorner('bottom-right', { viewportWidth: 1280, viewportHeight: 800, size: 68, inset: 20 })
  assert.deepEqual(store.position, { x: 1192, y: 712 })
  assert.equal(store.hidden, false)
})

test('keeps a freely dragged position after release while clamping it inside the viewport', () => {
  setActivePinia(createPinia())
  const store = useOpsSpiderStore()
  store.setPosition({ x: 604, y: 318 }, { viewportWidth: 1280, viewportHeight: 800, size: 68, inset: 20 })
  assert.deepEqual(store.position, { x: 604, y: 318 })
})

test('keeps the original grab offset while directly mapping pointer movement', () => {
  const viewport = { viewportWidth: 1280, viewportHeight: 800, size: 68, inset: 20 }
  assert.deepEqual(calculateOpsSpiderDragPosition({ pointerX: 790, pointerY: 465, grabOffsetX: 30, grabOffsetY: 25, ...viewport }), { x: 760, y: 440 })
})

test('only snaps to a nearby edge after release and otherwise preserves free placement', () => {
  const viewport = { viewportWidth: 1280, viewportHeight: 800, size: 68, inset: 20, threshold: 48 }
  assert.deepEqual(snapOpsSpiderToNearbyEdge({ x: 604, y: 318, ...viewport }), { x: 604, y: 318 })
  assert.deepEqual(snapOpsSpiderToNearbyEdge({ x: 24, y: 318, ...viewport }), { x: 20, y: 318 })
})

test('exposes existing routes plus explicit local pet controls', () => {
  assert.deepEqual(getOpsSpiderActions().filter(({ route }) => route).map(({ id, route }) => [id, route]), [
    ['chat', '/chat'],
    ['agent', '/agent'],
    ['cluster', '/servers'],
    ['terminal', '/connections'],
    ['knowledge', '/knowledge']
  ])
  assert.deepEqual(getOpsSpiderActions().filter(({ action }) => action).map(({ id, action }) => [id, action]), [
    ['alerts', 'investigation'],
    ['sleep', 'sleep'],
    ['hide', 'hide']
  ])
})
