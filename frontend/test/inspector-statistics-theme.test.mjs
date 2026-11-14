import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const statisticsView = await readFile(new URL('../src/views/inspector/InspectorStatisticsView.vue', import.meta.url), 'utf8')
const summaryView = await readFile(new URL('../src/components/inspector/InspectorSummary.vue', import.meta.url), 'utf8')
const variables = await readFile(new URL('../src/assets/styles/variables.css', import.meta.url), 'utf8')

function luminance(hex) {
  const channels = hex.replace('#', '').match(/.{2}/g).map(value => parseInt(value, 16) / 255)
  const linear = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
}

function contrastRatio(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a)
  return (values[0] + 0.05) / (values[1] + 0.05)
}

const darkBlock = variables.match(/:root\s*\{([\s\S]*?)\n\}/)[1]
const lightBlock = variables.match(/\[data-theme='light'\]\s*\{([\s\S]*?)\n\}/)[1]
const pick = (block, name) => block.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))[1]

test('inspector statistics uses the single-accent token system, not a second green accent', () => {
  // 语义：单一 accent 令牌体系，不允许旧绿色十六进制 / 发光残留。
  // 2026-11-14 P1 图表化后页面根类名与「纯文字列表」结构已重写，
  // 断言从「旧类名 .page / .grid p strong」改为「令牌化背景 + 等宽数值 + 强调色令牌」，
  // 保留原本要守的设计意图，不再与具体实现细节耦合。
  const greenLeftovers = [
    '#03140b', '#0c2414', '#07180e', '#10261d', '#0b1a14',
    '#a6ff82', '#d8ffd7', '#b8d6bd', '#a7c9ad', '#c6f0ce', '#e8ffe9',
    'rgba(115, 255, 125', 'rgba(166, 255, 130', 'rgba(139, 207, 180', 'rgba(177, 232, 202'
  ]
  for (const leftover of greenLeftovers) {
    assert.ok(!statisticsView.includes(leftover), `InspectorStatisticsView still contains ${leftover}`)
    assert.ok(!summaryView.includes(leftover), `InspectorSummary still contains ${leftover}`)
  }
  assert.match(statisticsView, /background:\s*var\(--(?:smart|ds)-[a-z-]*surface/, '页面背景必须走主题令牌')
  assert.doesNotMatch(statisticsView, /background:\s*#[0-9a-fA-F]{6}/, '不得硬编码背景色')
  assert.match(statisticsView, /var\(--font-mono/, '数值需沿用等宽字体令牌')
  assert.match(statisticsView, /var\(--(?:smart|ds)[a-z-]*primary/, '强调色需走主题令牌')
  assert.match(summaryView, /\.summary strong\s*\{[^}]*color:\s*var\(--smart-primary-strong\)/)
})

test('both themes keep readable contrast on the token system', () => {
  // 继承旧测试的意图：可读对比度。改为从 variables.css 解析令牌实算，深浅都校验。
  for (const [label, block] of [['dark', darkBlock], ['light', lightBlock]]) {
    const text = pick(block, 'smart-text')
    const surface = pick(block, 'smart-surface')
    const accent = pick(block, 'smart-primary-strong')
    assert.ok(contrastRatio(text, surface) >= 4.5, `${label}: body text on surface must be >= 4.5:1`)
    assert.ok(contrastRatio(accent, surface) >= 3, `${label}: accent numbers on surface must be >= 3:1`)
  }
})
