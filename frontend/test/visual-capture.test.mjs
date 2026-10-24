import assert from 'node:assert/strict'
import test from 'node:test'
import { captureScreen, stopMediaStream, sourceLabel } from '../src/domain/chat/visualCapture.js'

test('source labels are stable for visual attachment origins', () => {
  assert.equal(sourceLabel('SCREENSHOT'), '截屏')
  assert.equal(sourceLabel('CAMERA'), '拍照')
  assert.equal(sourceLabel('CLIPBOARD'), '剪贴板')
})

test('stopMediaStream releases every track', () => {
  const stopped = []
  stopMediaStream({ getTracks: () => [{ stop: () => stopped.push(1) }, { stop: () => stopped.push(2) }] })
  assert.deepEqual(stopped, [1, 2])
})

test('screen capture rejects when browser capability is unavailable', async () => {
  await assert.rejects(captureScreen({ mediaDevices: {} }), /SCREEN_CAPTURE_UNAVAILABLE/)
})
