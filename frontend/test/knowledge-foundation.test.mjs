import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeKnowledgeEntry, rankKnowledgeEntries } from '../src/views/knowledge/knowledgeModel.js'

const entries = [
  { id: 'body', title: '运行手册', content: 'nginx gateway 502', source: 'local' },
  { id: 'title', title: 'Nginx 502 排查', content: 'upstream gateway', version: '1.2', source: 'local' },
  { id: 'image', title: 'ImagePullBackOff', content: '镜像拉取失败，请检查证书和认证', source: 'local' }
].map(normalizeKnowledgeEntry)

test('canonical model preserves identity, content, version and honest review state', () => {
  const entry = entries[1]
  assert.equal(entry.id, 'title')
  assert.equal(entry.version, '1.2')
  assert.equal(entry.reviewStatus, 'UNVERIFIED')
  assert.equal(entry.lastVerifiedAt, null)
  assert.equal(entry.visibility, 'BUILTIN')
  assert.equal(entry.applicableVersion, '未注明适用组件版本')
})

test('multiword ranking weights title and reports matching terms', () => {
  const results = rankKnowledgeEntries(entries, { query: '502 nginx' })
  assert.deepEqual(results.map(entry => entry.id), ['title', 'body'])
  assert.match(results[0].matchReason, /标题/)
  assert.ok(results[0].matchedTerms.includes('nginx'))
  assert.equal(rankKnowledgeEntries(entries, { query: 'nginx nonexistent' }).length, 0)
})

test('Chinese aliases find image pull evidence without changing originals', () => {
  assert.equal(rankKnowledgeEntries(entries, { query: '镜像拉不下来' })[0].id, 'image')
  assert.deepEqual(entries.map(entry => entry.id), ['body', 'title', 'image'])
  assert.equal(rankKnowledgeEntries(entries, { query: '   ' }).length, 3)
})
