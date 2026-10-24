import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import { reviewQueueWithGuide } from '../src/components/knowledge/knowledgeCandidateGuide.js'
import { renderKnowledgeMarkdown } from '../src/components/knowledge/renderKnowledgeMarkdown.js'

test('knowledge candidate review route is available under Memory', async () => {
  const router = await readFile(new URL('../src/router/index.js', import.meta.url), 'utf8')
  const navigation = await readFile(new URL('../src/navigation/personalSystemNavigation.js', import.meta.url), 'utf8')

  assert.match(router, /knowledge\/review/)
  assert.match(router, /KnowledgeCandidateReview/)
  assert.match(navigation, /KNOWLEDGE REVIEW/)
  assert.match(navigation, /知识审核/)
})

test('review workbench loads candidates and renders markdown without publishing controls', async () => {
  const view = await readFile(new URL('../src/views/knowledge/KnowledgeCandidateReviewView.vue', import.meta.url), 'utf8')
  const api = await readFile(new URL('../src/api/operations.js', import.meta.url), 'utf8')

  assert.match(api, /getKnowledgeCandidates/)
  assert.match(api, /getKnowledgeCandidate/)
  assert.match(view, /待人工审核/)
  assert.match(view, /contentMarkdown/)
  assert.match(view, /renderKnowledgeMarkdown/)
  assert.match(view, /v-html="renderedMarkdown"/)
  assert.match(view, /来源 Trace/)
  assert.doesNotMatch(view, /直接发布|publishKnowledge/)
})

test('empty review queue exposes clearly labelled virtual guidance without persisting it', () => {
  const guided = reviewQueueWithGuide({ items: [], total: 0, page: 1, pageSize: 20 })

  assert.equal(guided.guideMode, true)
  assert.equal(guided.items.length, 8)
  assert.equal(guided.items[0].isGuide, true)
  assert.match(guided.items[0].title, /演示/)
  assert.match(guided.items[0].contentMarkdown, /操作步骤/)
  assert.match(guided.items[0].contentMarkdown, /报错原因/)
  assert.match(guided.items[0].contentMarkdown, /验证/)
  assert.equal(guided.total, 0)
})

test('virtual review queue covers representative operation domains with detailed evidence notes', () => {
  const guided = reviewQueueWithGuide({ items: [], total: 0, page: 1, pageSize: 20 })
  const tools = guided.items.map(item => item.toolId)

  assert.deepEqual(tools, [
    'k8s.service.diagnose',
    'docker.container.diagnose',
    'nginx.upstream.diagnose',
    'mysql.connection.diagnose',
    'linux.storage.diagnose',
    'k8s.ingress.tls.diagnose',
    'k8s.image.pull.diagnose',
    'mysql.replication.diagnose'
  ])

  for (const item of guided.items) {
    assert.equal(item.isGuide, true)
    assert.match(item.title, /【演示】/)
    assert.match(item.contentMarkdown, /## 已确认事实/)
    assert.match(item.contentMarkdown, /## 当前推测/)
    assert.match(item.contentMarkdown, /## 操作命令/)
    assert.match(item.contentMarkdown, /## 报错原因分析/)
    assert.match(item.contentMarkdown, /## 修复后验证/)
    assert.match(item.contentMarkdown, /## 风险与回滚/)
  }
})

test('real candidates replace virtual guidance as soon as data exists', () => {
  const real = { id: 9, title: '真实候选', status: 'PENDING_REVIEW' }
  const guided = reviewQueueWithGuide({ items: [real], total: 1, page: 1, pageSize: 20 })

  assert.equal(guided.guideMode, false)
  assert.deepEqual(guided.items, [real])
  assert.equal(guided.total, 1)
})

test('knowledge markdown renders readable structure and escapes embedded html', () => {
  const html = renderKnowledgeMarkdown(`# 排障笔记

> 这是演示说明

## 操作步骤

1. 查看状态
2. 收集日志

- [ ] 已验证

\`\`\`bash
kubectl get pod -A
\`\`\`

<script>alert('unsafe')</script>`)

  assert.match(html, /<h1>排障笔记<\/h1>/)
  assert.match(html, /<blockquote><p>这是演示说明<\/p><\/blockquote>/)
  assert.match(html, /<ol><li>查看状态<\/li><li>收集日志<\/li><\/ol>/)
  assert.match(html, /class="task-list-item"/)
  assert.match(html, /<pre><code class="language-bash">kubectl get pod -A<\/code><\/pre>/)
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /&lt;script&gt;/)
})
