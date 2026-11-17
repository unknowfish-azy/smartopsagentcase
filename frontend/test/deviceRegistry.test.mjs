// 设备接入台账纯统计内核测试：钉死"以真实字段判定"的口径，
// 防止任何"缺失字段当作在线/启用"的侥幸逻辑混进来。

import assert from 'node:assert/strict'
import test from 'node:test'

import { summarizeLedger } from '../src/utils/deviceRegistry.js'

test('counts server totals and online strictly by the real status field', () => {
  const servers = [
    { name: 'web-1', status: 'ONLINE' },
    { name: 'web-2', status: 'WARNING' },
    { name: 'db-1', status: 'OFFLINE' },
    { name: 'cache-1', status: 'UNKNOWN' },
    { name: 'no-status' }
  ]
  const summary = summarizeLedger(servers, [])
  assert.equal(summary.serverTotal, 5)
  assert.equal(summary.serverOnline, 1, '只有 status=ONLINE 计在线')
})

test('lowercase online is still a real status value and counts as online', () => {
  const summary = summarizeLedger([{ status: 'online' }, { status: 'Online' }], [])
  assert.equal(summary.serverTotal, 2)
  assert.equal(summary.serverOnline, 1, '仅全小写 online 视为在线，混合大小写不算')
})

test('counts connection totals and enabled strictly by boolean true', () => {
  const connections = [
    { name: 'a', enabled: true },
    { name: 'b', enabled: false },
    { name: 'c' },
    { name: 'd', enabled: 1 },
    { name: 'e', enabled: 'true' }
  ]
  const summary = summarizeLedger([], connections)
  assert.equal(summary.connectionTotal, 5)
  assert.equal(summary.connectionEnabled, 1, '仅 enabled === true 计启用，truthy 值不算')
})

test('both sources aggregate independently in one call', () => {
  const summary = summarizeLedger(
    [{ status: 'ONLINE' }, { status: 'ONLINE' }, { status: 'OFFLINE' }],
    [{ enabled: true }, { enabled: true }, { enabled: false }, { enabled: true }]
  )
  assert.deepEqual(summary, {
    serverTotal: 3,
    serverOnline: 2,
    connectionTotal: 4,
    connectionEnabled: 3
  })
})

test('non-array or missing inputs degrade to zeros instead of throwing', () => {
  assert.deepEqual(summarizeLedger(null, null), {
    serverTotal: 0,
    serverOnline: 0,
    connectionTotal: 0,
    connectionEnabled: 0
  })
  assert.deepEqual(summarizeLedger(undefined, {}), {
    serverTotal: 0,
    serverOnline: 0,
    connectionTotal: 0,
    connectionEnabled: 0
  })
  assert.deepEqual(summarizeLedger('nope', 42), {
    serverTotal: 0,
    serverOnline: 0,
    connectionTotal: 0,
    connectionEnabled: 0
  })
})

test('null or primitive entries inside arrays never crash the tally', () => {
  const summary = summarizeLedger([null, 'x', { status: 'ONLINE' }], [null, { enabled: true }])
  assert.deepEqual(summary, {
    serverTotal: 3,
    serverOnline: 1,
    connectionTotal: 2,
    connectionEnabled: 1
  })
})
