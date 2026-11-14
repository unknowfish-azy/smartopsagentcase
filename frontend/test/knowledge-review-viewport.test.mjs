import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ZOOM_MAX,
  ZOOM_MIN,
  clampPan,
  clampZoom,
  panBounds,
  stepZoom,
  zoomAt,
  zoomPercent
} from '../src/views/knowledge/reviewGraph/useGraphViewport.js'

test('zoom stays inside the 50%–200% window and rounds to two decimals', () => {
  assert.equal(clampZoom(0.1), ZOOM_MIN)
  assert.equal(clampZoom(9), ZOOM_MAX)
  assert.equal(clampZoom(Number.NaN), 1)
  assert.equal(clampZoom(1.23456), 1.23)
  assert.equal(stepZoom(1, 1), 1.1)
  assert.equal(stepZoom(ZOOM_MAX, 1), ZOOM_MAX)
  assert.equal(stepZoom(ZOOM_MIN, -1), ZOOM_MIN)
})

test('zoom below 100% is centred and cannot be dragged sideways', () => {
  const bounds = panBounds(800, 0.5)
  assert.deepEqual(bounds, { min: 200, max: 200 })
  assert.equal(clampPan(0, 800, 0.5), 200)
  assert.equal(clampPan(-500, 800, 0.5), 200)
})

test('zoom above 100% clamps panning to the scaled content edges', () => {
  assert.deepEqual(panBounds(800, 2), { min: -800, max: 0 })
  assert.equal(clampPan(120, 800, 2), 0)
  assert.equal(clampPan(-2000, 800, 2), -800)
  assert.equal(clampPan(-320, 800, 2), -320)
})

test('wheel zoom keeps the point under the pointer anchored', () => {
  const pointerX = 300
  const before = { zoom: 1, panX: 0 }
  const contentX = (pointerX - before.panX) / before.zoom

  const result = zoomAt({ ...before, viewportWidth: 800, pointerX, nextZoom: 1.5 })
  assert.equal(result.zoom, 1.5)
  // 缩放后同一内容点仍落在指针下（受 pan 夹紧影响时允许 0.5px 误差）。
  const afterContentX = (pointerX - result.panX) / result.zoom
  assert.ok(Math.abs(afterContentX - contentX) < 0.5, `内容点应保持不动，实际 ${afterContentX}`)
})

test('percent label never renders fractions', () => {
  assert.equal(zoomPercent(1), '100%')
  assert.equal(zoomPercent(1.234), '123%')
  assert.equal(zoomPercent(0.5), '50%')
})
