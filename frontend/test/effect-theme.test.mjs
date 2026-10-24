import test from 'node:test'
import assert from 'node:assert/strict'
import { readCanvasPalette } from '../src/components/common/canvasTheme.js'
import { resolveEffectTheme } from '../src/components/common/effectTheme.js'

const luminance = hex => {
  const channels = hex.replace('#', '').match(/.{2}/g).map(part => parseInt(part, 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
}

test('light effects are dark ink, not faded bright particles, with normal blending', () => {
  const original = globalThis.getComputedStyle
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' })
  try {
    const light = resolveEffectTheme(readCanvasPalette({ dataset: { theme: 'light' } }))
    const dark = resolveEffectTheme(readCanvasPalette({ dataset: { theme: 'dark' } }))
    assert.equal(light.blend, 'normal')
    assert.equal(dark.blend, 'additive')
    assert.ok(luminance(light.strong) < .15)
    assert.ok(luminance(dark.strong) > .45)
    assert.ok((luminance('#ffffff') + .05) / (luminance(light.strong) + .05) >= 4.5)
  } finally { globalThis.getComputedStyle = original }
})

test('theme palette changes no geometry or quality state and has deterministic fallback', () => {
  const dark = resolveEffectTheme(readCanvasPalette(null))
  assert.equal(dark.theme, 'dark')
  assert.equal(dark.blend, 'additive')
  assert.equal('particleCount' in dark, false)
})
