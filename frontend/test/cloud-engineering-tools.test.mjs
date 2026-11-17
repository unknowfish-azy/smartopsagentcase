import test from 'node:test'
import assert from 'node:assert/strict'
import { findOperationTool, operationToolGroups, previewOperationToolCommands } from '../src/views/operations/toolCatalog.js'
import { personalSystemGroups, findPersonalSystemGroup } from '../src/navigation/personalSystemNavigation.js'
import { cloudCoverage } from '../src/views/operations/cloudCoverage.js'

const ids = ['docker-compose-status', 'helm-releases', 'k8s-storage', 'k8s-rbac-check', 'mesh-status', 'terraform-environment', 'harbor-endpoint-check', 'containerd-registry-inspect']
test('coverage links resolve and distinguish planned integrations from runtime health', () => {
  assert.equal(cloudCoverage.length, 12)
  for (const area of cloudCoverage) {
    assert.ok([1, 2, 3].includes(area.priority))
    assert.ok(area.status && area.next && area.knowledge && area.tools)
    if (area.toolId) assert.ok(findOperationTool(area.toolId))
  }
})
test('cloud engineering tools expose safe previews, Chinese guidance and navigable entries', () => {
  /* 2026-11-16：云原生工程 / Harbor 工作台已并入智能仓库 3D 空间，侧栏不再单列，工具目录入口保留 */
  assert.equal(findPersonalSystemGroup('CloudNativeWorkbench'), null, 'folded into the smart repository 3D space')
  for (const id of ids) {
    const tool = findOperationTool(id)
    assert.equal(tool.readOnly, true)
    assert.ok(tool.prerequisite && tool.troubleshooting && tool.evidence.length)
    assert.ok(operationToolGroups.some(group => group.items.some(item => item.id === id)), `${id} remains available through the tools menu`)
    assert.ok(previewOperationToolCommands(tool).length)
    if (tool.parameters.length) assert.throws(() => previewOperationToolCommands(tool, { namespace: 'default;id' }))
  }
})
