/* mosaicType.js — 照片墙类型 / 风险归一化纯函数（无 Vue 依赖，可单测）
 *
 * 设计依据：docs/design/knowledge-photo-wall-v1/DESIGN.md v1.1 §4.1
 *  - type 实测 57 种取值 → 归一成 7 个上位类（只用于着色与短码，**不改写原始 type**）
 *  - risk 实测 6 类（READ_ONLY / REFERENCE / APPROVAL_REQUIRED / HIGH / MEDIUM / 其他长句）→ 6 档短码
 *  - applicableVersion 恒占位符「未注明适用组件版本」→ 单独识别
 *
 * 颜色映射：7 类 → 5 图表色 + neutral（项目最多 5 色，见 variables.css T20）。
 * 注意 WRONG_ANSWER 必须排在 QUESTION 之前，否则「Wrong Answer Bank」会被 BANK 先命中成 QUESTION。
 */

export const TYPE_CLASSES = [
  'RUNBOOK', 'INCIDENT', 'ENGINEERING', 'WRONG_ANSWER', 'QUESTION', 'RULE', 'REFERENCE'
]

// [cls, 匹配关键词（对 type 大写后 includes）, 短码]
const TYPE_RULES = [
  ['RUNBOOK',      ['RUNBOOK', 'STANDARD'], 'RB'],
  ['INCIDENT',     ['INCIDENT', 'PRODUCTION DIAGNOSIS'], 'INC'],
  ['ENGINEERING',  ['KNOWLEDGE', 'ENGINEERING', 'OPERATIONS', 'MODULE', 'AUTOMATION', 'SPECIFICATION', 'GUIDE', 'PATH', '工程知识卡'], 'ENG'],
  ['WRONG_ANSWER', ['WRONG_ANSWER', 'WRONG', 'ANTI-PATTERN'], 'WA'],
  ['QUESTION',     ['QUESTION', 'BANK'], 'Q'],
  ['RULE',         ['RULE', 'DECISION', 'POLICY', 'SAFETY'], 'RULE'],
]

// 7 类 → 颜色令牌（5 图表色 + neutral；顺序对应 TYPE_CLASSES）
export const TYPE_CLASS_COLORS = {
  RUNBOOK:      'var(--ds-chart-1)',
  INCIDENT:     'var(--ds-chart-2)',
  ENGINEERING:  'var(--ds-chart-3)',
  WRONG_ANSWER: 'var(--ds-chart-5)',
  QUESTION:     'var(--ds-chart-4)',
  RULE:         'var(--ds-chart-1)',
  REFERENCE:    'var(--ds-chart-neutral)',
}

export function normalizeKnowledgeType (raw) {
  const original = raw == null ? '' : String(raw)
  const upper = original.trim().toUpperCase()
  if (!upper) return { cls: 'REFERENCE', short: 'REF', original }
  for (const [cls, keys, short] of TYPE_RULES) {
    if (keys.some(key => upper.includes(key))) return { cls, short, original }
  }
  return { cls: 'REFERENCE', short: 'REF', original }
}

export function normalizeRisk (raw) {
  const r = String(raw ?? '').trim().toUpperCase()
  if (r === 'READ_ONLY')         return { key: 'READ_ONLY',         label: '只读',   short: 'RO' }
  if (r === 'REFERENCE')         return { key: 'REFERENCE',         label: '参考',   short: 'RF' }
  if (r === 'APPROVAL_REQUIRED') return { key: 'APPROVAL_REQUIRED', label: '需审批', short: 'AP' }
  if (r === 'HIGH')              return { key: 'HIGH',              label: '高风险', short: 'HI' }
  if (r === 'MEDIUM')            return { key: 'MEDIUM',            label: '中风险', short: 'MD' }
  return { key: 'OTHER', label: '其他', short: '—' }
}

export const RISK_COLORS = {
  READ_ONLY:         'var(--ds-semantic-neutral)',
  REFERENCE:         'var(--ds-semantic-neutral)',
  APPROVAL_REQUIRED: 'var(--ds-semantic-info)',
  HIGH:              'var(--ds-semantic-danger)',
  MEDIUM:            'var(--ds-semantic-warning)',
  OTHER:             'var(--ds-semantic-neutral)',
}

export function isPlaceholderVersion (v) {
  return !v || String(v).trim() === '未注明适用组件版本'
}
