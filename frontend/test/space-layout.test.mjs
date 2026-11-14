import assert from 'node:assert/strict'
import test from 'node:test'
import { knowledgeDomains, knowledgeEntries } from '../src/views/knowledge/knowledgeCatalog.js'
import { computeLayout, screenTier, GRID_DEFAULT } from '../src/views/knowledge/space/useSpaceLayout.js'

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

test('卡片内容分档按屏幕像素判定，不看世界像素', () => {
  const card = { w: 200, h: 124 }
  // 同一张卡，缩放不同 → 档位不同
  assert.equal(screenTier(card, 0.42), 'title', 'L1 起点 84×52 只够 2 行标题')
  assert.equal(screenTier(card, 0.65), 'full', '130×81 刚过 full 下限')
  assert.equal(screenTier(card, 2.2), 'full')
  assert.equal(screenTier(card, 0.22), 'title', '44×27 正好落在 micro 边界之上')
  assert.equal(screenTier(card, 0.2), 'micro', '40×25 宽不足 44')
})

test('分档两个门槛都生效：宽够但高不够仍是 title', () => {
  assert.equal(screenTier({ w: 200, h: 100 }, 0.65), 'title', '130×65 高不足 80')
  assert.equal(screenTier({ w: 50, h: 124 }, 2.2), 'title', '110×273 高很够但宽不足 124')
})

test('域内卡片尺寸一致，且不越出所属域块', () => {
  const { zones, cards } = computeLayout(knowledgeEntries, knowledgeDomains)
  for (const z of zones) {
    const own = cards.filter(c => c.zoneId === z.id)
    for (const c of own) {
      assert.equal(c.w, z.cw, `${z.id} 卡片宽度与域网格不一致`)
      assert.equal(c.h, z.ch, `${z.id} 卡片高度与域网格不一致`)
      assert.ok(c.col < z.cols && c.row < z.rows, `${c.id} 的 col/row 超出网格 ${z.cols}×${z.rows}`)
      assert.ok(c.x >= z.x && c.x + c.w <= z.x + z.w + 0.001, `${c.id} 水平越出 ${z.id}`)
      assert.ok(c.y >= z.y && c.y + c.h <= z.y + z.h + 0.001, `${c.id} 垂直越出 ${z.id}`)
    }
  }
})

test('列数取「宽高比 + 空格率」评分的最小值（REVIEW ③）', () => {
  const { zones, cards } = computeLayout(knowledgeEntries, knowledgeDomains)
  const { gap, headH, pad, maxCols } = GRID_DEFAULT
  for (const z of zones) {
    const n = cards.filter(c => c.zoneId === z.id).length
    if (!n) continue
    const innerW = z.w - pad * 2
    const innerH = z.h - headH - pad * 2
    const scoreOf = cols => {
      const rows = Math.ceil(n / cols)
      const cw = (innerW - gap * (cols - 1)) / cols
      const ch = (innerH - gap * (rows - 1)) / rows
      if (cw < 8 || ch < 8) return Infinity
      return Math.abs(cw / ch - 1.5) + Math.abs((cols * rows - n) / n) * 1.5
    }
    let bestCols = 1, bestScore = Infinity
    for (let cols = 1; cols <= maxCols; cols++) {
      const s = scoreOf(cols)
      if (s < bestScore) { bestScore = s; bestCols = cols }
    }
    assert.equal(z.cols, bestCols, `${z.id}（n=${n}）：期望 ${bestCols} 列，实际 ${z.cols}`)
  }
})
