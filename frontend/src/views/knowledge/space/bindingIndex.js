/* bindingIndex.js
 *
 * 纯函数：知识原子 ↔ 洞察 双向绑定索引构建。
 * 无 Date.now / Math.random / DOM 依赖；同输入 → 同输出（逐字段 deepEqual）。
 *
 * 设计依据：KNOWLEDGE-INSIGHT-BINDING.md §3–§4。
 */

// badge → platform/domain 映射表（§4.1 打分规则）
const BADGE_PLATFORM_MAP = {
  ALERTS: ['sre', 'monitoring', 'linux', 'nginx'],
  SERVERS: ['linux', 'sre', 'platform'],
  INSPECTOR: ['linux', 'sre', 'monitoring'],
  KNOWLEDGE: ['cloud', 'smartops', 'linux', 'nginx', 'mysql', 'docker'],
}

const CONTRADICTED_KEYWORDS = {
  positive: ['无需重启', '不影响', '安全', '可回滚', '无风险', '稳定', '正常'],
  negative: ['必须重启', '有影响', '风险', '不可回滚', '高危', '严重', '故障', '告警'],
}

/**
 * 把 text 按非英数字字符切 tokens（小写去重）。
 * 中英文混排时中文连续段也当作一个 token。
 */
function tokenize (text) {
  const t = String(text || '').toLowerCase().trim()
  if (!t) return []
  return [...new Set(t.split(/[\s,.;:!?()[\]{}"'_/\\|-]+/).filter(Boolean))]
}

/** 两个 source 是否同域（取第一个 . 前的段，或 URL 的 host） */
function sameSourceDomain (a, b) {
  const sa = String(a || '').toLowerCase()
  const sb = String(b || '').toLowerCase()
  if (!sa || !sb) return false
  // URL 情况：取 host
  const ha = sa.match(/^https?:\/\/([^/]+)/)?.[1]?.split('.')?.[0] || ''
  const hb = sb.match(/^https?:\/\/([^/]+)/)?.[1]?.split('.')?.[0] || ''
  if (ha && hb) return ha === hb
  // 非 URL：取第一个空格或 . 前的段
  const pa = sa.split(/[\s.]+/)[0]
  const pb = sb.split(/[\s.]+/)[0]
  return pa && pb && pa === pb
}

/** atom 的 platform 是否命中 insight 的 badge 映射表 */
function platformMatchesBadge (atomPlatform, badge) {
  const list = BADGE_PLATFORM_MAP[String(badge || '').toUpperCase()] || []
  const p = String(atomPlatform || '').toLowerCase()
  if (!p) return false
  return list.some(item => p.includes(item) || item.includes(p))
}

/**
 * 打分（KNOWLEDGE-INSIGHT-BINDING.md §4.1）。
 * 纯函数，输入 atom + insight，输出 0+ 浮点数。
 */
export function scoreAtom (atom, insight) {
  let score = 0

  const aService = String(atom?.service || '').toLowerCase()
  const aDomain  = String(atom?.domain || '').toLowerCase()
  const aTags    = Array.isArray(atom?.tags) ? atom.tags.map(t => String(t).toLowerCase()) : []
  const _aPlatform = String(atom?.platform || '').toLowerCase()

  const iService = String(insight?.service || '').toLowerCase()
  const iDomain  = String(insight?.domain || '').toLowerCase()
  const iTitle   = String(insight?.title || '')
  const iQuestion = String(insight?.question || '')
  const iSource  = String(insight?.source || '')
  const iBadge   = String(insight?.badge || '').toUpperCase()

  // 同 service 最强
  if (aService && iService && aService === iService) score += 3.0
  // 同 domain
  if (aDomain && iDomain && aDomain === iDomain) score += 2.0
  // badge platform 映射
  if (platformMatchesBadge(atom?.platform, iBadge)) score += 1.0
  // tags ∩ tokens(title + question) 的覆盖率
  const textTokens = new Set(tokenize(iTitle + ' ' + iQuestion))
  if (aTags.length > 0) {
    const hits = aTags.filter(tag => textTokens.has(tag)).length
    score += 1.2 * hits / aTags.length
  }
  // source 同域
  if (sameSourceDomain(iSource, atom?.source)) score += 0.8
  // freshness 负面扣分
  if (atom?.freshness?.status === 'CONTRADICTED') score -= 2.0

  return Math.round(score * 1000) / 1000
}

/**
 * 检测 contradicts（§4.3 结构判定）。
 * 同 service + 同 version 下，atom 含 positive 词、insight 含 negative 词 → true。
 * Phase A 只做结构判定，不做语义推理。
 */
function isContradicted (atom, insight) {
  const aService = String(atom?.service || '').toLowerCase()
  const aVersion = String(atom?.version || '').toLowerCase()
  const iService = String(insight?.service || '').toLowerCase()
  const iVersion = String(insight?.version || '').toLowerCase()
  // insight 侧可能没有 version 字段 → 跳过该约束
  if (aService && iService && aService !== iService) return false
  if (iVersion && aVersion && aVersion !== iVersion) return false

  const atomText = String(atom?.summary || atom?.content || '').toLowerCase()
  const insightText = String(insight?.title || insight?.description || insight?.question || '').toLowerCase()

  const hasPositive = CONTRADICTED_KEYWORDS.positive.some(k => atomText.includes(k))
  const hasNegative = CONTRADICTED_KEYWORDS.negative.some(k => insightText.includes(k))
  return hasPositive && hasNegative
}

/** 打分高的 atoms 中找出 contradicts 的（只在同 service/version 下） */
function findContradictions (topAtoms, insight) {
  return topAtoms.filter(a => isContradicted(a.atom, insight))
}

/**
 * 给一条洞察生成 binding.explanation（§4.2）。
 * 由命中项拼接，禁止空字符串。
 */
function buildExplanation (atomResults, insight) {
  const parts = []
  if (atomResults.length === 0) {
    const badge = String(insight?.badge || '')
    parts.push(`纯运行态洞察（${badge}），暂未匹配到知识条目`)
    return parts.join('；')
  }
  // 最多选前 2 条高分 atom 出现在解释里
  for (const { atom, reasons } of atomResults.slice(0, 2)) {
    const ident = String(atom.title || atom.id || '')
    parts.push(`「${ident}」命中：${reasons.join('、')}`)
  }
  return parts.join('；') || '匹配到知识条目'
}

/**
 * 构建一条 atom → insight 的匹配理由数组（用于 explanation 与日志）。
 */
function matchReasons (atom, insight) {
  const reasons = []
  const aService = String(atom?.service || '').toLowerCase()
  const iService = String(insight?.service || '').toLowerCase()
  const aDomain  = String(atom?.domain || '').toLowerCase()
  const iDomain  = String(insight?.domain || '').toLowerCase()
  if (aService && iService && aService === iService) reasons.push(`服务 ${aService}`)
  if (aDomain && iDomain && aDomain === iDomain) reasons.push(`域 ${aDomain}`)
  if (platformMatchesBadge(atom?.platform, insight?.badge)) reasons.push(`badge 平台命中`)
  const textTokens = new Set(tokenize(String(insight?.title || '') + ' ' + String(insight?.question || '')))
  const hits = (atom?.tags || []).filter(t => textTokens.has(String(t).toLowerCase()))
  if (hits.length) reasons.push(`标签 ${hits.slice(0, 3).join('、')}`)
  if (sameSourceDomain(String(insight?.source || ''), String(atom?.source || ''))) reasons.push(`来源同域`)
  return reasons.length ? reasons : ['低置信匹配']
}

/**
 * 为一条洞察生成其完整 binding 结构（§2.2）。
 * 独立函数，可被 NaturalLanguageInsightsView 直接调用来 enrich 洞察结果。
 */
export function enrichInsightBinding (insight, atoms) {
  if (!insight || !Array.isArray(atoms)) atoms = []

  // 给 insight 补一个稳定 id（按 badge + title 规则生成）
  const id = insight.id || generateInsightId(insight)

  // 对所有 atom 打分
  const scored = atoms
    .map(atom => ({ atom, score: scoreAtom(atom, insight) }))
    .sort((a, b) => b.score - a.score)

  const MIN_SCORE = 1.5
  const topAtoms = scored.filter(r => r.score >= MIN_SCORE).slice(0, 3)

  if (topAtoms.length === 0) {
    return {
      insight: {
        ...insight,
        id,
        confidence: insight.confidence || 'derived',
        binding: {
          mode: 'operational',
          atoms: [],
          explanation: buildExplanation([], insight),
        },
      },
      newThreads: [],
    }
  }

  // 找 contradicts
  const contradictions = findContradictions(topAtoms.map(t => t.atom), insight)
  const contradictionIds = new Set(contradictions.map(c => c.id))

  // 组装 atoms 列表
  const bindingAtoms = topAtoms.map(({ atom, score }) => ({
    atomId: atom.id,
    weight: Math.min(1, score / 4),  // score / 4 归一化到 0-1，cap 1
    anchor: {
      field: 'summary',  // Phase A 默认锚定 summary
    },
    stale: atom?.freshness?.status === 'STALE',
  }))

  // 检测整体 mode
  let mode = 'derived'
  if (contradictionIds.size === bindingAtoms.length) {
    mode = 'contradicts'
  } else if (contradictionIds.size > 0) {
    // 部分冲突：主 mode = derived，但给冲突的 atom 单独标记
    mode = 'derived'
  }

  const withReasons = topAtoms.map(r => ({ atom: r.atom, reasons: matchReasons(r.atom, insight) }))
  const explanation = buildExplanation(withReasons, insight)

  // 生成 threads 供外部使用
  const newThreads = bindingAtoms.map(ba => ({
    insightId: id,
    atomId: ba.atomId,
    relation: contradictionIds.has(ba.atomId) ? 'contradicts' : mode,
    weight: ba.weight,
    stale: !!ba.stale,
  }))

  return {
    insight: {
      ...insight,
      id,
      confidence: insight.confidence || 'derived',
      binding: {
        mode,
        atoms: bindingAtoms,
        explanation,
      },
    },
    newThreads,
  }
}

/** 稳定 insight id 生成：badge 小写 + title 分词 slug */
function generateInsightId (insight) {
  const badge = String(insight?.badge || 'insight').toLowerCase()
  const title = tokenize(insight?.title || insight?.question || '')
    .slice(0, 3).join('-').replace(/[^a-z0-9-]/g, '')
  return `insight.${badge}.${title || 'unidentified'}`
}

/**
 * 主入口：构建完整绑定索引（§3）。
 *
 * @param {Array} atoms     知识原子数组
 * @param {Array} insights  洞察数组（可以是原始洞察，也可以是已经带 binding 的——函数不会二次改写）
 * @returns {{ byAtom: Map, byInsight: Map, threads: Thread[], stats: Stats }}
 */
export function buildBindingIndex (atoms, insights) {
  atoms    = Array.isArray(atoms)    ? atoms    : []
  insights = Array.isArray(insights) ? insights : []

  const byAtom    = new Map()  // atomId → InsightRef[]
  const byInsight = new Map()  // insightId → AtomAnchor[]
  const threads   = []

  let bound = 0, operational = 0, contradicts = 0, staleAtoms = 0

  // 先统计陈旧原子（一次遍历够）
  for (const a of atoms) {
    if (a?.freshness?.status === 'STALE') staleAtoms++
  }

  for (const ins of insights) {
    const id = String(ins?.id || generateInsightId(ins))
    let binding, mode, atomAnchors

    if (ins?.binding && Array.isArray(ins.binding.atoms)) {
      // 洞察已经有 binding → 直接用，不重新匹配（尊重上游 enrich 结果）
      binding = ins.binding
      mode = binding.mode || 'operational'
      atomAnchors = binding.atoms
    } else {
      // 原始洞察 → 做一次匹配
      const enriched = enrichInsightBinding(ins, atoms)
      mode = enriched.insight.binding.mode
      atomAnchors = enriched.insight.binding.atoms
    }

    byInsight.set(id, atomAnchors)

    if (mode === 'operational' || atomAnchors.length === 0) {
      operational++
      // operational 洞察没有 threads
      continue
    }

    bound++
    if (mode === 'contradicts') contradicts++

    for (const anchor of atomAnchors) {
      const thread = {
        insightId: id,
        atomId: anchor.atomId,
        relation: mode === 'contradicts' ? 'contradicts' : 'derived',
        weight: typeof anchor.weight === 'number' ? anchor.weight : 0.5,
        stale: !!anchor.stale,
      }
      threads.push(thread)

      // 反向索引 atom → insight refs
      const list = byAtom.get(anchor.atomId) || []
      list.push({ insightId: id, relation: thread.relation, weight: thread.weight })
      byAtom.set(anchor.atomId, list)
    }
  }

  // 稳定排序 threads：(insightId, atomId) 字典序
  threads.sort((a, b) => {
    if (a.insightId !== b.insightId) return a.insightId.localeCompare(b.insightId)
    return a.atomId.localeCompare(b.atomId)
  })

  // 统计 unbound = bound + operational == insights.length ? 0 : ...
  // 实际上 "未绑定" 在这里就是 operational（纯运行态无知识锚点）。
  // 按 §B2：operational ⇔ atoms.length === 0。
  const unbound = operational  // 纯运行态且 atoms 为空，"未绑定" 就是 operational

  return {
    byAtom,
    byInsight,
    threads,
    stats: {
      bound,
      unbound,
      operational,
      contradicts,
      staleAtoms,
      totalInsights: insights.length,
    },
  }
}
