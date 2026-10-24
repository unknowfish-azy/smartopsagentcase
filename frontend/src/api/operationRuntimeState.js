const ACTIVE_RUNTIME_KEY = 'smartops.activeOperationRuntime'

function defaultStorage() {
  return typeof window === 'undefined' ? null : window.sessionStorage
}

export function setActiveOperationRuntime(runtime, storage = defaultStorage()) {
  if (!storage || !runtime?.runtimeId) return
  const safeRuntime = {
    runtimeId: String(runtime.runtimeId),
    sessionName: String(runtime.sessionName || ''),
    host: String(runtime.host || '')
  }
  storage.setItem(ACTIVE_RUNTIME_KEY, JSON.stringify(safeRuntime))
}

export function getActiveOperationRuntime(storage = defaultStorage()) {
  if (!storage) return null
  try {
    const runtime = JSON.parse(storage.getItem(ACTIVE_RUNTIME_KEY) || 'null')
    return runtime?.runtimeId ? runtime : null
  } catch {
    storage.removeItem(ACTIVE_RUNTIME_KEY)
    return null
  }
}

export function clearActiveOperationRuntime(storage = defaultStorage()) {
  storage?.removeItem(ACTIVE_RUNTIME_KEY)
}
