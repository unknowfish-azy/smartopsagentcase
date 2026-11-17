// 现场核查工单面板 · 纯函数单测：payload 映射、版本递增、事件追加、失败标注。
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  VERIFY_STATUSES,
  buildVerifyPayload,
  nextVersion,
  appendSessionEvent,
  makeVersionEntry
} from '../src/domain/inspector/fieldVerification.js'

test('VERIFY_STATUSES：固定三档', () => {
  assert.deepEqual([...VERIFY_STATUSES], ['PASS', 'FAIL', 'PENDING'])
})

test('buildVerifyPayload：对齐 InspectionVerifyRequest 契约', () => {
  const payload = buildVerifyPayload({ id: 'INS-1' }, { reading: '4.5', status: 'PASS', note: ' 水面无明显异常 ' })
  assert.equal(payload.inspectionId, 'INS-1')
  assert.equal(payload.resolved, true)
  assert.equal(payload.status, 'PASS')
  assert.equal(payload.details.reading, 4.5)
  assert.equal(payload.details.note, '水面无明显异常')

  const fail = buildVerifyPayload({ id: 'INS-2' }, { reading: '', status: 'FAIL', note: '' })
  assert.equal(fail.resolved, false)
  assert.equal(fail.details.reading, null)
  assert.equal(fail.details.note, '')
})

test('buildVerifyPayload：非法 status 归一为 PENDING；非数值读数归 null', () => {
  const p = buildVerifyPayload({ id: 'X' }, { reading: 'abc', status: 'WHATEVER', note: '' })
  assert.equal(p.status, 'PENDING')
  assert.equal(p.details.reading, null)
})

test('buildVerifyPayload：缺事件 id 给空串（组件层再拦截）', () => {
  const p = buildVerifyPayload(null, { reading: 1, status: 'PASS', note: '' })
  assert.equal(p.inspectionId, '')
})

test('nextVersion：无自带 verification 从 v1 起，有则从 v2 起', () => {
  assert.equal(nextVersion(null, 0), 'v1')
  assert.equal(nextVersion({ status: 'PASS' }, 0), 'v2')
  assert.equal(nextVersion(null, 2), 'v3')
  assert.equal(nextVersion({ status: 'PASS' }, 3), 'v5')
  assert.equal(nextVersion(null, -1), 'v1')
})

test('appendSessionEvent：白名单 kind + 尾插时间升序 + 不改原数组', () => {
  const base = [{ id: 'a', kind: 'submitted', at: '2026-11-16T10:00:00Z', synced: true }]
  const next = appendSessionEvent(base, 'resubmitted', { version: 'v2', synced: false })
  assert.equal(base.length, 1)
  assert.equal(next.length, 2)
  assert.equal(next[1].kind, 'resubmitted')
  assert.equal(next[1].synced, false)
  assert.equal(next[1].version, 'v2')
  assert.ok(next[1].id !== 'a')
  // 非法 kind 原样返回
  assert.deepEqual(appendSessionEvent(base, 'hacked', {}), base)
  // 空数组安全
  assert.equal(appendSessionEvent(null, 'submitted', {}).length, 1)
})

test('makeVersionEntry：synced 标注 + 字段透传', () => {
  const payload = buildVerifyPayload({ id: 'E' }, { reading: '7.5', status: 'FAIL', note: '浊度偏高' })
  const entry = makeVersionEntry('v1', payload, false)
  assert.equal(entry.version, 'v1')
  assert.equal(entry.status, 'FAIL')
  assert.equal(entry.reading, 7.5)
  assert.equal(entry.note, '浊度偏高')
  assert.equal(entry.synced, false)
  assert.ok(entry.at.endsWith('Z') || !Number.isNaN(new Date(entry.at).getTime()))
})
