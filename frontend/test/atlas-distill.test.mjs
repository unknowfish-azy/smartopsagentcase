import assert from 'node:assert/strict'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, test } from 'node:test'

import {
  COMMAND_WHITELIST,
  courseIdFor,
  distillAtlasCorpus,
  extractCommands,
  extractHeadings,
  extractSections,
  extractTerms,
  courseLabelFor
} from '../../scripts/atlas/distill-atlas.mjs'

let fixtureDir

beforeEach(async () => {
  fixtureDir = await mkdtemp(join(tmpdir(), 'atlas-distill-'))
})

afterEach(async () => {
  await rm(fixtureDir, { recursive: true, force: true })
})

test('courseIdFor: first-level directory owns the doc, root md files are standalone', () => {
  assert.equal(courseIdFor('Docker运维课/a.md'), 'Docker运维课')
  assert.equal(courseIdFor('安装Nginx.md'), 'standalone')
  assert.equal(courseLabelFor('standalone'), '独立专题')
})

test('extractCommands: whitelist filtering, sudo attribution and fence boundaries', () => {
  const body = [
    '正文里出现 docker 不算数',
    '```bash',
    'docker ps',
    'sudo systemctl restart nginx',
    'nonsensecommand --flag',
    '$ curl -I localhost',
    '```',
    '```',
    'cat /etc/hosts',
    '```'
  ].join('\n')
  const commands = extractCommands(body)
  const names = commands.map(item => item.cmd)
  assert.ok(names.includes('docker'))
  assert.ok(names.includes('systemctl'), 'sudo prefix should attribute to the real command')
  assert.ok(names.includes('curl'))
  assert.ok(names.includes('cat'))
  assert.ok(!names.includes('nonsensecommand'), 'non-whitelisted tokens must be dropped')
  assert.ok(names.includes('nginx') === false, 'object of restart is not a command')
})

test('extractCommands: unclosed fence runs to EOF (lenient parse) and result is capped', () => {
  const unclosed = '```bash\ndocker ps\ndocker images\n'
  const commands = extractCommands(unclosed)
  assert.deepEqual(commands, [{ cmd: 'docker', count: 2 }])
  const many = ['```sh', ...[...COMMAND_WHITELIST].map(cmd => `${cmd} x`), '```'].join('\n')
  assert.ok(extractCommands(many).length <= 8)
})

test('extractHeadings: level 1-3 only, capped at 8', () => {
  const body = [
    '# 主标题',
    '## 章节',
    '### 小节',
    '#### 四级不算',
    '没有空格#不是标题',
    '## 另一章'
  ].join('\n')
  const headings = extractHeadings(body)
  assert.equal(headings.length, 4)
  assert.deepEqual(headings[0], { level: 1, text: '主标题' })
  assert.equal(headings[2].level, 3)
})

test('distillAtlasCorpus: aggregates courses, documents and totals deterministically', async () => {
  await mkdir(join(fixtureDir, 'Docker运维课'), { recursive: true })
  await writeFile(join(fixtureDir, 'Docker运维课', 'b-容器命令.md'), '# 容器命令\n\n## run\n\n```bash\ndocker run nginx\n```\n', 'utf8')
  await writeFile(join(fixtureDir, 'Docker运维课', 'a-镜像管理.md'), '# 镜像管理\n\n```bash\ndocker images\n```\n', 'utf8')
  await writeFile(join(fixtureDir, '独立笔记.md'), '# 独立笔记\n\n正文\n', 'utf8')

  const snapshot = await distillAtlasCorpus(fixtureDir)
  assert.equal(snapshot.totals.documents, 3)
  assert.equal(snapshot.totals.courses, 2)
  assert.equal(snapshot.totals.codeBlocks, 2)

  const docker = snapshot.courses.find(course => course.id === 'Docker运维课')
  assert.equal(docker.documentCount, 2)
  assert.deepEqual(docker.topCommands, [{ cmd: 'docker', count: 2 }])

  // 文档按路径排序、id 稳定：a-镜像管理.md 在 b-容器命令.md 之前
  assert.equal(snapshot.documents[0].title, '镜像管理')
  assert.equal(snapshot.documents[0].id, 'd001')
  assert.equal(snapshot.documents[2].courseId, 'standalone')

  const again = await distillAtlasCorpus(fixtureDir)
  assert.deepEqual(snapshot.documents.map(doc => doc.id), again.documents.map(doc => doc.id))
})

test('distillAtlasCorpus: missing corpus directory fails with a clear message', async () => {
  await assert.rejects(
    () => distillAtlasCorpus(join(fixtureDir, '不存在')),
    /语料库目录不存在/
  )
})

test('extractSections: heading + prose excerpt, code fences excluded, capped at 12', () => {
  const body = [
    '# 容器命令',
    '',
    '容器是进程隔离技术。',
    '',
    '```bash',
    'docker run nginx',
    '```',
    '',
    '## 镜像分层',
    '',
    '镜像由只读层叠放而成，[参考](https://example.com/doc)。',
    '',
    '## 网络模式',
    '',
    'bridge 是默认网络。'
  ].join('\n')
  const sections = extractSections(body)
  assert.equal(sections.length, 3)
  assert.deepEqual(sections[0], { level: 1, text: '容器命令', excerpt: '容器是进程隔离技术。' })
  assert.ok(sections[1].excerpt.includes('镜像由只读层叠放而成'))
  assert.ok(!sections[1].excerpt.includes('https://'), 'links must be stripped from excerpts')
  assert.ok(!sections[1].excerpt.includes('docker run'), 'code fence content must not leak into excerpts')

  const manyHeadings = Array.from({ length: 20 }, (_, i) => `## 第${i}节\n\n内容${i}。`).join('\n')
  assert.ok(extractSections(manyHeadings).length <= 12)
})

test('extractTerms: chinese bigrams + latin words, stopwords filtered, sorted by frequency', () => {
  const body = [
    '# GPU 性能调优',
    '',
    'GPU 性能是推理系统的关键。性能不行就要调优 GPU。',
    '',
    '```bash',
    'nvidia-smi',
    '```',
    '',
    'vLLM 是推理框架。我们可以通过 vLLM 提升性能。'
  ].join('\n')
  const terms = extractTerms(body)
  const names = terms.map(item => item.term)
  assert.ok(names.includes('性能'), 'frequent CJK bigram should rank')
  assert.ok(names.includes('vllm'), 'latin words lowercased')
  assert.ok(!names.includes('nvidia-smi'), 'code fence content is not indexed')
  assert.ok(!names.includes('我们可以'), 'stopwords dropped')
  assert.ok(names.includes('gpu'))
  // 频次排序：性能出现 4 次（标题 1 + 正文 3），gpu 出现 2 次
  assert.equal(terms.find(item => item.term === '性能').count, 4)
  assert.ok(terms.length <= 12)
})

test('distillAtlasCorpus: real corpus snapshot is healthy (documents exist)', async () => {
  const realRoot = new URL('../../knowledge/reference/ops-knowledge-rag', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
  const snapshot = await distillAtlasCorpus(realRoot)
  assert.ok(snapshot.totals.documents >= 50, `expected the ops corpus, got ${snapshot.totals.documents}`)
  assert.ok(snapshot.topCommands.length > 0)
  assert.ok(snapshot.courses.some(course => course.id === 'Docker运维课'))
  assert.ok(snapshot.documents.every(doc => Array.isArray(doc.sections) && Array.isArray(doc.terms)), 'scholar fields must exist on every doc')
  assert.ok(snapshot.documents.some(doc => doc.sections.some(section => section.excerpt.length > 0)), 'excerpts must not all be empty')
})
