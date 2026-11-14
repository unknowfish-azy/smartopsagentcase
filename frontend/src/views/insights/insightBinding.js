/* insightBinding.js
 *
 * 把 NaturalLanguageInsightsView 的原始洞察结果 enrich 出 id/binding/confidence。
 * 纯函数，依赖 bindingIndex.js 的 enrichInsightBinding 与 knowledgeEntries。
 *
 * 按 KNOWLEDGE-INSIGHT-BINDING.md §5：
 *   enrichInsight(insight, knowledgeEntries) → enriched insight + 诊断信息
 */

import { enrichInsightBinding } from '../knowledge/space/bindingIndex.js'
import { knowledgeEntries, knowledgeDomains } from '../knowledge/knowledgeCatalog.js'

/**
 * 为一条 insight 做绑定 enrich：
 *   - 补 id（如果没有）
 *   - 补 confidence（缺省 'derived'）
 *   - 补 binding（mode / atoms / explanation）
 *
 * 调用侧：NaturalLanguageInsightsView.vue 在 analyze() 完成后调这个。
 * 返回 { enriched: {..., id, confidence, binding}, threads }
 */
export function enrichInsight (insight) {
  if (!insight) return { enriched: insight, threads: [] }
  const { insight: enriched, newThreads: threads } = enrichInsightBinding(
    insight, knowledgeEntries
  )
  return { enriched, threads }
}

/**
 * 批量 enrich（一次 enrich 多条，返回数组 + 合并 threads）。
 */
export function enrichInsights (insights) {
  if (!Array.isArray(insights)) return { enriched: [], threads: [] }
  const enriched = []
  const threads  = []
  for (const ins of insights) {
    const r = enrichInsight(ins)
    enriched.push(r.enriched)
    threads.push(...r.threads)
  }
  return { enriched, threads }
}

export { knowledgeDomains }
