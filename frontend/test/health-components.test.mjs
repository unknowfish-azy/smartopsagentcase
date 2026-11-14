import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const root = new URL('../', import.meta.url)
const source = path => readFile(new URL(path, root), 'utf8')

// ============================================================
// ConclusionBar.vue — 结论带组件契约
// ============================================================

test('ConclusionBar: 根 section 是 role="status" + aria-live="polite"（结论带是状态区）', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  assert.match(src, /role="status"/)
  assert.match(src, /aria-live="polite"/)
  // :aria-label 绑定到 verdictText — 屏幕阅读器直接读结论
  assert.match(src, /:aria-label="verdictText"/)
})

test('ConclusionBar: 过期提示条 v-if="stale" 且带 role="alert"（强制 AT 播报）', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  // stale-bar 只在 stale=true 时渲染
  assert.match(src, /<div v-if="stale" class="hc-stale-bar" role="alert">/)
  assert.match(src, /结果可能已过期/)
})

test('ConclusionBar: 计数 pill 是 <button> 可点击跳组（键盘可达）', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  // 不是 <div v-for>，必须是 <button type="button">
  assert.match(src, /<button\s+v-for="c in countItems"/)
  assert.match(src, /type="button"/)
  // 点击 emit jump-group
  assert.match(src, /@click="\$emit\('jump-group', c\.key\)"/)
  // 有 title 提示跳组功能
  assert.match(src, /:title="`跳到「\$\{c\.label\}」`"/)
})

test('ConclusionBar: countItems 四桶颜色严格映射语义色（DESIGN §6 硬约束）', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  assert.match(src, /action.*color: 'var\(--ds-semantic-danger\)'/)
  assert.match(src, /config.*color: 'var\(--ds-semantic-warning\)'/)
  // unknown 必须是中性色（不能用绿或红 — DESIGN §3）
  assert.match(src, /unknown.*color: 'var\(--ds-semantic-neutral\)'/)
  assert.match(src, /pass.*color: 'var\(--ds-semantic-success\)'/)
})

test('ConclusionBar: dotColor 优先级 = verdictText 优先级（action > config > unknown > pass）', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  // 必须是 if/else 链，顺序正确
  assert.match(src, /if \(props\.counts\.action\) return 'var\(--ds-semantic-danger\)'/)
  assert.match(src, /if \(props\.counts\.config\) return 'var\(--ds-semantic-warning\)'/)
  assert.match(src, /if \(props\.counts\.unknown\) return 'var\(--ds-semantic-neutral\)'/)
  assert.match(src, /if \(totalChecks\.value\) return 'var\(--ds-semantic-success\)'/)
})

test('ConclusionBar: 重新检查按钮 loading 时禁用 + 文案变 "检查中…"', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  assert.match(src, /:disabled="loading"/)
  assert.match(src, /@click="\$emit\('recheck'\)"/)
  assert.match(src, /\{\{ loading \? `检查中… \$\{loadingProgress \|\| ''\}` : '重新检查' \}\}/)
})

test('ConclusionBar: checkedAt=null 时 checkedAtText 兜底为 "—"（不兜底成当前时间）', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  // fmtTime 在 checkedAtMs=0 时返回 null，|| '—' 兜底
  assert.match(src, /fmtTime\(checkedAtMs\.value\) \|\| '—'/)
})

test('ConclusionBar: ringStyle 用 conic-gradient 且引用 ringColorToken', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  assert.match(src, /conic-gradient\(/)
  // ringColorToken 以 -- 开头时包 var()
  assert.match(src, /ringColorToken\.startsWith\('--'\)/)
})

test('ConclusionBar: 响应式断点 — 768px 下隐藏 freshText，879px 下隐藏 grow', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  assert.match(src, /@media \(max-width: 767px\)/)
  assert.match(src, /\.hc-fresh-text \{ display: none; \}/)
  assert.match(src, /@media \(max-width: 879px\)/)
})

test('ConclusionBar: 定义 6 个 props 且类型正确', async () => {
  const src = await source('src/components/diagnostics/ConclusionBar.vue')
  assert.match(src, /counts:\s*\{\s*type:\s*Object/)
  assert.match(src, /checkedAt:\s*\{\s*type:\s*\[Number, String, Date\]/)
  assert.match(src, /now:\s*\{\s*type:\s*Number/)
  assert.match(src, /stale:\s*\{\s*type:\s*Boolean/)
  assert.match(src, /loading:\s*\{\s*type:\s*Boolean/)
  assert.match(src, /loadingProgress:\s*\{\s*type:\s*String/)
})

// ============================================================
// EvidenceBanner.vue — 证据完整性横幅组件契约
// ============================================================

test('EvidenceBanner: 根 div v-if="flags.length"（无标志位时整块不渲染）', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  assert.match(src, /<div v-if="flags\.length" class="hc-evidence"/)
  // role="note" — 辅助说明语义，不抢焦点
  assert.match(src, /role="note"/)
})

test('EvidenceBanner: 必须包含 "证据不完整" 标题文案', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  assert.match(src, /<b>证据不完整<\/b>/)
  assert.match(src, /下面的结论基于不完整的数据/)
})

test('EvidenceBanner: 每个 flag 渲染成 <li>（语义列表，不是 div）', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  assert.match(src, /<ul class="hc-evidence-list">/)
  assert.match(src, /<li v-for="f in flags" :key="f\.key">/)
})

test('EvidenceBanner: li 里 text 和 why 分开，why 用独立 class（中性色）', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  // 格式：{{ f.text }} — <span class="hc-evidence-why">{{ f.why }}</span>
  assert.match(src, /\{\{ f\.text \}\} — <span class="hc-evidence-why">\{\{ f\.why \}\}<\/span>/)
  // why 必须用中性色（不能用琥珀/红 — 让用户聚焦在问题本身而非威胁感）
  const css = src.match(/<style scoped>[\s\S]*<\/style>/)?.[0] || ''
  assert.match(css, /\.hc-evidence-why\s*\{[\s\S]*color:\s*var\(--ds-semantic-neutral\)/)
})

test('EvidenceBanner: 横幅整体用琥珀色（warning）不是红色（danger）', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  const css = src.match(/<style scoped>[\s\S]*<\/style>/)?.[0] || ''
  // 背景和边框都基于 warning
  assert.match(css, /--ds-semantic-warning/)
  // 不能出现 danger
  assert.doesNotMatch(css, /--ds-semantic-danger/)
})

test('EvidenceBanner: 四个后端标志位 props 全部存在且为 Boolean 默认 false', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  for (const key of ['permissionDenied', 'dataMissing', 'unverified', 'truncated']) {
    assert.match(src, new RegExp(`${key}:\\s*\\{\\s*type:\\s*Boolean,\\s*default:\\s*false`),
      `${key} prop 缺失或类型错误`)
  }
})

test('EvidenceBanner: flags computed 把四个 props 透传给 bannerFlags()', async () => {
  const src = await source('src/components/diagnostics/EvidenceBanner.vue')
  for (const key of ['permissionDenied', 'dataMissing', 'unverified', 'truncated']) {
    assert.match(src, new RegExp(`${key}:\\s*props\\.${key}`),
      `props.${key} 没有透传给 bannerFlags()`)
  }
})

// ============================================================
// 跨组件一致性：两者都引用纯函数模块，不在组件内重复定义逻辑
// ============================================================

test('ConclusionBar & EvidenceBanner 都 import 共享纯函数模块（不 inline 逻辑）', async () => {
  const bar = await source('src/components/diagnostics/ConclusionBar.vue')
  const ebanner = await source('src/components/diagnostics/EvidenceBanner.vue')

  assert.match(bar, /from '\.\/conclusionState\.js'/)
  assert.match(ebanner, /from '\.\/evidenceBanner\.js'/)

  // ConclusionBar 不能再直接 import FIVE_MINUTES_MS（已收敛到 freshInfo）
  assert.doesNotMatch(bar, /import.*FIVE_MINUTES_MS/)

  // EvidenceBanner 不能再有内联的 FLAG_MAP
  assert.doesNotMatch(ebanner, /const FLAG_MAP/)
})
