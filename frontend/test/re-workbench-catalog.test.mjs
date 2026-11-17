import assert from 'node:assert/strict'
import test from 'node:test'

import {
  RE_STAGES,
  RE_TARGETS,
  RE_TOOLS,
  pipelineForTarget,
  toolsByStage
} from '../src/domain/research/reWorkbenchCatalog.js'

test('catalog: exactly 15 tools, unique ids and repos, all fields populated', () => {
  assert.equal(RE_TOOLS.length, 15, 'the curated list claims 15 tools — keep the count honest')
  const ids = new Set()
  const repos = new Set()
  for (const tool of RE_TOOLS) {
    assert.ok(!ids.has(tool.id), `duplicate tool id: ${tool.id}`)
    assert.ok(!repos.has(tool.repo), `duplicate repo: ${tool.repo}`)
    ids.add(tool.id)
    repos.add(tool.repo)
    assert.ok(tool.name && tool.blurb && tool.useWhen, `${tool.id} must have name/blurb/useWhen`)
    assert.match(tool.repo, /^https:\/\/(github|gitlab)\.com\/[\w.-]+\/[\w.-]+$/, `${tool.id} repo must be an official https repo url`)
    assert.ok(RE_STAGES.some(stage => stage.id === tool.stage), `${tool.id} has unknown stage ${tool.stage}`)
  }
})

test('catalog: every stage owns at least one tool, stage ids valid', () => {
  const stageIds = new Set(RE_STAGES.map(stage => stage.id))
  assert.equal(stageIds.size, RE_STAGES.length)
  for (const group of toolsByStage()) {
    assert.ok(stageIds.has(group.stage.id))
    assert.ok(group.tools.length > 0)
  }
  assert.equal(toolsByStage().reduce((sum, group) => sum + group.tools.length, 0), 15)
})

test('catalog: every target pipeline references real tools in stage order', () => {
  const stageOrder = RE_STAGES.map(stage => stage.id)
  for (const target of RE_TARGETS) {
    assert.ok(target.pipeline.length >= 3, `${target.id} pipeline too thin`)
    assert.ok(target.note && target.cn)
    const groups = pipelineForTarget(target.id)
    const flattened = groups.flatMap(group => group.tools.map(tool => tool.id))
    assert.deepEqual(flattened, target.pipeline, `${target.id} pipeline must round-trip without dropping tools`)
    const positions = groups.map(group => stageOrder.indexOf(group.stage))
    assert.deepEqual(positions, [...positions].sort((a, b) => a - b), `${target.id} groups must follow stage order`)
  }
  // 未知目标返回空，不抛错
  assert.deepEqual(pipelineForTarget('no-such-target'), [])
})

test('catalog: no closed-source or request-only tools sneaked in', () => {
  // 全部仓库必须来自开源托管平台上的公开组织/个人（本测试同时锁死"只导览不执行"边界的数据面）
  for (const tool of RE_TOOLS) {
    assert.ok(!tool.repo.includes('azurewebsites') && !tool.repo.includes('download'), tool.id)
  }
})
