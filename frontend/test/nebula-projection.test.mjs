/**
 * 星云投影纯函数单测（T32a）
 * 覆盖：抽样正确、四环带纬度互斥、经度随时间单调、投影往返、深度排序稳定。
 */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  NEBULA_CAP, PHI_BANDS,
  buildNebula, project, flatPosition, easeOutCubic, dimensionColorOf
} from '../src/components/inspector/desk/nebulaProjection.js'

const RANGE = { start: 0, end: 24 * 3600 * 1000 }

function makeEvents(n, severities = ['PASS', 'WARN', 'HIGH', 'CRITICAL']) {
  return Array.from({ length: n }, (_, i) => ({
    id: `E${String(i).padStart(5, '0')}`,
    at: RANGE.start + ((i + 0.5) / n) * (RANGE.end - RANGE.start),
    severity: severities[i % severities.length],
    taskId: `T${i}`,
    category: i % 2 === 0 ? 'DATABASE' : 'SECURITY'
  }))
}

test('buildNebula：窗口内全量映射，未超上限不抽样', () => {
  const events = makeEvents(120)
  const { particles, sampled, total } = buildNebula(events, RANGE)
  assert.equal(particles.length, 120)
  assert.equal(sampled, false)
  assert.equal(total, 120)
})

test('buildNebula：超 1000 条按上限均匀抽样并如实标注', () => {
  const events = makeEvents(NEBULA_CAP + 500)
  const { particles, sampled, total, cap } = buildNebula(events, RANGE)
  assert.equal(particles.length, NEBULA_CAP)
  assert.equal(sampled, true)
  assert.equal(total, NEBULA_CAP + 500)
  assert.equal(cap, NEBULA_CAP)
  // 首尾事件必须保留（等步长抽样边界）
  assert.equal(particles[0].id, 'E00000')
  assert.equal(particles.at(-1).id, `E${String(NEBULA_CAP + 499).padStart(5, '0')}`)
})

test('四环带纬度互斥：每个等级的 phi 全部落在自己的环带区间内', () => {
  const events = makeEvents(400)
  const { particles } = buildNebula(events, RANGE)
  const ranges = Object.entries(PHI_BANDS).map(([key, center]) => [key, center - 0.12, center + 0.12])
  for (const p of particles) {
    const range = ranges.find(([key]) => key === p.severity)
    assert.ok(range, `未知等级 ${p.severity}`)
    assert.ok(p.phi >= range[1] && p.phi <= range[2], `${p.severity} phi=${p.phi} 越界`)
  }
  // 区间两两不相交
  const sorted = ranges.map(([, lo, hi]) => [lo, hi]).sort((a, b) => a[0] - b[0])
  for (let i = 1; i < sorted.length; i += 1) {
    assert.ok(sorted[i][0] > sorted[i - 1][1], `环带区间相交：${sorted[i - 1]} vs ${sorted[i]}`)
  }
})

test('经度随时间单调：同一构建内 at 更晚的粒子 theta 不小于更早的', () => {
  const events = makeEvents(300)
  const { particles } = buildNebula(events, RANGE)
  for (let i = 1; i < particles.length; i += 1) {
    assert.ok(particles[i].theta >= particles[i - 1].theta, `theta 在 i=${i} 处回退`)
  }
  assert.ok(particles[0].theta >= 0 && particles[0].theta < Math.PI * 2 / particles.length)
  assert.ok(particles.at(-1).theta > Math.PI * 2 - Math.PI * 2 / particles.length)
})

test('窗口外事件不进入星云', () => {
  const events = [...makeEvents(10), { id: 'OUT', at: RANGE.end + 1, severity: 'PASS' }]
  const { particles, total } = buildNebula(events, RANGE)
  assert.equal(total, 10)
  assert.ok(particles.every(p => p.id !== 'OUT'))
})

test('project 往返：theta=0/phi=0 无旋转时粒子落在圆心正右方', () => {
  const particle = { id: 'A', theta: 0, phi: 0, severity: 'PASS', size: 2, age: 0 }
  const width = 800
  const height = 400
  const [proj] = project([particle], 0, 0, width, height, 100)
  assert.ok(Math.abs(proj.x - (width / 2 + 100)) < 1e-9, `x=${proj.x}`)
  assert.ok(Math.abs(proj.y - height / 2) < 1e-9, `y=${proj.y}`)
  assert.ok(Math.abs(proj.scale - 2.4 / 2.4) < 1e-9)
})

test('project 旋转：整圈自转回到原位，越靠近相机 scale 越大', () => {
  const particle = { id: 'A', theta: 1.1, phi: 0.6, severity: 'HIGH', size: 2, age: 0.3 }
  const [p0] = project([particle], 0, 0, 800, 400, 100)
  const [p1] = project([particle], Math.PI * 2, 0, 800, 400, 100)
  assert.ok(Math.abs(p0.x - p1.x) < 1e-9 && Math.abs(p0.y - p1.y) < 1e-9, '整圈自转未回到原位')
  assert.ok(Math.abs(p0.z - p1.z) < 1e-9)
  const near = { id: 'N', theta: Math.PI / 2, phi: 0 }
  const far = { id: 'F', theta: -Math.PI / 2, phi: 0 }
  const [f] = project([near], 0, 0, 800, 400, 100)
  const [b] = project([far], 0, 0, 800, 400, 100)
  assert.ok(f.scale > b.scale, '近处粒子透视放大应大于远处')
})

test('深度排序稳定：z 相同保持原顺序（画家算法远→近）', () => {
  const a = { id: 'A', theta: 0, phi: 0 }
  const b = { id: 'B', theta: Math.PI, phi: 0 }
  const out = project([a, b], 0, 0, 800, 400, 100)
  assert.equal(out.length, 2)
  assert.ok(out[0].z <= out[1].z)
  if (out[0].z === out[1].z) assert.equal(out[0].p.id, 'A')
})

test('flatPosition 与 project 同宽高：平面出发点在画布内', () => {
  const events = makeEvents(50)
  const { particles } = buildNebula(events, RANGE)
  for (const p of particles) {
    const { x, y } = flatPosition(p, 800, 420)
    assert.ok(x >= 0 && x <= 800, `x=${x} 越界`)
    assert.ok(y >= 0 && y <= 420, `y=${y} 越界`)
  }
})

test('easeOutCubic 边界与单调', () => {
  assert.equal(easeOutCubic(0), 0)
  assert.equal(easeOutCubic(1), 1)
  assert.ok(easeOutCubic(0.5) > 0.5)
  assert.ok(easeOutCubic(-1) === 0 && easeOutCubic(2) === 1)
})

test('dimensionColorOf：命中八色带，未命中回退等级色', () => {
  assert.equal(dimensionColorOf('security', '#111'), '#f85149')
  assert.equal(dimensionColorOf('knowledge', '#111'), '#a383a6')
  assert.equal(dimensionColorOf('nonexistent', '#111'), '#111')
  assert.equal(dimensionColorOf('', '#222'), '#222')
})
