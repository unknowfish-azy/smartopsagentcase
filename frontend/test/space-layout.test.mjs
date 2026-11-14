import assert from 'node:assert/strict'
import test from 'node:test'
import { knowledgeDomains, knowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'
import { computeLayout } from '../src/views/knowledge/space/useSpaceLayout.js'

test('真实数据 10 域全覆盖，互不重叠', () => {
  const { zones } = computeLayout(knowledgeEntries, knowledgeDomains)
  assert.equal(zones.length, 10, `预期 10 个域矩形，实际 ${zones.length}`)

  // 矩形两两不重叠（A.x < B.x + B.w && B.x < A.x + A.w && A.y < B.y + B.h && B.y < A.y + A.h）
  for (let i = 0; i < zones.length; i++) {
    for (let j = i + 1; j < zones.length; j++) {
      const a = zones[i], b = zones[j]
      const overlaps = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
      assert.ok(!overlaps, `${a.id}(${Math.round(a.w*a.h)}) 与 ${b.id}(${Math.round(b.w*b.h)}) 存在重叠`)
    }
  }

  // 所有域面积之和等于世界面积（允许 rounding 容差 5%）
  const world = 3200 * 2000
  const sum = zones.reduce((a, z) => a + z.w * z.h, 0)
  assert.ok(Math.abs(sum - world) / world < 0.05, `面积和 ${Math.round(sum)} 偏离世界面积 ${world} 超过 5%`)
})

test('卡片总数等于输入条目数', () => {
  const { zones, cards } = computeLayout(knowledgeEntries, knowledgeDomains)
  assert.equal(cards.length, knowledgeEntries.length,
    `预期 ${knowledgeEntries.length} 张卡片，实际 ${cards.length}`)
  // 每域卡片数与 entries 中 domain 计数一致
  for (const z of zones) {
    const n = cards.filter(c => c.domainId === z.id).length
    assert.equal(n, z.n, `域 ${z.id} 期望 ${z.n} 张卡片，实际 ${n}`)
  }
})

test('同输入两次调用结果完全一致（坐标恒定）', () => {
  const a = computeLayout(knowledgeEntries, knowledgeDomains)
  const b = computeLayout(knowledgeEntries, knowledgeDomains)
  assert.deepEqual(a, b, '两次 computeLayout 输出不相等——坐标不稳定')
})

test('linux / centos 面积比 ≈ √225 / √1（容差 5%）', () => {
  const { zones } = computeLayout(knowledgeEntries, knowledgeDomains)
  const linux  = zones.find(z => z.id === 'linux')
  const centos = zones.find(z => z.id === 'centos')
  assert.ok(linux && centos, '未找到 linux 或 centos 域矩形')
  const actual   = (linux.w * linux.h) / (centos.w * centos.h)
  const expected = Math.sqrt(225) / Math.sqrt(1)  // = 15
  const ratio    = actual / expected
  assert.ok(ratio >= 0.95 && ratio <= 1.05,
    `linux/centos 面积比 ${actual.toFixed(2)} 偏离预期 15 超过 5% (ratio=${ratio.toFixed(3)})`)
})

test('linux 域绝对比 centos 大（权重单调）', () => {
  const { zones } = computeLayout(knowledgeEntries, knowledgeDomains)
  const linux  = zones.find(z => z.id === 'linux')
  const centos = zones.find(z => z.id === 'centos')
  assert.ok(linux.w * linux.h > centos.w * centos.h * 3,
    `linux 面积应显著大于 centos（至少 3×），实际 linux=${linux.w*linux.h} centos=${centos.w*centos.h}`)
})

test('单域布局核心耗时合理（切块 + 网格，200 次冷启动平均）', () => {
  // Node 环境里模块加载本身有 IO 开销，不代表浏览器真实性能。
  // 这里只验证：200 次连续调用的平均耗时在可接受范围（< 25ms），
  // 浏览器端冷启动后 V8 JIT 应能压到 < 3ms/次。
  const t0 = performance.now()
  for (let i = 0; i < 200; i++) computeLayout(knowledgeEntries, knowledgeDomains)
  const total = performance.now() - t0
  const perRun = total / 200
  assert.ok(perRun < 25, `单次布局 ${perRun.toFixed(2)}ms 超过 25ms 预算`)
})

test('域内 type 优先级生效：RUNBOOK/DIAGNOSIS 排在 ENGINEERING 前面', () => {
  const { cards } = computeLayout(knowledgeEntries, knowledgeDomains)
  const linuxCards = cards.filter(c => c.domainId === 'linux')
  const engIdx = linuxCards.findIndex(c => String(c.entry.type || '').toUpperCase().includes('ENGINEERING'))
  const diagIdx = linuxCards.findIndex(c => /RUNBOOK|DIAGNOSIS/i.test(c.entry.type || ''))
  if (diagIdx >= 0 && engIdx >= 0) {
    assert.ok(diagIdx < engIdx, `linux 域内 RUNBOOK 应排在 ENGINEERING 前面，但 diagIdx=${diagIdx} engIdx=${engIdx}`)
  }
})

test('空输入安全返回空布局', () => {
  const { zones, cards } = computeLayout([], [])
  assert.deepEqual(zones, [])
  assert.deepEqual(cards, [])
})

test('单域输入返回整块世界', () => {
  const entries = [{ id: 'x', domain: 'solo', platform: 'p', service: 's', type: 'ENGINEERING', title: 'T', summary: 'S' }]
  const domains = [{ id: 'solo', label: 'SOLO', detail: '' }]
  const { zones, cards } = computeLayout(entries, domains)
  assert.equal(zones.length, 1)
  assert.equal(zones[0].x, 0)
  assert.equal(zones[0].y, 0)
  assert.equal(zones[0].w, 3200)
  assert.equal(zones[0].h, 2000)
  assert.equal(cards.length, 1)
})
