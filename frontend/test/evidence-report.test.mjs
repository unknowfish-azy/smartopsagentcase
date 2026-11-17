/**
 * 证据链报告组装（P2-5）测试。
 *
 * 被测模块：src/views/incident/evidenceReport.js（纯逻辑，无 DOM 依赖）。
 * 覆盖：标题与元信息、标签翻译、表格转义、空数据占位（不编造）、
 * 经验匹配渲染、契约草案段落（digest 空说明 + JSON fence）、未生成草案占位。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'

import { buildEvidenceReport, evidenceReportFileName } from '../src/views/incident/evidenceReport.js'

const BASE_INCIDENT = {
  id: 42,
  title: '支付服务 5xx 突增',
  status: 'MITIGATING',
  severity: 'P1',
  priority: 'P2',
  source: 'ALERT',
  category: 'service-degradation',
  tags: 'payment,5xx',
  relatedService: 'payment-api',
  assigneeId: 7,
  createdAt: '2026-11-17 10:00:00',
  updatedAt: '2026-11-17 10:20:00',
  description: '支付接口错误率超过 5%'
}

const SAMPLE_EVENTS = [
  { id: 1, at: '2026-11-17 10:00:05', kind: 'STATUS_CHANGE', actorId: 7, detail: 'OPEN → ACK' },
  { id: 2, at: '2026-11-17 10:01:00', kind: 'COMMENT', actorId: null, detail: '告警自动建单' }
]

const SAMPLE_RELATIONS = [
  { id: 1, relationType: 'ALERT', refId: 9, refType: 'sentinel-alert', createdAt: '2026-11-17 10:00:10' }
]

const SAMPLE_EXPERIENCES = [
  { action: '扩容支付网关副本', source: 'OPERATOR_MEMORY', confidence: 0.86, sourceRefs: 'exp-12', verification: '观察 5xx 回落后再扩容' }
]

const SAMPLE_DRAFT = {
  summary: '针对 payment-api 的反应式恢复契约草案',
  notes: ['digest 为空：平台不越权签发', '占位谓词，待 Agent 校验'],
  draft: {
    schema_version: 'recovery-contract/v1',
    id: 'incident-reactive-42-v1',
    target: { service: 'payment-api' },
    obligations: [{ predicate_id: 'service-health-ok' }],
    digest: ''
  }
}

test('报告包含标题、工单号与导出时间', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT, generatedAt: '2026/11/17 12:00:00' })
  assert.ok(report.includes('# 证据链报告：支付服务 5xx 突增'))
  assert.ok(report.includes('#42'))
  assert.ok(report.includes('2026/11/17 12:00:00'))
})

test('基本信息翻译为中文标签并保留原始枚举', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT })
  assert.ok(report.includes('状态：处置中（MITIGATING）'))
  assert.ok(report.includes('P1 / 高'))
  assert.ok(report.includes('来源：告警（ALERT）'))
  assert.ok(report.includes('负责人：#7'))
  assert.ok(report.includes('分类：service-degradation'))
  assert.ok(report.includes('关联服务：payment-api'))
})

test('无 SLA 时写「未设置」，有 SLA 时写目标与截止', () => {
  const without = buildEvidenceReport({ incident: BASE_INCIDENT })
  assert.ok(without.includes('- SLA：未设置'))
  assert.ok(!without.includes('SLA：目标'))
  const withSla = buildEvidenceReport({ incident: { ...BASE_INCIDENT, slaTargetMinutes: 30, slaDeadline: '2026-11-17 10:30:00' } })
  assert.ok(withSla.includes('SLA：目标 30 分钟（截止 2026-11-17 10:30:00）'))
})

test('根因 / 处置过程 / 复盘结论仅在存在时出现', () => {
  const plain = buildEvidenceReport({ incident: BASE_INCIDENT })
  assert.ok(!plain.includes('- 根因：'))
  const closed = buildEvidenceReport({
    incident: { ...BASE_INCIDENT, rootCause: '下游缓存击穿', resolution: '回源限流', postmortem: '补预热' }
  })
  assert.ok(closed.includes('- 根因：下游缓存击穿'))
  assert.ok(closed.includes('- 处置过程：回源限流'))
  assert.ok(closed.includes('- 复盘结论：补预热'))
})

test('时间线表格：行数一致、类型翻译、无操作人记为系统', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT, events: SAMPLE_EVENTS })
  assert.ok(report.includes('## 事件时间线（2 条）'))
  assert.ok(report.includes('| 2026-11-17 10:00:05 | 状态流转 | #7 | OPEN → ACK |'))
  assert.ok(report.includes('| 2026-11-17 10:01:00 | 评论 | 系统 | 告警自动建单 |'))
})

test('表格单元格转义竖线与换行，不破坏 Markdown 表结构', () => {
  const report = buildEvidenceReport({
    incident: BASE_INCIDENT,
    events: [{ id: 1, at: 't1', kind: 'COMMENT', actorId: 3, detail: '含 | 竖线\n与换行' }]
  })
  assert.ok(report.includes('含 \\| 竖线 与换行'))
})

test('空时间线 / 空关联 / 空经验写占位，不编造内容', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT })
  assert.ok(report.includes('## 事件时间线（0 条）'))
  assert.ok(report.includes('_暂无事件记录。_'))
  assert.ok(report.includes('## 关联对象（0 条）'))
  assert.ok(report.includes('_暂无关联对象。_'))
  assert.ok(report.includes('## 经验库匹配（0 条）'))
  assert.ok(report.includes('_经验库无匹配记录（空结果是有效结论）。_'))
})

test('关联对象表格：类型翻译 + 目标 ID', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT, relations: SAMPLE_RELATIONS })
  assert.ok(report.includes('## 关联对象（1 条）'))
  assert.ok(report.includes('| 关联告警 | ALERT#9 | sentinel-alert | 2026-11-17 10:00:10 |'))
})

test('经验匹配渲染动作、来源、置信度与验证要点', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT, experiences: SAMPLE_EXPERIENCES })
  assert.ok(report.includes('## 经验库匹配（1 条）'))
  assert.ok(report.includes('1. **扩容支付网关副本** — 来源 OPERATOR_MEMORY · 置信度 86% · 依据 exp-12'))
  assert.ok(report.includes('- 验证要点：观察 5xx 回落后再扩容'))
})

test('契约草案段落：摘要、ID、digest 空说明与 JSON fence', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT, contractDraft: SAMPLE_DRAFT })
  assert.ok(report.includes('- 摘要：针对 payment-api 的反应式恢复契约草案'))
  assert.ok(report.includes('- 草案 ID：`incident-reactive-42-v1`'))
  assert.ok(report.includes('- 义务 1 条 · digest 空（未签发，签发由 Agent 侧完成）'))
  assert.ok(report.includes('  - digest 为空：平台不越权签发'))
  assert.ok(report.includes('```json'))
  assert.ok(report.includes('"schema_version": "recovery-contract/v1"'))
})

test('未生成契约草案时写占位，不编造草案内容', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT })
  assert.ok(report.includes('_尚未生成恢复契约草案。_'))
  assert.ok(!report.includes('```json'))
})

test('incident 缺失时抛错（页面侧由 disabled 守卫，不导出空报告）', () => {
  assert.throws(() => buildEvidenceReport({}), /incident 必填/)
})

test('文件名跟随工单 ID；缺 ID 回退 unknown', () => {
  assert.equal(evidenceReportFileName(BASE_INCIDENT), 'evidence-incident-42.md')
  assert.equal(evidenceReportFileName({}), 'evidence-incident-unknown.md')
})

test('导出说明注明快照属性与 Agent 侧留痕边界', () => {
  const report = buildEvidenceReport({ incident: BASE_INCIDENT })
  assert.ok(report.includes('导出时刻的快照'))
  assert.ok(report.includes('签发与执行回执记录在 Agent 侧'))
})
