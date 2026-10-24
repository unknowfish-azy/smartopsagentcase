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
  // 2026-10-18：按「深空底 + 单色霓虹」参考，绿色终端审美整体切换为 --smart-* 令牌。
  // 旧绿色十六进制 / 绿色发光 rgba 一律不允许残留。
  const greenLeftovers = [
    '#03140b', '#0c2414', '#07180e', '#10261d', '#0b1a14',
    '#a6ff82', '#d8ffd7', '#b8d6bd', '#a7c9ad', '#c6f0ce', '#e8ffe9',
    'rgba(115, 255, 125', 'rgba(166, 255, 130', 'rgba(139, 207, 180', 'rgba(177, 232, 202'
  ]
  for (const leftover of greenLeftovers) {
    assert.ok(!statisticsView.includes(leftover), `InspectorStatisticsView still contains ${leftover}`)
    assert.ok(!summaryView.includes(leftover), `InspectorSummary still contains ${leftover}`)
  }
  assert.match(statisticsView, /\.page\s*\{[^}]*background:\s*var\(--smart-surface\)/)
  assert.match(statisticsView, /\.grid p strong\s*\{[^}]*color:\s*var\(--smart-primary-strong\)/)
  assert.match(statisticsView, /\.grid p strong\s*\{[^}]*font-family:\s*var\(--font-mono\)/)
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
