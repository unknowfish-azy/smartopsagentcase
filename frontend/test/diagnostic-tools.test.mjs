import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { findOperationTool } from '../src/views/operations/toolCatalog.js'

const root = new URL('../', import.meta.url)
const source = path => readFile(new URL(path, root), 'utf8')

test('service diagnostic tools are read-only and use controlled execution types', () => {
  for (const id of ['service-http-check', 'service-certificate-check', 'config-diff']) {
    const tool = findOperationTool(id)
    assert.ok(tool)
    assert.equal(tool.readOnly, true)
    assert.equal(tool.requireConfirm, false)
    assert.ok(['service-probe', 'local-browser'].includes(tool.executionType))
  }
})

test('diagnostic pages use target IDs and local config diff without arbitrary URL input', async () => {
  const network = await source('src/components/diagnostics/NetworkDiagnosticTool.vue')
  const diff = await source('src/components/diagnostics/ConfigDiffTool.vue')
  const api = await source('src/api/diagnostics.ts')
  assert.match(network, /targetId/)
  assert.equal(network.includes('type="url"'), false)
  assert.match(api, /\/api\/diagnostics\/http/)
  assert.match(api, /\/api\/diagnostics\/certificate/)
  assert.equal(diff.includes('localStorage'), false)
  assert.equal(diff.includes('request.'), false)
})

test('health center and route stay lazy', async () => {
  const router = await source('src/router/index.js')
  const view = await source('src/views/diagnostics/HealthCenterView.vue')
  assert.match(router, /path: 'health'/)
  assert.match(router, /import\('\.\.\/views\/diagnostics\/HealthCenterView\.vue'\)/)
  assert.match(view, /HealthCheckList/)
})

test('admin readiness renders a safe manual policy summary without sensitive fields', async () => {
  const readiness = await source('src/views/admin/AdminReadinessView.vue')
  const health = await source('src/components/diagnostics/HealthCheckList.vue')
  const docs = await source('../docs/operations/health-and-diagnostic-tools.md')
  assert.match(readiness, /策略边界/)
  assert.match(readiness, /手动、只读、受白名单控制/)
  assert.match(readiness, /policy/)
  assert.doesNotMatch(readiness, /token|password|Authorization|Cookie|hostname|pinnedAddresses/i)
  assert.doesNotMatch(health, /token|password|Authorization|Cookie|hostname|pinnedAddresses/i)
  assert.match(docs, /五分钟/)
})
