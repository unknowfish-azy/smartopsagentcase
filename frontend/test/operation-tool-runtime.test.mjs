import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

import {
  clearActiveOperationRuntime,
  getActiveOperationRuntime,
  setActiveOperationRuntime
} from '../src/api/operationRuntimeState.ts'

test('shares only current runtime metadata between connections and tools', () => {
  const storage = new Map()
  const sessionStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key)
  }

  setActiveOperationRuntime({ runtimeId: 'runtime-1', sessionName: 'prod-host', host: '10.0.0.8' }, sessionStorage)
  assert.deepEqual(getActiveOperationRuntime(sessionStorage), {
    runtimeId: 'runtime-1', sessionName: 'prod-host', host: '10.0.0.8'
  })

  clearActiveOperationRuntime(sessionStorage)
  assert.equal(getActiveOperationRuntime(sessionStorage), null)
})

test('tools view executes through the active runtime and renders traceable evidence', async () => {
  const source = await readFile(new URL('../src/views/operations/ToolsView.vue', import.meta.url), 'utf8')

  assert.match(source, /getActiveOperationRuntime/)
  assert.match(source, /executeOperationTool/)
  assert.match(source, /TraceId/)
  assert.match(source, /stdout/)
  assert.match(source, /stderr/)
  assert.match(source, /exitCode/)
})
