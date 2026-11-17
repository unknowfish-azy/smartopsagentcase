import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildDeck,
  buildReview,
  reviewToMarkdown,
  runPipeline,
  searchDocuments,
  tokenizeQuery
} from '../src/domain/scholar/scholarEngine.js'
import snapshot from '../src/views/atlas/atlasDistilled.json' with { type: 'json' }

test('tokenizeQuery: latin lowercased, cjk split into run + bigrams, stopwords dropped', () => {
  const tokens = tokenizeQuery('GPU 性能调优')
  assert.ok(tokens.includes('gpu'))
  assert.ok(tokens.includes('性能'))
  assert.ok(tokens.includes('性能调优'), 'short cjk runs are kept as whole tokens')
  assert.ok(!tokenizeQuery('性能 如何').includes('如何'), 'stopword bigrams must be dropped')
  assert.ok(tokenizeQuery('the and com').length === 0, 'pure stopwords -> empty')
  assert.ok(tokenizeQuery('').length === 0)
})

test('tokenizeQuery: capped at 8 tokens for long questions', () => {
  const tokens = tokenizeQuery('docker compose kubernetes prometheus grafana nginx mysql redis 内存泄漏')
  assert.ok(tokens.length <= 8)
})

test('searchDocuments: real snapshot ranks relevant docs first with matched sections', () => {
  const { tokens, results } = searchDocuments(snapshot, 'GPU 性能优化', { limit: 5 })
  assert.ok(tokens.includes('gpu'))
  assert.ok(results.length > 0)
  assert.ok(results[0].score >= results[results.length - 1].score, 'sorted by score desc')
  const top = results[0]
  assert.ok(top.matchedTerms.length > 0)
  assert.ok(top.doc.path.length > 0, 'citation carries real corpus path')
  for (const result of results) {
    for (const section of result.sections) {
      assert.ok(typeof section.excerpt === 'string', 'sections are real snapshot objects')
    }
  }
})

test('searchDocuments: no hit returns empty honestly, garbage query included', () => {
  const { results, tokens } = searchDocuments(snapshot, 'qqzzxxwwvv')
  assert.ok(tokens.includes('qqzzxxwwvv'), 'garbage token is tokenized but matches nothing')
  assert.equal(results.length, 0)
})

test('searchDocuments: courseId filter narrows the corpus', () => {
  const docker = snapshot.courses.find(course => course.id === 'Docker运维课')
  if (!docker) return
  const { results } = searchDocuments(snapshot, 'docker 镜像', { courseId: docker.id, limit: 20 })
  assert.ok(results.length > 0)
  assert.ok(results.every(result => result.doc.courseId === docker.id))
})

test('buildDeck: cards only from real sections, deterministic order, capped', () => {
  const deck = buildDeck(snapshot, { limit: 40 })
  assert.ok(deck.length > 0 && deck.length <= 40)
  for (const card of deck) {
    assert.ok(card.front.length >= 2)
    assert.ok(card.back.excerpt.length >= 12, 'back must quote real excerpt')
    assert.ok(card.back.path.startsWith(/^(AI Infra|Docker|云原生|RH|[^/]+\.md)/.source) || card.back.path.includes('/'))
  }
  const again = buildDeck(snapshot, { limit: 40 })
  assert.deepEqual(deck.map(card => card.id), again.map(card => card.id))
  // courseId 过滤
  const dockerDeck = buildDeck(snapshot, { courseId: 'Docker运维课' })
  if (dockerDeck.length > 0) assert.ok(dockerDeck.every(card => card.courseId === 'Docker运维课'))
})

test('buildReview: references numbered, commands aggregated, quotes from snapshot', () => {
  const review = buildReview(snapshot, { courseId: 'Docker运维课', topic: 'Docker 运维要点' })
  assert.ok(review.overview.documents > 0)
  assert.equal(review.references[0].n, 1)
  assert.equal(review.references[review.references.length - 1].n, review.references.length)
  assert.ok(review.threads.every(thread => thread.headings.length > 0))
  for (const ref of review.references) {
    for (const quote of ref.quotes) assert.ok(quote.excerpt.length >= 12)
  }
  assert.ok(review.commands.every(cmd => typeof cmd.count === 'number'))
})

test('reviewToMarkdown: citations listed with real paths and honest disclaimer', () => {
  const review = buildReview(snapshot, { courseId: 'Docker运维课', topic: 'Docker 运维要点' })
  const markdown = reviewToMarkdown(review)
  assert.ok(markdown.startsWith('# Docker 运维要点'))
  assert.ok(markdown.includes('非大模型生成'))
  for (const ref of review.references) {
    assert.ok(markdown.includes(`[${ref.n}] ${ref.title}`))
    assert.ok(markdown.includes(ref.path))
  }
})

test('runPipeline: five observable stages with real intermediate data', () => {
  const stages = runPipeline(snapshot, 'docker 镜像分层')
  assert.deepEqual(stages.map(stage => stage.id), ['parse', 'retrieve', 'filter', 'summarize', 'produce'])
  const [parse, retrieve, filter, summarize, produce] = stages
  assert.ok(parse.data.tokens.includes('docker'))
  assert.ok(retrieve.data.scanned === snapshot.documents.length)
  assert.ok(retrieve.data.candidateCount > 0)
  assert.equal(filter.data.kept, retrieve.data.candidateCount)
  assert.ok(summarize.data.citations.every(citation => citation.path.includes('/')))
  assert.equal(produce.data.answerable, true)
  assert.ok(produce.data.statement.includes('引用'))
  // 重复运行结果一致（确定性）
  assert.deepEqual(runPipeline(snapshot, 'docker 镜像分层'), stages)
})

test('runPipeline: unanswerable question reports empty honestly', () => {
  const stages = runPipeline(snapshot, 'qqzzxxwwvv')
  const produce = stages.find(stage => stage.id === 'produce')
  assert.equal(produce.data.answerable, false)
  assert.equal(produce.data.citationCount, 0)
  assert.ok(produce.data.statement.includes('不编造'))
})
