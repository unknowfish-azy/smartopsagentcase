import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveWhaleQuality } from '../src/components/common/whaleQuality.js'
import { createWhalePointCloud } from '../src/components/common/whaleShape.js'
import { getJellyfishProfile, getWhaleBreath, getWhaleMotionProfile, getWhaleSwimMotion } from '../src/components/common/organismMotion.js'
import { createStellarField, resolveStellarQuality } from '../src/components/common/stellarOcean.js'

test('reduced motion uses a static low-density whale', () => {
  assert.deepEqual(resolveWhaleQuality({ width: 1440, dpr: 2, reducedMotion: true }), {
    tier: 'low',
    particleCount: 4200,
    animate: false
  })
})

test('desktop uses a denser whale than a mobile viewport', () => {
  const desktop = resolveWhaleQuality({ width: 1920, dpr: 1, reducedMotion: false })
  const mobile = resolveWhaleQuality({ width: 375, dpr: 2, reducedMotion: false })

  assert.equal(desktop.tier, 'high')
  assert.equal(desktop.particleCount, 18000)
  assert.equal(mobile.tier, 'low')
  assert.equal(mobile.particleCount, 4200)
  assert.ok(desktop.particleCount > mobile.particleCount)
})

test('whale point cloud keeps every particle finite and assigns structural regions', () => {
  const cloud = createWhalePointCloud(240)

  assert.equal(cloud.positions.length, 720)
  assert.equal(cloud.regions.length, 240)
  assert.ok([...cloud.positions].every(Number.isFinite))
  assert.ok(new Set(cloud.regions).has(0))
  assert.ok(new Set(cloud.regions).has(1))
  assert.ok(new Set(cloud.regions).has(2))
})

test('whale motion uses a staged breath rather than a continuous spin', () => {
  const profile = getWhaleMotionProfile('executing')
  const inhale = getWhaleBreath(profile.duration * 1000 * 0.16, 'executing')
  const hold = getWhaleBreath(profile.duration * 1000 * 0.33, 'executing')
  const exhale = getWhaleBreath(profile.duration * 1000 * 0.58, 'executing')

  assert.equal(profile.rotationLimit, 0.02)
  assert.equal(inhale.phase, 'inhale')
  assert.equal(hold.phase, 'hold')
  assert.equal(exhale.phase, 'exhale')
  assert.ok(exhale.exhale > 0)
})

test('whale swims horizontally with a gentle vertical drift and limited roll', () => {
  const start = getWhaleSwimMotion(0, 'idle')
  const quarter = getWhaleSwimMotion(getWhaleMotionProfile('idle').swimDuration * 250, 'idle')
  const threeQuarter = getWhaleSwimMotion(getWhaleMotionProfile('idle').swimDuration * 750, 'idle')

  assert.equal(start.x, 0)
  assert.ok(quarter.x > 0.35)
  assert.ok(threeQuarter.x < -0.35)
  assert.ok(Math.abs(quarter.y) <= 0.1)
  assert.ok(Math.abs(quarter.rotation) <= 0.03)
})

test('jellyfish keeps a distinct, faster cadence than the whale', () => {
  assert.ok(getJellyfishProfile('thinking').driftDuration < getWhaleMotionProfile('thinking').duration)
  assert.ok(getJellyfishProfile('observing').scanStrength > getJellyfishProfile('idle').scanStrength)
})

test('stellar ocean uses layered stars and sparse chain data across quality tiers', () => {
  const high = resolveStellarQuality({ width: 1920, dpr: 1, reducedMotion: false })
  const low = resolveStellarQuality({ width: 375, dpr: 2, reducedMotion: false })
  const field = createStellarField(low)

  assert.ok(high.totalStars > low.totalStars)
  assert.equal(low.totalStars, 260)
  assert.equal(field.layers.length, 3)
  assert.ok(field.layers.every((layer) => layer.positions.length > 0))
  assert.ok(field.chainPairs.length > 0)
  assert.ok([...field.layers.flatMap((layer) => [...layer.positions])].every(Number.isFinite))
})
