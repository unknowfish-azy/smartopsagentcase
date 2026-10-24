import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import {
  navHealthLevelForGroup,
  navHealthBadgeMap,
  navHealthBadgeTitle,
  NAV_HEALTH_LEVELS
} from '../src/navigation/navigationHealth.js'

const capabilities = {
  ai: { status: 'available' },
  knowledge: { status: 'available' },
  visual: { status: 'offline' },
  telemetry: { status: 'available' }
}

test('sentinel badge reflects telemetry capability and escalates on active fault', () => {
  assert.equal(navHealthLevelForGroup('sentinel', { capabilities }), 'ready')
  assert.equal(navHealthLevelForGroup('sentinel', { capabilities: { ...capabilities, telemetry: { status: 'degraded' } } }), 'degraded')
  assert.equal(navHealthLevelForGroup('sentinel', { capabilities, activeFault: { id: 'f1' } }), 'alert')
})

test('alert outranks degraded; offline outranks degraded', () => {
  assert.equal(navHealthLevelForGroup('health', { capabilities: { telemetry: { status: 'degraded' } }, activeFault: { id: 'f1' } }), 'alert')
  assert.equal(navHealthLevelForGroup('health', { capabilities: { telemetry: { status: 'offline' } } }), 'offline')
  assert.equal(navHealthLevelForGroup('sentinel', { capabilities: { telemetry: { status: 'degraded' }, ai: { status: 'offline' } } }), 'offline')
})

test('missing capability key reads as offline, unknown status falls back to offline', () => {
  assert.equal(navHealthLevelForGroup('sentinel', { capabilities: {} }), 'offline')
  assert.equal(navHealthLevelForGroup('health', { capabilities: { telemetry: { status: 'weird' } } }), 'offline')
})

test('groups without signal configuration get no badge', () => {
  assert.equal(navHealthLevelForGroup('home', { capabilities }), null)
  assert.equal(navHealthLevelForGroup('models', { capabilities, activeFault: { id: 'f1' } }), null)
  const badges = navHealthBadgeMap([{ id: 'home' }, { id: 'sentinel' }, { id: 'health' }], { capabilities })
  assert.deepEqual(badges, { sentinel: 'ready', health: 'ready' })
  assert.deepEqual(Object.hasOwn(navHealthBadgeMap([{ id: 'home' }], { capabilities }), 'home'), false)
})

test('badge title combines group name and level label', () => {
  assert.equal(navHealthBadgeTitle({ cn: '哨兵与自动化', label: 'SENTINEL' }, 'alert'), '哨兵与自动化 / SENTINEL · 存在活动告警')
  assert.equal(navHealthBadgeTitle(null, 'ready'), '运行正常')
  assert.ok(NAV_HEALTH_LEVELS.every(level => navHealthBadgeTitle({ cn: '健康诊断', label: 'HEALTH CENTER' }, level).length > 0))
})

test('collapsed navigation flyout is exposed as a keyboard menu', async () => {
  const source = await readFile(new URL('../src/components/navigation/PersonalSystemNavigation.vue', import.meta.url), 'utf8')
  assert.match(source, /class="navigation-flyout"[^>]*role="menu"/)
  assert.match(source, /role="menuitem"/)
  assert.match(source, /event\.key === 'Escape'/)
})
