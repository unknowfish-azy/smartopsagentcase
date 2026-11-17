// 科研助手引擎：对「知识蒸馏快照」做确定性检索、组卡、综述组装与流水线编排。
//
// 诚实边界（与蒸馏器一致）：
// - 这里没有大模型。所有"答案 / 综述 / 摘要"都是对快照的结构化组装，页面必须如实声明。
// - 一切引用都能回溯到语料库真实路径（doc.path），检索不到就如实返回空。
// - 不 import scripts/atlas/distill-atlas.mjs（那是 Node 模块，浏览器构建进不去），
//   分词与停用词在本地维护，两边的语义保持一致。

/** 停用词：与蒸馏器 STOP_TERMS 保持同集，中文虚词 bigram + 英文功能词。 */
export const STOP_TERMS = Object.freeze(new Set([
  '一个', '一些', '什么', '我们', '你们', '他们', '这个', '那个', '这些', '那些',
  '可以', '应该', '需要', '使用', '通过', '如果', '但是', '然后', '因此', '所以',
  '进行', '以及', '或者', '例如', '注意', '问题', '内容', '时候', '如何', '为什么',
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'your', 'are', 'not',
  'http', 'https', 'com', 'www', 'org', 'png', 'jpg', 'img', 'src', 'alt'
]))

const MAX_QUERY_TOKENS = 8
const MAX_RESULT_SECTIONS = 4

/** 把自然语言问题拆成可检索 token：英文单词 + 中文短词/双字组。 */
export function tokenizeQuery(query) {
  const text = String(query ?? '').toLowerCase()
  const tokens = []
  const seen = new Set()
  const push = token => {
    if (!token || token.length < 2 || seen.has(token) || STOP_TERMS.has(token)) return
    seen.add(token)
    tokens.push(token)
  }
  for (const match of text.matchAll(/[a-z0-9][a-z0-9-]+/g)) push(match[0])
  for (const match of text.matchAll(/[\u4e00-\u9fa5]{2,}/g)) {
    const run = match[0]
    if (run.length <= 6) push(run)
    for (let i = 0; i + 2 <= run.length; i += 1) push(run.slice(i, i + 2))
  }
  return tokens.slice(0, MAX_QUERY_TOKENS)
}

/** 单文档打分：标题命中权重最高，其次章节标题，再次关键词表与正文节选。 */
function scoreDocument(doc, tokens) {
  let score = 0
  const matchedTerms = []
  const sections = []
  const titleLower = doc.title.toLowerCase()
  for (const token of tokens) {
    let hit = 0
    if (titleLower.includes(token)) hit += 8
    const headingHits = doc.headings.filter(heading => heading.text.toLowerCase().includes(token))
    hit += headingHits.length * 4
    const termEntry = doc.terms.find(term => term.term === token)
    if (termEntry) hit += Math.min(termEntry.count, 6) * 2
    const sectionHits = doc.sections.filter(section =>
      section.text.toLowerCase().includes(token) || section.excerpt.toLowerCase().includes(token))
    hit += sectionHits.length * 2
    if (hit === 0) continue
    matchedTerms.push(token)
    for (const section of sectionHits) {
      if (!sections.some(item => item.text === section.text)) sections.push(section)
    }
    score += hit
  }
  return {
    score,
    matchedTerms,
    sections: sections.slice(0, MAX_RESULT_SECTIONS)
  }
}

/**
 * 快照检索：返回带引用的文档命中列表。
 * @returns {{tokens: string[], results: Array<{doc, score, matchedTerms, sections}>}}
 */
export function searchDocuments(snapshot, query, { limit = 6, courseId = null } = {}) {
  const tokens = tokenizeQuery(query)
  if (tokens.length === 0) return { tokens, results: [] }
  const pool = courseId ? snapshot.documents.filter(doc => doc.courseId === courseId) : snapshot.documents
  // IDF 罕见度权重：只在少数文档出现的 token 更能说明相关性，压制常见 bigram 的误命中。
  const docFrequency = new Map(tokens.map(token => [token, 0]))
  for (const doc of pool) {
    for (const token of tokens) {
      if (scoreDocument(doc, [token]).score > 0) docFrequency.set(token, docFrequency.get(token) + 1)
    }
  }
  const weight = token => 1 + Math.log2(pool.length / (docFrequency.get(token) + 1))
  const results = []
  for (const doc of pool) {
    const hit = scoreDocument(doc, tokens)
    if (hit.score === 0) continue
    const rarity = hit.matchedTerms.reduce((sum, token) => sum + weight(token), 0) / hit.matchedTerms.length
    results.push({ doc, score: Math.round(hit.score * rarity), matchedTerms: hit.matchedTerms, sections: hit.sections })
  }
  results.sort((a, b) => b.score - a.score || a.doc.id.localeCompare(b.doc.id))
  return { tokens, results: results.slice(0, limit) }
}

/** 单篇文档成卡：章节有正文的才成卡，正反两面都来自快照原文。组卷与知识树共用。 */
export function buildDocCards(doc) {
  const cards = []
  for (const section of doc.sections) {
    if (!section.excerpt || section.excerpt.length < 12) continue
    if (section.level === 1) continue
    cards.push({
      id: `${doc.id}:${section.text}`,
      front: section.text,
      source: doc.title,
      courseId: doc.courseId,
      back: {
        excerpt: section.excerpt,
        docTitle: doc.title,
        path: doc.path,
        commands: doc.commands.slice(0, 3).map(item => item.cmd)
      }
    })
  }
  return cards
}

/** 资料卡组卷：按快照文档顺序取前 limit 张卡。 */
export function buildDeck(snapshot, { courseId = null, limit = 48 } = {}) {
  const cards = []
  for (const doc of snapshot.documents) {
    if (courseId && doc.courseId !== courseId) continue
    for (const card of buildDocCards(doc)) {
      cards.push(card)
      if (cards.length >= limit) return cards
    }
  }
  return cards
}

/**
 * 章节依赖：只从原文真实声明与快照顺序中抽取，不做语义推断。
 * - 「已完成第 N 课」/「第 N 课」→ required（原文把它列为前置）
 * - 「建议先完成第 N 课」→ suggested（原文措辞是建议）
 * - 同课程上一篇 → order（快照文档顺序，结构性顺序而非硬依赖）
 * 目标课次不在快照里时 docTitle 为 null，由界面如实标「未收录」。
 * 返回 Map<docId, { deps, declared, excerpt }>：declared=true 表示原文写了「前置知识」节，
 * excerpt 是该节原文首句（未提课次时界面展示原文，不擅自说「未声明」）。
 */
export function buildDependencyMap(snapshot) {
  const lessonDocs = new Map()
  for (const doc of snapshot.documents) {
    const matched = /第\s*(\d+)\s*课/.exec(doc.title)
    if (matched && !lessonDocs.has(Number(matched[1]))) lessonDocs.set(Number(matched[1]), doc)
  }

  const map = new Map()
  const prevInCourse = new Map()
  for (const doc of snapshot.documents) {
    const deps = []
    const prereq = doc.sections.find(section => section.text === '前置知识')
    if (prereq?.excerpt) {
      const seen = new Set()
      const pattern = /建议先完成第\s*(\d+)\s*课|已完成第\s*(\d+)\s*课|第\s*(\d+)\s*课/g
      for (const matched of prereq.excerpt.matchAll(pattern)) {
        const lesson = Number(matched[1] || matched[2] || matched[3])
        const kind = matched[1] ? 'suggested' : 'required'
        const target = lessonDocs.get(lesson)
        const key = `${kind}:${lesson}`
        if (seen.has(key) || target?.id === doc.id) continue
        seen.add(key)
        deps.push({ kind, label: `第 ${lesson} 课`, docTitle: target?.title || null })
      }
    }
    const prev = prevInCourse.get(doc.courseId)
    if (prev) deps.push({ kind: 'order', label: '顺序·上一课', docTitle: prev.title })
    prevInCourse.set(doc.courseId, doc)

    if (deps.length || prereq?.excerpt) {
      map.set(doc.id, {
        deps,
        declared: Boolean(prereq?.excerpt),
        excerpt: prereq?.excerpt ? prereq.excerpt.split(/[。；]/)[0].trim() : ''
      })
    }
  }
  return map
}

/**
 * 综述组装：按选中文档集合产出结构化综述（概览 → 主题脉络 → 命令面板 → 引用）。
 * 每条引用都是快照里的真实节选，编号可在正文里回查。
 */
export function buildReview(snapshot, { courseId = null, docIds = null, topic = '' } = {}) {
  const docs = snapshot.documents.filter(doc => {
    if (courseId && doc.courseId !== courseId) return false
    if (docIds && docIds.length > 0 && !docIds.includes(doc.id)) return false
    return true
  })
  const references = docs.map((doc, index) => ({
    n: index + 1,
    id: doc.id,
    title: doc.title,
    path: doc.path,
    course: snapshot.courses.find(course => course.id === doc.courseId)?.label ?? doc.courseId,
    chars: doc.chars,
    quotes: doc.sections.filter(section => section.excerpt.length >= 12).slice(0, 2)
  }))
  const commandCounts = new Map()
  for (const doc of docs) {
    for (const { cmd, count } of doc.commands) {
      commandCounts.set(cmd, (commandCounts.get(cmd) ?? 0) + count)
    }
  }
  const commands = [...commandCounts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 10)
    .map(([cmd, count]) => ({ cmd, count }))
  return {
    topic,
    generatedFrom: 'atlasDistilled.json',
    overview: {
      documents: docs.length,
      chars: docs.reduce((sum, doc) => sum + doc.chars, 0),
      sections: docs.reduce((sum, doc) => sum + doc.sections.length, 0),
      codeBlocks: docs.reduce((sum, doc) => sum + doc.codeBlocks, 0)
    },
    threads: references.map(ref => ({
      n: ref.n,
      title: ref.title,
      headings: docs.find(doc => doc.id === ref.id).headings.slice(0, 4).map(heading => heading.text),
      quotes: ref.quotes
    })),
    commands,
    references
  }
}

/** 综述导出为 markdown（正文用 [n] 引用编号，文末列出真实路径）。 */
export function reviewToMarkdown(review) {
  const lines = []
  lines.push(`# ${review.topic || '研究综述'}`)
  lines.push('')
  lines.push(`> 覆盖 ${review.overview.documents} 篇文档 · ${review.overview.chars} 字符 · 引用 ${review.references.length} 篇。`)
  lines.push('> 本综述由检索快照结构化组装，非大模型生成；每条内容都可回查语料路径。')
  lines.push('')
  lines.push('## 主题脉络')
  lines.push('')
  for (const thread of review.threads) {
    lines.push(`### [${thread.n}] ${thread.title}`)
    for (const heading of thread.headings) lines.push(`- ${heading}`)
    for (const quote of thread.quotes) lines.push(`  > ${quote.excerpt}`)
    lines.push('')
  }
  if (review.commands.length > 0) {
    lines.push('## 高频命令')
    lines.push('')
    for (const { cmd, count } of review.commands) lines.push(`- \`${cmd}\` ×${count}`)
    lines.push('')
  }
  lines.push('## 引用')
  lines.push('')
  for (const ref of review.references) lines.push(`[${ref.n}] ${ref.title} — \`${ref.path}\` (${ref.course})`)
  return lines.join('\n')
}

const PIPELINE_STAGES = Object.freeze([
  { id: 'parse', label: 'PARSE / 解析问题' },
  { id: 'retrieve', label: 'RETRIEVE / 全库检索' },
  { id: 'filter', label: 'FILTER / 相关性筛选' },
  { id: 'summarize', label: 'SUMMARIZE / 证据汇总' },
  { id: 'produce', label: 'PRODUCE / 引用产出' }
])

/**
 * 检索编排：把一次问答拆成五个可观察的阶段，每阶段的数据都是引擎真实中间产物。
 * 阶段推进由视图控制（配合 reduced-motion 直接全量展示），这里一次性给全。
 */
export function runPipeline(snapshot, query, { courseId = null } = {}) {
  const { tokens, results } = searchDocuments(snapshot, query, { limit: 5, courseId })
  const scanned = courseId
    ? snapshot.documents.filter(doc => doc.courseId === courseId).length
    : snapshot.documents.length
  const candidates = results.map(result => ({ id: result.doc.id, title: result.doc.title, score: result.score }))
  const citations = results.slice(0, 3).map((result, index) => ({
    n: index + 1,
    title: result.doc.title,
    path: result.doc.path,
    excerpt: result.sections[0]?.excerpt ?? result.doc.headings.map(heading => heading.text).join(' · ')
  }))
  const data = {
    parse: { tokens },
    retrieve: { scanned, candidateCount: results.length, candidates },
    filter: { kept: results.length, threshold: 'score > 0', candidates: candidates.slice(0, 5) },
    summarize: { citations },
    produce: {
      answerable: results.length > 0,
      citationCount: citations.length,
      statement: results.length > 0
        ? `在 ${scanned} 篇文档中找到 ${results.length} 处相关证据，可给出 ${citations.length} 条带路径的引用。`
        : `在 ${scanned} 篇文档中没有命中，如实返回空结果，不编造答案。`
    }
  }
  return PIPELINE_STAGES.map(stage => ({ ...stage, data: data[stage.id] }))
}
