const EVENT_MARKER = Symbol('companion-event')

function requireNonEmptyString(value, field) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new TypeError(`${field} must be a non-empty string`)
  }
  return value.trim()
}

function cloneJson(value, path = 'payload', seen = new Set()) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError(`${path} must contain only finite numbers`)
    return value
  }
  if (Array.isArray(value)) {
    if (seen.has(value)) throw new TypeError(`${path} must not contain cycles`)
    seen.add(value)
    const result = value.map((item, index) => cloneJson(item, `${path}[${index}]`, seen))
    seen.delete(value)
    return result
  }
  if (typeof value === 'object') {
    if (Object.getPrototypeOf(value) !== Object.prototype) throw new TypeError(`${path} must contain only plain objects and arrays`)
    if (seen.has(value)) throw new TypeError(`${path} must not contain cycles`)
    seen.add(value)
    const result = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneJson(item, `${path}.${key}`, seen)]))
    seen.delete(value)
    return result
  }
  throw new TypeError(`${path} must contain only JSON values`)
}

function freezeDeep(value, seen = new Set()) {
  if (!value || typeof value !== 'object' || seen.has(value)) return value
  seen.add(value)
  for (const child of Object.values(value)) freezeDeep(child, seen)
  return Object.freeze(value)
}

function snapshotEvent(input) {
  const type = requireNonEmptyString(input?.type, 'type')
  const source = requireNonEmptyString(input?.source, 'source')
  const contextId = requireNonEmptyString(input?.contextId, 'contextId')
  const payload = freezeDeep(cloneJson(input?.payload === undefined ? {} : input.payload))
  const event = {
    id: typeof input?.id === 'string' && input.id.trim() ? input.id.trim() : `companion-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    source,
    contextId,
    payload,
    timestamp: new Date().toISOString()
  }
  Object.defineProperty(event, EVENT_MARKER, { value: true })
  return Object.freeze(event)
}

export function createCompanionEvent(input = {}) {
  return snapshotEvent(input)
}

export function immutableSnapshot(value) { return freezeDeep(cloneJson(value)) }

export function createCompanionEventBus() {
  const subscribers = new Map()

  return {
    subscribe(type, handler) {
      type = requireNonEmptyString(type, 'type')
      if (typeof handler !== 'function') throw new TypeError('handler must be a function')
      if (!subscribers.has(type)) subscribers.set(type, new Set())
      subscribers.get(type).add(handler)
      return () => subscribers.get(type)?.delete(handler)
    },

    publish(event) {
      if (!event || event[EVENT_MARKER] !== true) {
        throw new TypeError('event must be created by createCompanionEvent')
      }
      const handlers = subscribers.get(event.type)
      if (handlers) for (const handler of [...handlers]) handler(event)
      return event
    },

    clear() {
      subscribers.clear()
    }
  }
}
