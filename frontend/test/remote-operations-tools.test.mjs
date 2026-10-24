import assert from 'node:assert/strict'
import test from 'node:test'

import {
  findOperationTool,
  operationToolGroups,
  previewOperationToolCommands
} from '../src/views/operations/toolCatalog.js'

test('provides dedicated Kubernetes, Docker and remote host tool groups', () => {
  assert.ok(operationToolGroups.some(group => group.id === 'kubernetes'))
  assert.ok(operationToolGroups.some(group => group.id === 'docker'))
  assert.ok(operationToolGroups.some(group => group.id === 'remote-observability'))

  for (const id of ['k8s-resources', 'k8s-logs', 'docker-containers', 'docker-images', 'host-health', 'http-probe', 'system-logs']) {
    assert.ok(findOperationTool(id), id)
  }
})

test('marks discovery tools as read-only and renders parameterized command previews', () => {
  const tool = findOperationTool('k8s-resources')
  assert.equal(tool.readOnly, true)
  assert.equal(tool.riskLevel, 'LOW')
  assert.equal(tool.requireConfirm, false)

  assert.deepEqual(previewOperationToolCommands(tool, {
    namespace: 'production',
    resource: 'pod',
    name: 'api-0'
  }), [
    'kubectl get pod api-0 -n production -o wide',
    'kubectl describe pod api-0 -n production'
  ])
})

test('rejects unsafe tool parameters instead of interpolating shell input', () => {
  const tool = findOperationTool('docker-logs')

  assert.throws(
    () => previewOperationToolCommands(tool, { container: 'api; rm -rf /', tail: '200' }),
    /参数 container 不符合安全规则/
  )
})

test('requires confirmation for mutating tool definitions', () => {
  const restart = findOperationTool('service-restart')

  assert.equal(restart.readOnly, false)
  assert.equal(restart.riskLevel, 'HIGH')
  assert.equal(restart.requireConfirm, true)
  assert.ok(restart.rollback)
})

test('provides agent operations tools from the requested domains', () => {
  for (const id of [
    'log-search', 'network-diagnostics', 'alerts-query', 'alerts-suppress',
    'knowledge-retrieval', 'database-readonly'
  ]) assert.ok(findOperationTool(id), id)

  for (const id of ['log-search', 'network-diagnostics', 'alerts-query', 'knowledge-retrieval', 'database-readonly']) {
    const tool = findOperationTool(id)
    assert.equal(tool.readOnly, true, id)
    assert.equal(tool.requireConfirm, false, id)
  }
  const suppress = findOperationTool('alerts-suppress')
  assert.equal(suppress.readOnly, false)
  assert.equal(suppress.requireConfirm, true)
  assert.equal(suppress.riskLevel, 'HIGH')
})

test('keeps new tool previews parameterized and rejects shell injection', () => {
  assert.deepEqual(previewOperationToolCommands(findOperationTool('network-diagnostics'), {
    host: 'api.example.com', port: '443'
  }), ['ping -c 3 api.example.com', 'nc -vz -w 5 api.example.com 443', 'dig api.example.com'])
  assert.throws(() => previewOperationToolCommands(findOperationTool('log-search'), {
    service: 'api; rm -rf /', keyword: 'error', lines: '50'
  }), /service/)
})

test('provides cloud native observability and database diagnostic tools', () => {
  for (const id of ['prometheus-query', 'grafana-dashboard', 'loki-log-query', 'mysql-slow-query', 'k8s-diagnose']) {
    const tool = findOperationTool(id)
    assert.ok(tool, id)
    assert.equal(tool.readOnly, true, id)
    assert.equal(tool.requireConfirm, false, id)
  }
  assert.deepEqual(previewOperationToolCommands(findOperationTool('mysql-slow-query'), {
    database: 'orders', limit: '20'
  }), ['smartops db slow-queries --database orders --limit 20 --read-only'])
})
