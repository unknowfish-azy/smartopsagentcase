import assert from 'node:assert/strict'
import test from 'node:test'

import { THEME_MODES, normalizeThemeMode, resolveTheme } from '../src/theme.js'

test('theme modes accept light, dark, and system and reject unknown values', () => {
  assert.deepEqual(THEME_MODES, ['light', 'dark', 'system'])
  assert.equal(normalizeThemeMode('light'), 'light')
  assert.equal(normalizeThemeMode('dark'), 'dark')
  assert.equal(normalizeThemeMode('system'), 'system')
  assert.equal(normalizeThemeMode('solarized'), 'system')
  assert.equal(normalizeThemeMode(null), 'system')
})

test('system mode resolves from the operating system while explicit modes win', () => {
  assert.equal(resolveTheme('system', true), 'dark')
  assert.equal(resolveTheme('system', false), 'light')
  assert.equal(resolveTheme('light', true), 'light')
  assert.equal(resolveTheme('dark', false), 'dark')
})
