import assert from 'node:assert/strict'
import test from 'node:test'

import {
  STAGE_COLORS,
  FALLBACK_COLOR,
  CY,
  START_X,
  END_X,
  TOP_Y,
  BOTTOM_Y,
  ARC_R,
  stageColor,
  buildArcs,
  buildRays,
  radiationHint,
  radiationAriaLabel
} from '../src/domain/research/reWorkbenchRadiation.js'
import { RE_STAGES, RE_TOOLS, RE_TARGETS, pipelineForTarget } from '../src/domain/research/reWorkbenchCatalog.js'

const fakeStage = (id, label) => ({ id, label })

test('radiation: stage colors cover all six real stages, unknown stage falls back', () => {
  assert.equal(Object.keys(STAGE_COLORS).length, 6, 'six semantic stage colors, no seventh')
  for (const stage of RE_STAGES) {
    assert.equal(stageColor(stage.id), STAGE_COLORS[stage.id], `stage ${stage.id} must map to its semantic color`)
  }
  assert.equal(stageColor('no-such-stage'), FALLBACK_COLOR, 'unknown stage must fall back, not undefined')
})

test('radiation: buildArcs divides the ring evenly with gaps and stable offsets', () => {
  const stages = RE_STAGES.map(stage => fakeStage(stage.id, stage.label))
  const arcs = buildArcs(stages)
  assert.equal(arcs.length, RE_STAGES.length)
  const circumference = 2 * Math.PI * ARC_R
  for (const arc of arcs) {
    assert.equal(arc.r, ARC_R)
    assert.equal(stageColor(arc.stage.id), arc.color)
    const [seg, rest] = arc.dash.split(' ').map(Number)
    assert.ok(seg > 0, 'arc segment must be positive')
    assert.ok(Math.abs(seg + rest - circumference) < 1e-6, 'dash + gap must fill exactly one circumference')
  }
  // 段间间隙：相邻弧的 offset 差等于均分步长
  const step = circumference / arcs.length
  for (let i = 1; i < arcs.length; i++) {
    assert.ok(Math.abs((arcs[i].offset - arcs[i - 1].offset) - (-step)) < 1e-6)
  }
})

test('radiation: buildArcs tolerates empty input', () => {
  assert.deepEqual(buildArcs([]), [])
  assert.deepEqual(buildArcs(null), [])
})

test('radiation: buildRays spreads endpoints across full vertical range', () => {
  const rays = buildRays(RE_TOOLS, new Set(), [])
  assert.equal(rays.length, RE_TOOLS.length)
  assert.equal(rays[0].y, TOP_Y, 'first endpoint at top bound')
  assert.equal(rays[rays.length - 1].y, BOTTOM_Y, 'last endpoint at bottom bound')
  for (let i = 1; i < rays.length; i++) {
    assert.ok(rays[i].y > rays[i - 1].y, 'endpoints strictly increasing')
  }
  assert.equal(rays[7].y, (TOP_Y + BOTTOM_Y) / 2, 'middle endpoint centered')
})

test('radiation: ray path is a cubic bezier from ring edge to END_X at endpoint y', () => {
  const rays = buildRays(RE_TOOLS, new Set(), [])
  for (const ray of rays) {
    assert.match(ray.d, new RegExp(`^M ${START_X} ${CY} C 360 ${CY}, 520 ${ray.y}, ${END_X} ${ray.y}$`))
  }
})

test('radiation: single tool is vertically centered', () => {
  const [only] = buildRays([RE_TOOLS[0]], new Set(), [])
  assert.equal(only.y, (TOP_Y + BOTTOM_Y) / 2)
})

test('radiation: activation follows activeIds (Set or Array), silent when empty', () => {
  const rays = buildRays(RE_TOOLS, new Set(), [])
  assert.ok(rays.every(ray => !ray.active), 'no selection = no active rays (no fake busyness)')
  const target = RE_TARGETS[0]
  const pipeline = pipelineForTarget(target)
  const ids = new Set(pipeline.map(tool => tool.id))
  const lit = buildRays(RE_TOOLS, ids, [])
  assert.deepEqual(
    lit.filter(ray => ray.active).map(ray => ray.tool.id),
    pipeline.map(tool => tool.id),
    'exactly the pipeline tools light up'
  )
  // Array 形式同样支持
  const litByArray = buildRays(RE_TOOLS, [...ids], [])
  assert.deepEqual(litByArray.filter(ray => ray.active).map(ray => ray.tool.id), pipeline.map(tool => tool.id))
})

test('radiation: order follows the real pipeline sequence, others keep card order', () => {
  const target = RE_TARGETS.find(item => item.pipeline.length >= 5) || RE_TARGETS[0]
  const pipeline = pipelineForTarget(target)
  const order = pipeline.map(tool => tool.id)
  const rays = buildRays(RE_TOOLS, new Set(order), order)
  const activeRays = rays.filter(ray => ray.active)
  assert.deepEqual(
    activeRays.map(ray => ray.order),
    order.map((_, i) => i),
    'active rays stagger in real pipeline order 0..n-1'
  )
  const inactiveRays = rays.filter(ray => !ray.active)
  assert.ok(inactiveRays.length + activeRays.length === rays.length)
  // 未命中工具的 order 退回卡片序号，保证渲染稳定（不出现 NaN/undefined）
  for (const ray of inactiveRays) {
    assert.equal(ray.order, rays.indexOf(ray), `inactive ray for ${ray.tool.id} falls back to card index`)
  }
})

test('radiation: copy text keeps the no-busy contract in both states', () => {
  assert.match(radiationHint(15, 0, ''), /静默/)
  assert.match(radiationHint(15, 5, '安卓应用'), /5 \/ 15/)
  assert.match(radiationHint(15, 5, '安卓应用'), /安卓应用/)
  assert.match(radiationAriaLabel(15, 0, ''), /尚未选择目标/)
  assert.match(radiationAriaLabel(15, 5, '安卓应用'), /命中 5 个/)
  // 兜底：非法数字不得产出 NaN 文案
  assert.match(radiationHint(undefined, NaN, ''), /静默/)
  assert.match(radiationAriaLabel('x', 'y', ''), /尚未选择目标/)
})
