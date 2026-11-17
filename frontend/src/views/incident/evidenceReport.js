/**
 * 证据链报告（P2-5）纯逻辑组装模块。
 *
 * 把工单上下文（详情 / 事件时间线 / 关联对象 / 经验匹配 / 恢复契约草案）
 * 组装成一份 Markdown 快照报告，供复盘与审计导出。设计边界：
 *  - 报告是导出时刻的快照，不是实时视图；
 *  - 契约草案 digest 恒为空（未签发），签发与回执记录在 Agent 侧，
 *    平台不越权留痕——报告里如实说明，不编造「已签发」结论；
 *  - 数据缺失时写占位文案（「暂无」），不编造内容。
 *
 * 纯函数、无 DOM 依赖，标签翻译复用 incidentModel.js，可用 node:test 直测。
 */

import {
  statusLabel,
  severityLabel,
  sourceLabel,
  eventKindLabel,
  relationTypeLabel
} from './incidentModel.js'

/** Markdown 表格单元格安全化：竖线转义、换行折成空格。 */
function cell(text) {
  return String(text ?? '')
    .replace(/\|/g, '\\|')
    .replace(/\r?\n/g, ' ')
    .trim()
}

/** 无内联代码歧义的行内文本：反引号成对转义。 */
function inline(text) {
  return String(text ?? '').replace(/`/g, '\\`')
}

function fmtCount(n) {
  return Number.isFinite(n) ? n : 0
}

function eventActor(event) {
  return event?.actorId ? `#${event.actorId}` : '系统'
}

function relationTarget(relation) {
  return `${relation?.relationType ?? ''}#${relation?.refId ?? ''}`
}

function experienceLine(match) {
  const parts = [
    match?.source ? `来源 ${match.source}` : '',
    match?.confidence != null ? `置信度 ${Math.round(match.confidence * 100)}%` : '',
    match?.sourceRefs ? `依据 ${match.sourceRefs}` : ''
  ].filter(Boolean)
  return parts.join(' · ')
}

function contractSection(contractDraft) {
  if (!contractDraft?.draft) return '_尚未生成恢复契约草案。_'
  const draft = contractDraft.draft
  const lines = []
  if (contractDraft.summary) lines.push(`- 摘要：${inline(contractDraft.summary)}`)
  if (draft.id) lines.push(`- 草案 ID：\`${inline(draft.id)}\``)
  if (Array.isArray(draft.obligations)) {
    lines.push(`- 义务 ${draft.obligations.length} 条 · digest 空（未签发，签发由 Agent 侧完成）`)
  }
  if (Array.isArray(contractDraft.notes) && contractDraft.notes.length) {
    lines.push('- 组装说明：')
    for (const note of contractDraft.notes) lines.push(`  - ${inline(note)}`)
  }
  lines.push('', '```json', JSON.stringify(draft, null, 2), '```')
  return lines.join('\n')
}

/**
 * 组装证据链报告 Markdown。
 *
 * @param {object} input
 * @param {object} input.incident        工单详情（必填，来自 GET /api/incidents/{id}）
 * @param {Array}  [input.events]        事件时间线
 * @param {Array}  [input.relations]     关联对象（ALERT/AGENT_RUN/KNOWLEDGE/EVIDENCE）
 * @param {Array}  [input.experiences]   经验库匹配结果
 * @param {object} [input.contractDraft] 契约草案（{ summary, draft, notes }）
 * @param {string} [input.generatedAt]   导出时刻展示文本
 * @returns {string} Markdown 全文
 */
export function buildEvidenceReport({
  incident,
  events = [],
  relations = [],
  experiences = [],
  contractDraft = null,
  generatedAt = ''
} = {}) {
  if (!incident) throw new Error('buildEvidenceReport: incident 必填')

  const eventList = Array.isArray(events) ? events : []
  const relationList = Array.isArray(relations) ? relations : []
  const experienceList = Array.isArray(experiences) ? experiences : []

  const head = [
    `# 证据链报告：${inline(incident.title || '未命名工单')}`,
    '',
    `> 工单 \`#${incident.id ?? '—'}\` · 导出时间 ${generatedAt || '—'}`,
    '>',
    '> 本报告由平台从工单上下文导出，是导出时刻的快照：覆盖事件时间线、关联对象、',
    '> 经验匹配与恢复契约草案。契约的签发与执行回执记录在 Agent 侧，平台不越权留痕。',
    '',
    '## 基本信息',
    ''
  ]

  const info = [
    `- 状态：${statusLabel(incident.status)}（${incident.status ?? '—'}）`,
    `- 等级 / 优先级：${severityLabel(incident.severity)} / ${severityLabel(incident.priority)}`,
    `- 来源：${sourceLabel(incident.source)}（${incident.source ?? '—'}）`
  ]
  if (incident.category) info.push(`- 分类：${inline(incident.category)}`)
  if (incident.tags) info.push(`- 标签：${inline(incident.tags)}`)
  if (incident.relatedService) info.push(`- 关联服务：${inline(incident.relatedService)}`)
  info.push(`- 负责人：${incident.assigneeId ? `#${incident.assigneeId}` : '未指派'}`)
  info.push(`- 创建 / 更新：${incident.createdAt || '—'} / ${incident.updatedAt || '—'}`)
  if (incident.slaTargetMinutes) {
    info.push(`- SLA：目标 ${incident.slaTargetMinutes} 分钟（截止 ${incident.slaDeadline || '—'}）`)
  } else {
    info.push('- SLA：未设置')
  }
  if (incident.description) info.push(`- 描述：${inline(incident.description)}`)
  if (incident.rootCause) info.push(`- 根因：${inline(incident.rootCause)}`)
  if (incident.resolution) info.push(`- 处置过程：${inline(incident.resolution)}`)
  if (incident.postmortem) info.push(`- 复盘结论：${inline(incident.postmortem)}`)

  const timeline = [
    '',
    `## 事件时间线（${fmtCount(eventList.length)} 条）`,
    ''
  ]
  if (eventList.length) {
    timeline.push('| 时间 | 类型 | 操作人 | 内容 |', '| --- | --- | --- | --- |')
    for (const event of eventList) {
      timeline.push(
        `| ${cell(event.at)} | ${cell(eventKindLabel(event.kind))} | ${cell(eventActor(event))} | ${cell(event.detail)} |`
      )
    }
  } else {
    timeline.push('_暂无事件记录。_')
  }

  const relation = [
    '',
    `## 关联对象（${fmtCount(relationList.length)} 条）`,
    ''
  ]
  if (relationList.length) {
    relation.push('| 类型 | 目标 | 说明 | 创建时间 |', '| --- | --- | --- | --- |')
    for (const item of relationList) {
      relation.push(
        `| ${cell(relationTypeLabel(item.relationType))} | ${cell(relationTarget(item))} | ${cell(item.refType)} | ${cell(item.createdAt)} |`
      )
    }
  } else {
    relation.push('_暂无关联对象。_')
  }

  const experience = [
    '',
    `## 经验库匹配（${fmtCount(experienceList.length)} 条）`,
    ''
  ]
  if (experienceList.length) {
    experienceList.forEach((match, index) => {
      const meta = experienceLine(match)
      experience.push(`${index + 1}. **${inline(match?.action || '（无动作描述）')}**${meta ? ` — ${meta}` : ''}`)
      if (match?.verification) experience.push(`   - 验证要点：${inline(match.verification)}`)
    })
  } else {
    experience.push('_经验库无匹配记录（空结果是有效结论）。_')
  }

  const contract = ['', '## 恢复契约草案', '', contractSection(contractDraft)]

  const foot = [
    '',
    '---',
    '',
    '_导出自 SmartOpsAgent 工单中心 · 证据链报告为快照，非实时视图。_',
    ''
  ]

  return [...head, ...info, ...timeline, ...relation, ...experience, ...contract, ...foot].join('\n')
}

/** 导出文件名：evidence-incident-{id}.md。 */
export function evidenceReportFileName(incident) {
  const id = incident?.id != null ? incident.id : 'unknown'
  return `evidence-incident-${id}.md`
}
