// 运维知识蒸馏器：扫描 knowledge/reference/ops-knowledge-rag 语料库，
// 把 markdown 课程资料蒸馏成结构化快照（课程 → 文档 → 标题/命令/体量），
// 供前端「知识蒸馏图谱」页面（/atlas）做可视化。
//
// 设计原则（与 knowledge/export-catalog.mjs 一致）：
// - 蒸馏结果带 generatedAt 与 schemaVersion，页面如实展示快照时间，不冒充实时数据
// - 蒸馏是确定性的：同一语料两次蒸馏输出完全一致（文件按路径排序、id 稳定）
// - 命令提取用白名单而非正则猜测，宁可漏提也不产生垃圾 token
import { readdir, readFile, stat } from 'node:fs/promises'
import { join, relative, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

export const SCHEMA_VERSION = 1

/** 命令白名单：只统计运维语料里真实出现的命令，避免把普通单词当成命令。 */
export const COMMAND_WHITELIST = Object.freeze(new Set([
  // 容器与编排
  'docker', 'docker-compose', 'kubectl', 'podman', 'crictl', 'ctr', 'nerdctl', 'helm', 'containerd', 'dockerd',
  // 服务与系统
  'systemctl', 'journalctl', 'service', 'timedatectl', 'hostnamectl', 'localectl', 'systemd-analyze',
  // 常用工具
  'nginx', 'mysql', 'mysqld', 'redis-cli', 'git', 'curl', 'wget', 'tar', 'zip', 'unzip', 'ssh', 'scp', 'ansible',
  // 包管理
  'apt', 'apt-get', 'yum', 'dnf', 'rpm', 'pip', 'pip3', 'npm', 'node', 'python', 'python3', 'conda',
  // 性能与 AI Infra
  'top', 'free', 'df', 'du', 'ps', 'vmstat', 'iostat', 'lscpu', 'nvidia-smi', 'nvcc', 'torchrun', 'vllm', 'nsys', 'ncu',
  // 文本与文件
  'cat', 'less', 'vi', 'vim', 'find', 'grep', 'awk', 'sed', 'ls', 'mkdir', 'rm', 'cp', 'mv', 'touch', 'head', 'tail', 'wc', 'chmod', 'chown', 'ln', 'stat',
  // 网络与存储
  'ip', 'ifconfig', 'netstat', 'ss', 'ping', 'firewall-cmd', 'iptables', 'mount', 'umount', 'fdisk', 'lsblk', 'mkfs', 'lsof', 'dmesg', 'lsmod', 'modprobe',
  // SELinux 与用户
  'getenforce', 'setenforce', 'semanage', 'useradd', 'userdel', 'passwd', 'sudo'
]))

/** 课程目录 → 展示名（语料库目录名偏机械，图谱上用课名）。 */
const COURSE_LABELS = Object.freeze({
  '云原生公开课_分章md': '云原生公开课',
  'AI Infra训练营二期_分课': 'AI Infra 训练营',
  'Docker运维课': 'Docker 运维课',
  'RH教材': 'RH 教材'
})

const ROOT_COURSE_ID = 'standalone'
const ROOT_COURSE_LABEL = '独立专题'
const MAX_HEADINGS_PER_DOC = 8
const MAX_COMMANDS_PER_DOC = 8
const MAX_TOP_COMMANDS = 24
const MAX_SECTIONS_PER_DOC = 12
const MAX_SECTION_EXCERPT = 160
const MAX_TERMS_PER_DOC = 12

/** 检索停用词：中文高频虚词 bigram 与英文常见功能词，不作为检索关键词。 */
export const STOP_TERMS = Object.freeze(new Set([
  '一个', '一些', '什么', '我们', '你们', '他们', '这个', '那个', '这些', '那些',
  '可以', '应该', '需要', '使用', '通过', '如果', '但是', '然后', '因此', '所以',
  '进行', '以及', '或者', '例如', '注意', '问题', '内容', '时候', '如何', '为什么',
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'your', 'are', 'not',
  'http', 'https', 'com', 'www', 'org', 'png', 'jpg', 'img', 'src', 'alt'
]))

/** 课程归属：语料库一级目录；根目录散文件归入「独立专题」。兼容正反斜杠。 */
export function courseIdFor(relativePath) {
  const first = relativePath.replace(/[\\/]+/g, '/').split('/')[0]
  return first.endsWith('.md') ? ROOT_COURSE_ID : first
}

export function courseLabelFor(courseId) {
  if (courseId === ROOT_COURSE_ID) return ROOT_COURSE_LABEL
  return COURSE_LABELS[courseId] ?? courseId
}

/** 从 fenced code block 里提取白名单命令（sudo X 记到 X 头上）。 */
export function extractCommands(body) {
  const counts = new Map()
  let inFence = false
  for (const rawLine of body.split('\n')) {
    const fence = rawLine.trim().startsWith('```')
    if (fence) { inFence = !inFence; continue }
    if (!inFence) continue
    const match = /^\s*(?:sudo\s+)?(?:\$|PS>)?\s*([a-z][a-z0-9._-]*)/i.exec(rawLine)
    if (!match) continue
    let cmd = match[1].toLowerCase()
    // docker compose / docker-comepose 两种写法都归到 docker-compose 语义下太武断，只归并 sudo
    if (cmd === 'sudo') continue
    if (!COMMAND_WHITELIST.has(cmd)) continue
    counts.set(cmd, (counts.get(cmd) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, MAX_COMMANDS_PER_DOC)
    .map(([cmd, count]) => ({ cmd, count }))
}

/** 提取 1-3 级标题作为文档主题骨架。 */
export function extractHeadings(body) {
  const headings = []
  for (const line of body.split('\n')) {
    const match = /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line)
    if (!match) continue
    headings.push({ level: match[1].length, text: match[2].trim() })
    if (headings.length >= MAX_HEADINGS_PER_DOC) break
  }
  return headings
}

/**
 * 提取章节结构（供科研助手做引用溯源）：标题 + 该节正文节选。
 * 与 extractHeadings 不同，这里允许更多章节数，且每节带 excerpt（正文去语法后的前 N 字符）。
 * 节选只取文字，不包含代码块内容与 markdown 语法符号。
 */
export function extractSections(body) {
  const sections = []
  let current = null
  let inFence = false
  for (const rawLine of body.split('\n')) {
    if (rawLine.trim().startsWith('```')) { inFence = !inFence; continue }
    if (inFence) continue
    const heading = !inFence && /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(rawLine)
    if (heading) {
      if (current) finalizeSection(sections, current)
      if (sections.length < MAX_SECTIONS_PER_DOC) {
        current = { level: heading[1].length, text: heading[2].trim(), _lines: [] }
      } else {
        current = null
      }
      continue
    }
    if (current) current._lines.push(rawLine)
  }
  if (current) finalizeSection(sections, current)
  return sections
}

function finalizeSection(sections, section) {
  const text = section._lines
    .join(' ')
    .replace(/[#>*`_\-\[\]()!|]/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  sections.push({ level: section.level, text: section.text, excerpt: text.slice(0, MAX_SECTION_EXCERPT) })
}

/** 提取文档关键词（供检索匹配）：中文 bigram + 英文单词，停用词过滤，频次排序。 */
export function extractTerms(body) {
  const counts = new Map()
  let inFence = false
  const plain = []
  for (const rawLine of body.split('\n')) {
    if (rawLine.trim().startsWith('```')) { inFence = !inFence; continue }
    if (!inFence) plain.push(rawLine)
  }
  const text = plain.join('\n').toLowerCase()
  for (const match of text.matchAll(/[a-z][a-z0-9-]{2,}/g)) {
    addTerm(counts, match[0])
  }
  for (const match of text.matchAll(/[\u4e00-\u9fa5]{2,}/g)) {
    const run = match[0]
    addTerm(counts, run)
    for (let i = 0; i + 2 <= run.length; i += 1) addTerm(counts, run.slice(i, i + 2))
  }
  return [...counts.entries()]
    .filter(([term]) => !STOP_TERMS.has(term) && term.length >= 2)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, MAX_TERMS_PER_DOC)
    .map(([term, count]) => ({ term, count }))
}

function addTerm(counts, term) {
  if (STOP_TERMS.has(term)) return
  counts.set(term, (counts.get(term) ?? 0) + 1)
}

function extractTitle(body, fileName) {
  const match = /^#\s+(.+?)\s*$/m.exec(body)
  return match ? match[1].trim() : fileName.replace(/\.md$/i, '')
}

async function listMarkdownFiles(rootDir) {
  const files = []
  async function walk(dir) {
    const entries = await readdir(dir, { withFileTypes: true })
    for (const entry of entries) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) await walk(full)
      else if (entry.isFile() && entry.name.toLowerCase().endsWith('.md')) files.push(full)
    }
  }
  await walk(rootDir)
  files.sort()
  return files
}

/**
 * 蒸馏语料库：读入全部 markdown，产出课程/文档/命令三级结构化模型。
 * @param {string} rootDir 语料库根目录
 * @returns {Promise<object>} 快照对象（含 schemaVersion / generatedAt / totals / courses / documents / topCommands）
 */
export async function distillAtlasCorpus(rootDir) {
  const info = await stat(rootDir).catch(() => null)
  if (!info?.isDirectory()) {
    throw new Error(`语料库目录不存在：${rootDir}`)
  }
  const files = await listMarkdownFiles(rootDir)
  const courses = new Map()
  const documents = []
  const commandTotals = new Map()

  for (let index = 0; index < files.length; index += 1) {
    const fullPath = files[index]
    const rel = relative(rootDir, fullPath)
    const body = await readFile(fullPath, 'utf8')
    const courseId = courseIdFor(rel)
    const headings = extractHeadings(body)
    const commands = extractCommands(body)
    const sections = extractSections(body)
    const document = {
      id: `d${String(index + 1).padStart(3, '0')}`,
      courseId,
      title: extractTitle(body, fullPath.split(sep).pop() ?? ''),
      path: rel.split(sep).join('/'),
      chars: body.length,
      headingsCount: headings.length,
      codeBlocks: Math.floor((body.match(/^\s*```/gm) ?? []).length / 2),
      commands,
      headings,
      sections,
      terms: extractTerms(body)
    }
    documents.push(document)
    if (!courses.has(courseId)) {
      courses.set(courseId, { id: courseId, label: courseLabelFor(courseId), documentCount: 0, chars: 0, headingsCount: 0, codeBlocks: 0, topCommands: [] })
    }
    const course = courses.get(courseId)
    course.documentCount += 1
    course.chars += document.chars
    course.headingsCount += document.headingsCount
    course.codeBlocks += document.codeBlocks
    for (const { cmd, count } of commands) {
      commandTotals.set(cmd, (commandTotals.get(cmd) ?? 0) + count)
    }
  }

  for (const course of courses.values()) {
    const perCourse = new Map()
    for (const doc of documents) {
      if (doc.courseId !== course.id) continue
      for (const { cmd, count } of doc.commands) {
        perCourse.set(cmd, (perCourse.get(cmd) ?? 0) + count)
      }
    }
    course.topCommands = [...perCourse.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 6)
      .map(([cmd, count]) => ({ cmd, count }))
  }

  const courseList = [...courses.values()].sort((a, b) => b.chars - a.chars)
  return {
    schemaVersion: SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    sourceRoot: 'knowledge/reference/ops-knowledge-rag',
    totals: {
      courses: courseList.length,
      documents: documents.length,
      headings: documents.reduce((sum, doc) => sum + doc.headingsCount, 0),
      codeBlocks: documents.reduce((sum, doc) => sum + doc.codeBlocks, 0),
      chars: documents.reduce((sum, doc) => sum + doc.chars, 0)
    },
    courses: courseList,
    documents,
    topCommands: [...commandTotals.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, MAX_TOP_COMMANDS)
      .map(([cmd, count]) => ({ cmd, count }))
  }
}

const outputPath = new URL('../../frontend/src/views/atlas/atlasDistilled.json', import.meta.url)

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const rootDir = process.argv[2] ?? new URL('../../knowledge/reference/ops-knowledge-rag', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
  const snapshot = await distillAtlasCorpus(rootDir)
  const { writeFile, mkdir } = await import('node:fs/promises')
  await mkdir(new URL('.', outputPath), { recursive: true })
  await writeFile(outputPath, JSON.stringify(snapshot, null, 2) + '\n', 'utf8')
  console.log(`Atlas snapshot distilled: ${snapshot.totals.documents} docs / ${snapshot.totals.courses} courses -> frontend/src/views/atlas/atlasDistilled.json`)
}
