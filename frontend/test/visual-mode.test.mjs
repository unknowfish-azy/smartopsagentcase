import assert from 'node:assert/strict'
import test from 'node:test'

import {
  VISUAL_MODES,
  isLightweightVisualMode,
  normalizeVisualMode,
  setVisualMode,
  visualMode
} from '../src/visual/visualMode.js'
import { resolveTheme } from '../src/theme.js'
import { readFile } from 'node:fs/promises'

test('visual preference persists safely and does not overwrite theme', () => {
  const values = new Map([['smartops_theme', 'light']])
  const previous = globalThis.localStorage
  globalThis.localStorage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  try {
    setVisualMode('reduced-motion')
    assert.equal(values.get('smartops_visual_mode'), 'reduced-motion')
    assert.equal(values.get('smartops_theme'), 'light')
    globalThis.localStorage.setItem = () => { throw new Error('unavailable') }
    assert.doesNotThrow(() => setVisualMode('unknown'))
    assert.equal(visualMode.value, 'balanced')
  } finally { globalThis.localStorage = previous; setVisualMode('balanced') }
})

test('reduced visual preference reaches Canvas and stops carousel autoplay', async () => {
  for (const path of ['components/common/CanvasParticleWhale.vue', 'components/common/CanvasAmbientField.vue', 'components/ui/home-orbit-carousel.vue']) {
    const content = await readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')
    assert.match(content, /visualMode/)
    assert.match(content, /reduced-motion/)
  }
})

test('visual modes expose the supported values and default to balanced', () => {
  assert.deepEqual(VISUAL_MODES, ['balanced', 'lightweight', 'reduced-motion'])
  assert.equal(normalizeVisualMode(undefined), 'balanced')
  assert.equal(normalizeVisualMode('unknown'), 'balanced')
})

test('visual mode normalizes independently from color theme', () => {
  assert.equal(normalizeVisualMode('lightweight'), 'lightweight')
  assert.equal(normalizeVisualMode('reduced-motion'), 'reduced-motion')
  assert.equal(resolveTheme('light', true), 'light')
})

test('explicit visual mode changes persist without changing the theme preference', () => {
  setVisualMode('lightweight')
  assert.equal(visualMode.value, 'lightweight')
  assert.equal(isLightweightVisualMode.value, true)

  setVisualMode('balanced')
  assert.equal(visualMode.value, 'balanced')
  assert.equal(isLightweightVisualMode.value, false)
})
