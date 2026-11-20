import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

// Z0-03：目录级 rAF 守卫。
//
// 只扫"空间知识场 + 洞察"两个目录，不扫全仓：
// 仓库里已有 20 处存量 requestAnimationFrame（MainLayout / useCountUp /
// SpiderCrawler / MilestoneRain / LoginView / DataCenterTwin3D 等），
// 全仓守卫会立刻误伤，等于没有守卫。
//
// 规则：这两个目录里的动画必须走 src/visual/motionScheduler.js。

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.resolve(HERE, '../src')

const GUARDED_DIRS = [
  path.join(SRC, 'views', 'knowledge', 'space'),
  path.join(SRC, 'views', 'insights'),
]

const SOURCE_EXT = new Set(['.vue', '.js', '.mjs', '.ts'])

function walk(dir) {
  const files = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) files.push(...walk(full))
    else if (SOURCE_EXT.has(path.extname(entry.name))) files.push(full)
  }
  return files
}

function offenders() {
  const hits = []
  for (const dir of GUARDED_DIRS) {
    if (!fs.existsSync(dir)) continue
    for (const file of walk(dir)) {
      const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/)
      lines.forEach((line, index) => {
        // 允许在注释/文档字符串里提到它（如 EvidenceBed 的说明），不算违规
        const code = line.trim()
        if (code.startsWith('//') || code.startsWith('*') || code.startsWith('/*')) return
        if (code.includes('requestAnimationFrame')) {
          hits.push(`${path.relative(SRC, file)}:${index + 1}`)
        }
      })
    }
  }
  return hits
}

test('受守卫目录存在（否则守卫失效）', () => {
  for (const dir of GUARDED_DIRS) {
    assert.ok(fs.existsSync(dir), `受守卫目录不存在：${path.relative(SRC, dir)}`)
  }
})

test('空间知识场与洞察视图不得自己开 requestAnimationFrame', () => {
  const hits = offenders()
  assert.deepEqual(
    hits,
    [],
    `以下位置自行开启了 rAF，请改用 src/visual/motionScheduler.js：\n${hits.join('\n')}`,
  )
})
