import test from 'node:test'
import assert from 'node:assert/strict'
import { observeCanvasTheme, readCanvasPalette } from '../src/components/common/canvasTheme.js'

test('canvas palette returns safe dark defaults without a browser document', () => {
  const palette = readCanvasPalette(null)
  assert.equal(palette.background, '#05090d')
  assert.equal(palette.primaryStrong, '#7ad7f5')
})

test('canvas palette reads CSS variables and reacts to data-theme mutations', () => {
  const root = { dataset: { theme: 'light' } }
  const lightVariables = {
    '--smart-bg': '#f4f7f9', '--smart-surface': '#ffffff', '--smart-primary': '#0e5f92',
    '--smart-primary-strong': '#084b73', '--smart-muted': '#4d606c',
    '--smart-border': 'rgba(16, 53, 70, .22)', '--smart-primary-soft': 'rgba(14, 95, 146, .08)', '--smart-text': '#10212b'
  }
  const darkVariables = {
    '--smart-bg': '#05090d', '--smart-surface': '#071018', '--smart-primary': '#2496ed',
    '--smart-primary-strong': '#7ad7f5', '--smart-muted': '#92a6b5',
    '--smart-border': 'rgba(159, 190, 207, .18)', '--smart-primary-soft': 'rgba(122, 215, 245, .12)', '--smart-text': '#e8f2f7'
  }
  const originalGetComputedStyle = globalThis.getComputedStyle
  const originalMutationObserver = globalThis.MutationObserver
  let mutationCallback
  let disconnected = false
  globalThis.getComputedStyle = () => ({
    getPropertyValue: name => (root.dataset.theme === 'light' ? lightVariables : darkVariables)[name] || ''
  })
  globalThis.MutationObserver = class {
    constructor(callback) { mutationCallback = callback }
    observe() {}
    disconnect() { disconnected = true }
  }
  try {
    const lightPalette = readCanvasPalette(root)
    assert.equal(lightPalette.primary, '#0e5f92')
    let updatedPalette
    const stop = observeCanvasTheme(nextPalette => { updatedPalette = nextPalette }, root)
    root.dataset.theme = 'dark'
    mutationCallback([{ attributeName: 'data-theme' }])
    assert.equal(updatedPalette.primaryStrong, '#7ad7f5')
    assert.equal(updatedPalette.background, '#05090d')
    stop()
    assert.equal(disconnected, true)
  } finally {
    globalThis.getComputedStyle = originalGetComputedStyle
    globalThis.MutationObserver = originalMutationObserver
  }
})