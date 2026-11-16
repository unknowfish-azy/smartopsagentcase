import assert from 'node:assert/strict'
import test from 'node:test'
import { engineNodeLayout, engineVisualState, engineFieldCenter, ENGINE_FIELD_IDS } from '../src/components/sentinel/engineField3D.js'

test('six engine nodes are laid out deterministically by id', () => {
  const a = engineNodeLayout()
  const b = engineNodeLayout()
  assert.equal(a.length, 6)
  assert.deepEqual(a.map(n => n.id), ENGINE_FIELD_IDS)
  assert.deepEqual(a, b, 'same id must never jump to a different position')
  assert.ok(a.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)))
})

test('running node breath and progress derive from the real age/period ratio', () => {
  const fresh = engineVisualState({ status: 'RUNNING', ageSec: 3, expectedPeriodSec: 30 })
  const near = engineVisualState({ status: 'RUNNING', ageSec: 27, expectedPeriodSec: 30 })
  assert.ok(fresh.animated && near.animated)
  assert.ok(near.breathSec > fresh.breathSec, 'closer to threshold breathes slower')
  assert.ok(near.progress > fresh.progress)
  assert.ok(near.progress <= 1, 'progress never exceeds the declared period')
})

test('stalled node slows further and keeps amber; error is a one-shot flash', () => {
  const stalled = engineVisualState({ status: 'STALLED', ageSec: 120, expectedPeriodSec: 30 })
  assert.equal(stalled.colorVar, '--ds-semantic-warning')
  assert.ok(stalled.breathSec >= 4)
  const error = engineVisualState({ status: 'ERROR', ageSec: 3, expectedPeriodSec: 30 })
  assert.equal(error.colorVar, '--ds-semantic-danger')
  assert.equal(error.flashOnce, true)
})

test('no-data and not-run nodes are fully static outlines', () => {
  for (const status of ['NO_DATA', 'NOT_RUN']) {
    const v = engineVisualState({ status, eventCount: 0 })
    assert.equal(v.animated, false, `${status} must not animate`)
    assert.equal(v.breathSec, 0)
    assert.equal(v.outline, true)
    assert.equal(v.progress, 0)
  }
})

test('unknown age is not guessed into motion', () => {
  const v = engineVisualState({ status: 'RUNNING', ageSec: null, expectedPeriodSec: null })
  assert.equal(v.progress, 0)
  assert.equal(v.breathSec, 0)
})

test('center aggregates only real snapshot fields', () => {
  const center = engineFieldCenter([
    { status: 'RUNNING' }, { status: 'RUNNING' }, { status: 'STALLED' }, { status: 'NOT_RUN' }, { status: 'NO_DATA' }
  ], '15:40')
  assert.equal(center.live, 2)
  assert.equal(center.quiet, 2)
  assert.equal(center.total, 5)
  assert.equal(center.generatedAtText, '15:40')
})
