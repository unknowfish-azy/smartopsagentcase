import assert from 'node:assert/strict'
import test from 'node:test'
import { createAttachmentQueue, attachmentFiles } from '../src/domain/chat/attachments.ts'

const file = (name = 'error.log', type = 'text/plain', size = 20) => ({ name, type, size, lastModified: 1 })

test('file chooser, paste and drop share deduplication and count limits', () => {
  const queue = createAttachmentQueue({ createUrl: () => 'blob:preview' })
  const first = file()
  queue.add([first, first])
  assert.equal(queue.items.length, 1)
  queue.add(Array.from({ length: 5 }, (_, index) => file(`${index}.txt`)))
  assert.equal(queue.items.length, 5)
  assert.ok(queue.error)
})

test('oversized and active files never enter the upload queue', () => {
  const queue = createAttachmentQueue()
  queue.add([file('bad.svg', 'image/svg+xml'), file('large.png', 'image/png', 11 * 1024 * 1024), file('empty.txt', 'text/plain', 0)])
  assert.equal(queue.items.length, 0)
  assert.ok(queue.error)
})

test('previews are revoked on removal and disposal, normal text paste is untouched', () => {
  const released = []
  const queue = createAttachmentQueue({ createUrl: () => 'blob:preview', revokeUrl: url => released.push(url) })
  queue.add([file('screen.png', 'image/png')])
  assert.equal(queue.items[0].preview, 'blob:preview')
  queue.remove(queue.items[0].id)
  assert.deepEqual(released, ['blob:preview'])
  assert.deepEqual(attachmentFiles({ items: [{ kind: 'string', type: 'text/plain' }] }), [])
  const image = file('paste.png', 'image/png')
  assert.deepEqual(attachmentFiles({ items: [{ kind: 'file', getAsFile: () => image }] }), [image])
  queue.add([image]); queue.clear()
  assert.equal(released.length, 2)
})

test('a retry retains its upload id and uploaded result, clearing invalidates in-flight work', async () => {
  const queue = createAttachmentQueue()
  queue.add([file()])
  const requestIds = []
  await assert.rejects(queue.upload(async (_, id) => { requestIds.push(id); throw new Error('offline') }))
  assert.equal(queue.items[0].status, 'failed')
  const result = await queue.upload(async (_, id) => { requestIds.push(id); return { id: 'stored-1' } })
  assert.deepEqual(requestIds, [requestIds[0], requestIds[0]])
  assert.equal(result[0].id, 'stored-1')
  let resolveUpload
  queue.clear(); queue.add([file('second.txt')])
  const pending = queue.upload(() => new Promise(resolve => { resolveUpload = resolve }))
  queue.clear(); resolveUpload({ id: 'late' })
  await assert.rejects(pending)
  assert.deepEqual(queue.items, [])
})

test('visual attachment origins stay attached to the queued upload item', async () => {
  const queue = createAttachmentQueue({ createUrl: () => 'blob:preview' })
  queue.add([file('screen.png', 'image/png')], 'SCREENSHOT')
  const origins = []
  await queue.upload(async (_, __, sourceType) => { origins.push(sourceType); return { id: 'visual-1' } })
  assert.deepEqual(origins, ['SCREENSHOT'])
})
