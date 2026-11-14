/**
 * build-data.mjs —— 把真实知识库导出成空间视图用的数据文件
 *
 * 直接 import 项目 catalog（唯一的真相来源），不手抄、不猜字段。
 * 产物：space-data.js（`window.__KB__`，可用 <script> 加载，file:// 下也能跑）
 *
 * 用法：node build-data.mjs
 */
import { writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

/* 项目的 catalog 在本仓 frontend 下；用相对路径直接 import，保证与线上同一份数据 */
const CATALOG = join(HERE, '../../../frontend/src/views/knowledge/knowledgeCatalog.js')
const { knowledgeEntries, knowledgeDomains } = await import('file://' + CATALOG.replace(/\\/g, '/'))

/* 域的真实取值比 knowledgeDomains 多三个（缺口 A），这里显式补齐中文名，不静默合并 */
const EXTRA_DOMAINS = {
  network: { label: '网络基础', detail: 'OSI / TCP-IP / IPv4 / 路由 / 交换' },
  'web-lamp': { label: 'Linux Web / LAMP', detail: 'HTTP / 浏览器与服务端 / Apache' },
  'linux-services': { label: 'Linux 服务', detail: 'systemd / 监听 / 服务健康' }
}
const registered = new Map(knowledgeDomains.map(d => [d.id, d]))

const counts = new Map()
for (const e of knowledgeEntries) counts.set(e.domain, (counts.get(e.domain) || 0) + 1)

const domains = [...counts.keys()]
  .sort((a, b) => counts.get(b) - counts.get(a))
  .map(id => {
    const reg = registered.get(id)
    const extra = EXTRA_DOMAINS[id]
    return {
      id,
      label: reg?.label ?? extra?.label ?? id,
      detail: reg?.detail ?? extra?.detail ?? '',
      registered: Boolean(reg),
      n: counts.get(id)
    }
  })

const entries = knowledgeEntries.map((e, i) => ({
  i,
  id: e.id,
  d: e.domain,
  t: e.title ?? '(无标题)',
  ty: e.type ?? null,
  p: e.platform ?? null,
  sv: e.service ?? null,
  s: (e.summary ?? '').slice(0, 160)
}))

const payload = {
  generatedAt: new Date().toISOString(),
  source: 'frontend/src/views/knowledge/knowledgeCatalog.js',
  total: entries.length,
  domains,
  entries,
  stats: {
    domainCount: domains.length,
    registeredDomainCount: knowledgeDomains.length,
    missingType: entries.filter(e => !e.ty).length,
    missingPlatform: entries.filter(e => !e.p).length
  }
}

const out = join(HERE, 'space-data.js')
await writeFile(out, `window.__KB__ = ${JSON.stringify(payload)};\n`, 'utf8')
await writeFile(join(HERE, 'space-data.json'), JSON.stringify(payload, null, 1), 'utf8')

console.log(`entries=${payload.total}  domains=${payload.domains.length}  未登记域=${domains.filter(d => !d.registered).length}`)
console.log('missing type =', payload.stats.missingType, ' missing platform =', payload.stats.missingPlatform)
console.log('top domains:', domains.slice(0, 5).map(d => `${d.id}:${d.n}`).join('  '))
console.log('bytes:', (JSON.stringify(payload).length / 1024).toFixed(0) + ' KB')
