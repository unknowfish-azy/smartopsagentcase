/**
 * 小节互引抽取：为「小节图谱」提供原文级证据。
 *
 * 只认原文显式写出的引用措辞（上一节 / 下一节 / 前述），不做语义推断：
 * - prev：小节正文提到「上一节/上节/前一节」；
 * - next：提到「下一节/下节/后一节」；
 * - back：提到「前述/前面提到/前面介绍/如上所述」。
 *
 * 输出按语料相对路径归档（不按文档 id），前端用快照 doc.path 关联，
 * 这样无需重蒸 atlasDistilled.json，也不会改变研究卡组卷的文档集合。
 *
 * 用法：node scripts/atlas/section-refs.mjs [语料根目录]
 */
import { readdir, readFile, writeFile, mkdir, stat } from 'node:fs/promises'
import { join, relative, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const SCHEMA_VERSION = 1

export const REFERENCE_PATTERNS = Object.freeze([
  { kind: 'prev', pattern: /上一节|上节|前一节/g },
  { kind: 'next', pattern: /下一节|下节|后一节/g },
  { kind: 'back', pattern: /前述|前面提到|前面介绍|如上所述/g }
])

/** 逐节切分：以 heading 行为界，返回 [{ level, text, body }]。 */
export function splitSections(body) {
  const lines = body.split('\n')
  const sections = []
  let current = null
  for (const line of lines) {
    const heading = /^(#{1,6})\s+(.+?)\s*$/.exec(line)
    if (heading) {
      if (current) sections.push(current)
      current = { level: heading[1].length, text: heading[2].trim(), body: [] }
      continue
    }
    if (current) current.body.push(line)
  }
  if (current) sections.push(current)
  return sections.map(section => ({ level: section.level, text: section.text, body: section.body.join('\n') }))
}

/** 抽取单篇文档里带互引的小节；无互引返回空数组。 */
export function extractSectionRefs(body) {
  const refs = []
  let inFence = false
  const withoutCode = body.split('\n').map((line) => {
    if (line.trim().startsWith('```')) { inFence = !inFence; return '' }
    return inFence ? '' : line
  }).join('\n')
  for (const section of splitSections(withoutCode)) {
    const kinds = REFERENCE_PATTERNS
      .filter(item => item.pattern.test(section.body))
      .map(item => item.kind)
    if (!kinds.length) continue
    refs.push({ text: section.text, kinds })
  }
  return refs
}

async function listMarkdownFiles(rootDir) {
  const files = []
  async function walk(dir) {
    const entries = await readdir(dir, { withFileTypes: true })
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) await walk(full)
      else if (entry.name.toLowerCase().endsWith('.md')) files.push(full)
    }
  }
  await walk(rootDir)
  return files.sort()
}

export async function buildSectionRefs(rootDir) {
  const info = await stat(rootDir).catch(() => null)
  if (!info?.isDirectory()) throw new Error(`语料库目录不存在：${rootDir}`)
  const files = await listMarkdownFiles(rootDir)
  const docs = []
  for (const file of files) {
    const body = await readFile(file, 'utf8')
    const sections = extractSectionRefs(body)
    if (!sections.length) continue
    docs.push({ path: relative(rootDir, file).split(sep).join('/'), sections })
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    sourceRoot: 'knowledge/reference/ops-knowledge-rag',
    docs
  }
}

const outputPath = new URL('../../frontend/src/views/atlas/atlasSectionRefs.json', import.meta.url)

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const rootDir = process.argv[2] ??
    fileURLToPath(new URL('../../knowledge/reference/ops-knowledge-rag', import.meta.url))
  const snapshot = await buildSectionRefs(rootDir)
  await mkdir(new URL('.', outputPath), { recursive: true })
  await writeFile(outputPath, JSON.stringify(snapshot, null, 2) + '\n', 'utf8')
  const refCount = snapshot.docs.reduce((sum, doc) => sum + doc.sections.length, 0)
  console.log(`Section refs distilled: ${snapshot.docs.length} docs / ${refCount} sections -> frontend/src/views/atlas/atlasSectionRefs.json`)
}
