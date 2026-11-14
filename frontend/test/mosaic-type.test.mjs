import assert from 'node:assert/strict'
import test from 'node:test'

import { searchKnowledgeEntries, knowledgeDomains } from '../src/views/knowledge/knowledgeCatalog.js'
import {
  normalizeKnowledgeType, normalizeRisk, isPlaceholderVersion,
  TYPE_CLASSES, TYPE_CLASS_COLORS,
} from '../src/views/knowledge/space/mosaic/mosaicType.js'

const all = searchKnowledgeEntries({})

test('57 种 type 全部归入 7 个上位类，无 undefined，原始值不丢', () => {
  const distinct = [...new Set(all.map(e => String(e.type ?? '')))]
  assert.ok(distinct.length >= 40, `type 取值种类偏少：${distinct.length}`)
  for (const raw of distinct) {
    const r = normalizeKnowledgeType(raw)
    assert.ok(TYPE_CLASSES.includes(r.cls), `type "${raw}" 归类为 ${r.cls}，不在 7 类内`)
    assert.equal(typeof r.short, 'string')
    assert.equal(r.original, raw, '原始 type 必须保留')
    assert.ok(r.cls in TYPE_CLASS_COLORS, '每个类必须有颜色令牌')
  }
})

test('DIAGNOSIS RUNBOOK → RUNBOOK 且 original 不丢', () => {
  const r = normalizeKnowledgeType('DIAGNOSIS RUNBOOK')
  assert.equal(r.cls, 'RUNBOOK')
  assert.equal(r.short, 'RB')
  assert.equal(r.original, 'DIAGNOSIS RUNBOOK')
})

test('空 / null / undefined type → REFERENCE / REF', () => {
  assert.deepEqual(normalizeKnowledgeType(''), { cls: 'REFERENCE', short: 'REF', original: '' })
  assert.deepEqual(normalizeKnowledgeType(null), { cls: 'REFERENCE', short: 'REF', original: '' })
  assert.deepEqual(normalizeKnowledgeType(undefined), { cls: 'REFERENCE', short: 'REF', original: '' })
})

test('工程知识卡 → ENGINEERING', () => {
  assert.equal(normalizeKnowledgeType('工程知识卡').cls, 'ENGINEERING')
  assert.equal(normalizeKnowledgeType('工程知识卡').short, 'ENG')
})

test('WRONG_ANSWER 优先于 QUESTION（避免 BANK 误命中），Wrong Answer Bank → WA', () => {
  assert.equal(normalizeKnowledgeType('WRONG_ANSWER').cls, 'WRONG_ANSWER')
  assert.equal(normalizeKnowledgeType('Wrong Answer Bank').cls, 'WRONG_ANSWER')
  assert.equal(normalizeKnowledgeType('QUESTION BANK').cls, 'QUESTION')
})

test('normalizeRisk 五档命中，中文长句 → OTHER 且 short 为 —', () => {
  assert.deepEqual(normalizeRisk('READ_ONLY'), { key: 'READ_ONLY', label: '只读', short: 'RO' })
  assert.deepEqual(normalizeRisk('REFERENCE'), { key: 'REFERENCE', label: '参考', short: 'RF' })
  assert.deepEqual(normalizeRisk('APPROVAL_REQUIRED'), { key: 'APPROVAL_REQUIRED', label: '需审批', short: 'AP' })
  assert.deepEqual(normalizeRisk('HIGH'), { key: 'HIGH', label: '高风险', short: 'HI' })
  assert.deepEqual(normalizeRisk('MEDIUM'), { key: 'MEDIUM', label: '中风险', short: 'MD' })
  const other = normalizeRisk('参考资料 · 操作前查看命令风险')
  assert.equal(other.key, 'OTHER')
  assert.equal(other.short, '—')
})

test('isPlaceholderVersion 识别占位符版本', () => {
  assert.equal(isPlaceholderVersion('未注明适用组件版本'), true)
  assert.equal(isPlaceholderVersion('1.0'), false)
  assert.equal(isPlaceholderVersion(''), true)
  assert.equal(isPlaceholderVersion(undefined), true)
})

test('knowledgeDomains 与实测一致（域顺序锁死）', () => {
  assert.deepEqual(knowledgeDomains.map(d => d.id), [
    'linux', 'cloud-operations', 'docker', 'mysql', 'nginx', 'ubuntu', 'centos',
    'network', 'web-lamp', 'linux-services',
  ])
})
