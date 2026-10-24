import test from 'node:test'
import assert from 'node:assert/strict'
import {
  createCompanionEvent,
  createCompanionEventBus
} from '../src/domain/companion/eventBus.ts'

test('creates events with metadata and an ISO timestamp', () => {
  const event = createCompanionEvent({
    type: 'companion.ready',
    source: 'companion-panel',
    contextId: 'ctx-1',
    payload: { ready: true }
  })

  assert.equal(event.type, 'companion.ready')
  assert.equal(event.source, 'companion-panel')
  assert.equal(event.contextId, 'ctx-1')
  assert.equal(event.payload.ready, true)
  assert.match(event.timestamp, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
  assert.ok(event.id)
  assert.ok(Object.isFrozen(event))
})

test('clones and freezes nested payloads as an immutable snapshot', () => {
  const payload = { nested: { value: 1 }, items: [{ label: 'original' }] }
  const event = createCompanionEvent({ type: 'snapshot', source: 'test', contextId: 'ctx', payload })
  payload.nested.value = 2
  payload.items[0].label = 'changed'

  assert.equal(event.payload.nested.value, 1)
  assert.equal(event.payload.items[0].label, 'original')
  assert.ok(Object.isFrozen(event.payload))
  assert.ok(Object.isFrozen(event.payload.nested))
  assert.ok(Object.isFrozen(event.payload.items))
  assert.throws(() => { event.payload.nested.value = 3 }, TypeError)
})

test('publishes only to subscribers for the matching type', () => {
  const bus = createCompanionEventBus()
  const received = []
  bus.subscribe('alpha', event => received.push(event.type))
  bus.subscribe('beta', event => received.push(event.type))

  bus.publish(createCompanionEvent({ type: 'alpha', source: 'test', contextId: 'ctx', payload: {} }))
  assert.deepEqual(received, ['alpha'])
})

test('unsubscribe and clear stop future deliveries', () => {
  const bus = createCompanionEventBus()
  let calls = 0
  const unsubscribe = bus.subscribe('alpha', () => { calls += 1 })
  const event = createCompanionEvent({ type: 'alpha', source: 'test', contextId: 'ctx', payload: {} })
  bus.publish(event)
  unsubscribe()
  bus.publish(event)
  assert.equal(calls, 1)

  bus.subscribe('alpha', () => { calls += 1 })
  bus.clear()
  bus.publish(event)
  assert.equal(calls, 1)
})

test('rejects malformed event metadata and malformed published events', () => {
  for (const field of ['type', 'source', 'contextId']) {
    const input = { type: 'valid', source: 'test', contextId: 'ctx', payload: {} }
    input[field] = '   '
    assert.throws(() => createCompanionEvent(input), /must be a non-empty string/)
  }

  const bus = createCompanionEventBus()
  assert.throws(() => bus.publish({ type: 'x', source: 'test', contextId: 'ctx', payload: {} }), /created by createCompanionEvent/)
  assert.throws(() => bus.subscribe('', () => {}), /type must be a non-empty string/)
  assert.throws(() => bus.subscribe('x', null), /handler must be a function/)
})

test('rejects mutable non-JSON payload values, cycles, and non-finite numbers', () => {
  const base = { type: 'snapshot', source: 'test', contextId: 'ctx' }
  assert.throws(() => createCompanionEvent({ ...base, payload: new Map([['key', 'value']]) }), /plain objects and arrays/)
  assert.throws(() => createCompanionEvent({ ...base, payload: new Date() }), /plain objects and arrays/)
  assert.throws(() => createCompanionEvent({ ...base, payload: { value: Infinity } }), /finite numbers/)
  const cyclic = {}
  cyclic.self = cyclic
  assert.throws(() => createCompanionEvent({ ...base, payload: cyclic }), /must not contain cycles/)
})

test('published event is frozen for handlers', () => {
  const bus = createCompanionEventBus()
  let delivered
  bus.subscribe('alpha', event => { delivered = event })
  const published = bus.publish(createCompanionEvent({ type: 'alpha', source: 'test', contextId: 'ctx', payload: { ok: true } }))

  assert.strictEqual(delivered, published)
  assert.ok(Object.isFrozen(delivered))
  assert.throws(() => { delivered.source = 'mutated' }, TypeError)
})
