import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { shouldBeginOpsSpiderDrag, resolveOpsSpiderPanelPosition } from '../src/components/common/opsSpiderState.js'

const variables = await readFile(new URL('../src/assets/styles/variables.css', import.meta.url), 'utf8')
const petStyles = await readFile(new URL('../src/components/common/OpsSpiderPet.vue', import.meta.url), 'utf8')

test('does not begin pet dragging while the action menu is open', () => {
  assert.equal(shouldBeginOpsSpiderDrag({ menuOpen: true, interactiveTarget: false }), false)
  assert.equal(shouldBeginOpsSpiderDrag({ menuOpen: false, interactiveTarget: true }), false)
  assert.equal(shouldBeginOpsSpiderDrag({ menuOpen: false, interactiveTarget: false }), true)
})

test('defines light and dark pet surface tokens and consumes them in the menu', () => {
  assert.match(variables, /--pet-action-bg:\s*#071018;/)
  assert.match(variables, /\[data-theme='light'\][\s\S]*--pet-action-bg:\s*#ffffff;/)
  assert.match(petStyles, /background:var\(--pet-action-bg\)/)
  assert.match(petStyles, /color:var\(--pet-action-text\)/)
  assert.match(petStyles, /border:1px solid var\(--pet-action-border\)/)
})

test('places a panel above a bottom-right pet without changing pet coordinates', () => {
  const input = { x: 1352, y: 812, size: 68, panelWidth: 248, panelHeight: 210, viewportWidth: 1440, viewportHeight: 900, safeLeft: 272 }
  assert.deepEqual(resolveOpsSpiderPanelPosition(input), { left: -180, top: -222 })
  assert.equal(input.x, 1352)
  assert.equal(input.y, 812)
})

test('places top-edge panels below the pet and clamps wide panels on narrow screens', () => {
  assert.deepEqual(resolveOpsSpiderPanelPosition({ x: 272, y: 20, size: 68, panelWidth: 248, panelHeight: 210, viewportWidth: 1440, viewportHeight: 900, safeLeft: 272 }), { left: 0, top: 80 })
  const input = { x: 20, y: 812, size: 52, panelWidth: 300, panelHeight: 200, viewportWidth: 320, viewportHeight: 900, safeLeft: 272 }
  const panel = resolveOpsSpiderPanelPosition(input)
  assert.equal(panel.left + input.x, 12)
  assert.ok(panel.top + input.y >= 12)
})
