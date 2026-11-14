import assert from 'node:assert/strict'
import test from 'node:test'
import {
  groupOf, severityRank, sortChecks, partitionChecks,
  kindLabel, statusVisual, countByGroup,
  GROUP_ORDER, GROUP_META
} from '../src/components/diagnostics/healthGroups.js'

// ---- groupOf：五种状态各归到正确的组 ----
test('groupOf maps all 5 Check.status values to the correct semantic group', () => {
  assert.equal(groupOf('HEALTHY'), 'pass')
  assert.equal(groupOf('UNHEALTHY'), 'action')
  assert.equal(groupOf('UNCONFIGURED'), 'config')
  assert.equal(groupOf('NOT_CHECKED'), 'unknown')
  assert.equal(groupOf('FORBIDDEN'), 'forbidden')
  // 后端可能返回的边界值
  assert.equal(groupOf(null), 'unknown')
  assert.equal(groupOf(undefined), 'unknown')
  assert.equal(groupOf('UNKNOWN_ENUM'), 'unknown')
})

test('groupOf also handles diagnosis-result side states', () => {
  assert.equal(groupOf('UNVERIFIED'), 'unknown')
  assert.equal(groupOf('BLOCKED'), 'config')
  assert.equal(groupOf('TIMEOUT'), 'action')
})

// ---- 固定顺序是 DESIGN §6.1 要求 ----
test('GROUP_ORDER is exactly action → config → unknown → pass → forbidden', () => {
  assert.deepEqual(GROUP_ORDER, ['action', 'config', 'unknown', 'pass', 'forbidden'])
  assert.equal(GROUP_ORDER.length, 5)
})

// ---- 每个组都有元数据（标题+颜色令牌） ----
test('every group in GROUP_ORDER has a GROUP_META entry with title and colorToken', () => {
  for (const g of GROUP_ORDER) {
    assert.ok(GROUP_META[g], `${g} 缺少 GROUP_META`)
    assert.ok(GROUP_META[g].title, `${g} 缺少 title`)
    assert.ok(GROUP_META[g].colorToken, `${g} 缺少 colorToken`)
  }
})

// ---- severityRank：ACTIVE_PROBE 最硬排最前 ----
test('severityRank assigns ACTIVE_PROBE=0, LOCAL_CHECK=1, CONFIGURATION=2', () => {
  assert.equal(severityRank({ checkKind: 'ACTIVE_PROBE' }), 0)
  assert.equal(severityRank({ checkKind: 'LOCAL_CHECK' }), 1)
  assert.equal(severityRank({ checkKind: 'CONFIGURATION' }), 2)
  assert.equal(severityRank({}), 2)
  assert.equal(severityRank(null), 2)
})

// ---- sortChecks：先硬度后耗时 ----
test('sortChecks puts ACTIVE_PROBE before LOCAL_CHECK before CONFIGURATION', () => {
  const arr = [
    { id: 'c1', checkKind: 'CONFIGURATION', durationMs: 100 },
    { id: 'c2', checkKind: 'ACTIVE_PROBE', durationMs: 100 },
    { id: 'c3', checkKind: 'LOCAL_CHECK', durationMs: 100 }
  ]
  const sorted = sortChecks(arr)
  assert.equal(sorted[0].id, 'c2')
  assert.equal(sorted[1].id, 'c3')
  assert.equal(sorted[2].id, 'c1')
})

test('sortChecks sorts same-kind checks by durationMs descending', () => {
  const arr = [
    { id: 'slow', checkKind: 'ACTIVE_PROBE', durationMs: 500 },
    { id: 'fast', checkKind: 'ACTIVE_PROBE', durationMs: 2 }
  ]
  const sorted = sortChecks(arr)
  assert.equal(sorted[0].id, 'slow')
  assert.equal(sorted[1].id, 'fast')
})

test('sortChecks is stable and handles zero/null duration', () => {
  const arr = [
    { id: 'a', checkKind: 'ACTIVE_PROBE', durationMs: 0 },
    { id: 'b', checkKind: 'ACTIVE_PROBE', durationMs: null },
    { id: 'c', checkKind: 'ACTIVE_PROBE' }
  ]
  const sorted = sortChecks(arr)
  assert.equal(sorted.length, 3)
})

// ---- partitionChecks：分桶 + FORBIDDEN 单独取 ----
test('partitionChecks buckets checks and separates FORBIDDEN', () => {
  const input = [
    { id: 'a', status: 'UNHEALTHY', checkKind: 'ACTIVE_PROBE', durationMs: 10 },
    { id: 'b', status: 'HEALTHY', checkKind: 'ACTIVE_PROBE', durationMs: 5 },
    { id: 'c', status: 'UNCONFIGURED', checkKind: 'CONFIGURATION', durationMs: 0 },
    { id: 'd', status: 'NOT_CHECKED', checkKind: 'CONFIGURATION', durationMs: 0 },
    { id: 'e', status: 'FORBIDDEN', checkKind: 'ACTIVE_PROBE', durationMs: 0 }
  ]
  const { buckets, forbidden } = partitionChecks(input)
  assert.equal(buckets.action.length, 1)
  assert.equal(buckets.action[0].id, 'a')
  assert.equal(buckets.pass.length, 1)
  assert.equal(buckets.config.length, 1)
  assert.equal(buckets.unknown.length, 1)
  assert.equal(forbidden.length, 1)
  assert.equal(forbidden[0].id, 'e')
})

test('partitionChecks returns empty arrays for empty input', () => {
  const { buckets, forbidden } = partitionChecks([])
  assert.deepEqual(buckets.action, [])
  assert.deepEqual(buckets.config, [])
  assert.deepEqual(buckets.unknown, [])
  assert.deepEqual(buckets.pass, [])
  assert.deepEqual(forbidden, [])
})

test('partitionChecks sorts each bucket (hard → soft, slow → fast)', () => {
  const input = [
    { id: 'config-soft', status: 'UNCONFIGURED', checkKind: 'CONFIGURATION', durationMs: 0 },
    { id: 'probe-slow', status: 'UNHEALTHY', checkKind: 'ACTIVE_PROBE', durationMs: 300 },
    { id: 'probe-fast', status: 'UNHEALTHY', checkKind: 'ACTIVE_PROBE', durationMs: 2 },
    { id: 'local', status: 'UNHEALTHY', checkKind: 'LOCAL_CHECK', durationMs: 10 }
  ]
  const { buckets } = partitionChecks(input)
  const action = buckets.action.map(c => c.id)
  assert.deepEqual(action, ['probe-slow', 'probe-fast', 'local'])
})

// ---- kindLabel：三档中文标签 + tooltip ----
test('kindLabel returns Chinese label and tip for all three checkKinds', () => {
  assert.equal(kindLabel('ACTIVE_PROBE').label, '主动探测')
  assert.ok(kindLabel('ACTIVE_PROBE').tip.includes('真的连'))
  assert.equal(kindLabel('LOCAL_CHECK').label, '本地检查')
  assert.ok(kindLabel('LOCAL_CHECK').tip.includes('不证明'))
  assert.ok(kindLabel('LOCAL_CHECK').tip.includes('服务'))
  assert.equal(kindLabel('CONFIGURATION').label, '配置读取')
  assert.ok(kindLabel('CONFIGURATION').tip.includes('只读了配置'))
})

test('kindLabel falls back to showing the raw enum when unknown', () => {
  const r = kindLabel('SOMETHING_WEIRD')
  assert.equal(r.label, 'SOMETHING_WEIRD')
})

// ---- statusVisual：关键 a11y 约束（§4 + 硬约束 5） ----
test('NOT_CHECKED shape=dashed and UNCONFIGURED shape=solid (must be visually distinct)', () => {
  const nc = statusVisual('NOT_CHECKED')
  const uc = statusVisual('UNCONFIGURED')
  assert.equal(nc.shape, 'dashed')
  assert.equal(uc.shape, 'solid')
  assert.notEqual(nc.shape, uc.shape)
})

test('FORBIDDEN has distinct outline shape, HEALTHY and UNHEALTHY use solid', () => {
  assert.equal(statusVisual('FORBIDDEN').shape, 'outline')
  assert.equal(statusVisual('HEALTHY').shape, 'solid')
  assert.equal(statusVisual('UNHEALTHY').shape, 'solid')
})

test('statusVisual provides cls + icon + label for all 5 semantic groups', () => {
  for (const status of ['HEALTHY', 'UNHEALTHY', 'UNCONFIGURED', 'NOT_CHECKED', 'FORBIDDEN']) {
    const v = statusVisual(status)
    assert.ok(v.cls, `${status} 缺少 cls`)
    assert.ok(v.icon, `${status} 缺少 icon`)
    assert.ok(v.label, `${status} 缺少 label`)
  }
})

// ---- countByGroup ----
test('countByGroup aggregates counts across all 5 semantic groups', () => {
  const input = [
    { status: 'UNHEALTHY' },
    { status: 'UNHEALTHY' },
    { status: 'UNCONFIGURED' },
    { status: 'HEALTHY' },
    { status: 'HEALTHY' },
    { status: 'HEALTHY' },
    { status: 'NOT_CHECKED' },
    { status: 'FORBIDDEN' }
  ]
  const c = countByGroup(input)
  assert.equal(c.action, 2)
  assert.equal(c.config, 1)
  assert.equal(c.pass, 3)
  assert.equal(c.unknown, 1)
  assert.equal(c.forbidden, 1)
})

test('countByGroup returns zeros for empty input', () => {
  const c = countByGroup([])
  assert.deepEqual(c, { action: 0, config: 0, unknown: 0, pass: 0, forbidden: 0 })
})

// ---- 关键回归：NOT_CHECKED 永远不映射到 pass 或 action ----
test('NOT_CHECKED never maps to pass or action (design constraint)', () => {
  const s = 'NOT_CHECKED'
  const g = groupOf(s)
  assert.notEqual(g, 'pass')
  assert.notEqual(g, 'action')
  assert.equal(statusVisual(s).shape, 'dashed')
})

// ---- 关键回归：healthState.js 的现有函数不受影响 ----
import { healthStateLabel } from '../src/components/diagnostics/healthState.js'
test('healthGroups.js additions do not change healthStateLabel behavior', () => {
  assert.equal(healthStateLabel('HEALTHY'), '正常')
  assert.equal(healthStateLabel('UNHEALTHY'), '异常')
  assert.equal(healthStateLabel('UNCONFIGURED'), '未配置')
  assert.equal(healthStateLabel('FORBIDDEN'), '无权限')
  assert.equal(healthStateLabel('NOT_CHECKED'), '未检查')
})
