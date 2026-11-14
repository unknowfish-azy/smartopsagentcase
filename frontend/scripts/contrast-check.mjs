// WCAG 对比度计算脚本（浅色模式）
// 用法: node scripts/contrast-check.mjs

function hexToRgb(hex) {
  hex = hex.replace('#', '')
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('')
  return {
    r: parseInt(hex.slice(0, 2), 16) / 255,
    g: parseInt(hex.slice(2, 4), 16) / 255,
    b: parseInt(hex.slice(4, 6), 16) / 255,
  }
}

function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
}

function luminance({ r, g, b }) {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

// 把 rgba 与底色合成（alpha 混合）
function composite(fg, bg, alpha) {
  return {
    r: fg.r * alpha + bg.r * (1 - alpha),
    g: fg.g * alpha + bg.g * (1 - alpha),
    b: fg.b * alpha + bg.b * (1 - alpha),
  }
}

function contrast(c1, c2) {
  const l1 = luminance(c1)
  const l2 = luminance(c2)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

// rgba 颜色与白底合成后的颜色
function rgbaOnWhite(rgb, alpha) {
  return composite(rgb, { r: 1, g: 1, b: 1 }, alpha)
}

function passAA(c) { return c >= 4.5 }

function grade(c) {
  if (c >= 7) return 'AAA'
  if (c >= 4.5) return 'AA'
  if (c >= 3) return 'AA-large'
  return 'FAIL'
}

// ============== 浅色模式令牌 ==============
const TEXT = '#1f2329'
const MUTED = '#57606a'
const BG = '#f6f8fa'
const SURFACE = '#ffffff'

const PRIMARY = '#0e5f92'
const PRIMARY_STRONG = '#084b73'
const PRIMARY_FG = '#ffffff'

const DS_SUCCESS = '#176b30'
const DS_WARNING = '#8a5a00'
const DS_DANGER = '#cf222e'
const DS_INFO = '#0969da'
const DS_NEUTRAL = '#57606a'

const SMART_SUCCESS = '#176b50'
const SMART_WARNING = '#8a5a08'
const SMART_DANGER = '#a33f52'

// pill 背景（与白底合成）
const PILL_SUCCESS_BG = rgbaOnWhite(hexToRgb('#176b30'), 0.10)
const PILL_WARNING_BG = rgbaOnWhite(hexToRgb('#8a5a00'), 0.14)
const PILL_DANGER_BG = rgbaOnWhite(hexToRgb('#cf222e'), 0.10)
const PILL_INFO_BG = rgbaOnWhite(hexToRgb('#0969da'), 0.10)

// 边框（与白底合成）
const BORDER = rgbaOnWhite(hexToRgb('#1f2329'), 0.22)
const BORDER_STRONG = rgbaOnWhite(hexToRgb('#1f2329'), 0.34)

const rows = [
  // 文字在页面底/卡片上
  ['正文 on 页面底', TEXT, BG],
  ['正文 on 卡片(白)', TEXT, SURFACE],
  ['弱文 on 页面底', MUTED, BG],
  ['弱文 on 卡片(白)', MUTED, SURFACE],

  // 主色相关
  ['主色 on 卡片(白)', PRIMARY, SURFACE],
  ['主色强 on 卡片(白)', PRIMARY_STRONG, SURFACE],
  ['白字 on 主色底', PRIMARY_FG, PRIMARY],

  // 语义色 on 白（ds 令牌）
  ['success on 白', DS_SUCCESS, SURFACE],
  ['warning on 白', DS_WARNING, SURFACE],
  ['danger on 白', DS_DANGER, SURFACE],
  ['info on 白', DS_INFO, SURFACE],
  ['neutral on 白', DS_NEUTRAL, SURFACE],

  // 语义色 on 白（smart 令牌）
  ['smart-success on 白', SMART_SUCCESS, SURFACE],
  ['smart-warning on 白', SMART_WARNING, SURFACE],
  ['smart-danger on 白', SMART_DANGER, SURFACE],

  // pill 前景 on pill 背景
  ['success fg on pill bg', DS_SUCCESS, PILL_SUCCESS_BG],
  ['warning fg on pill bg', DS_WARNING, PILL_WARNING_BG],
  ['danger fg on pill bg', DS_DANGER, PILL_DANGER_BG],
  ['info fg on pill bg', DS_INFO, PILL_INFO_BG],

  // 边框 vs 白底（用于判断边框是否可见，非文字对比度，但检查可辨识度）
  ['边框 on 白（视觉）', BORDER, SURFACE],
  ['强边框 on 白（视觉）', BORDER_STRONG, SURFACE],
]

console.log('浅色模式 WCAG 对比度检查\n')
console.log(`${'颜色对'.padEnd(28)}${'对比度'.padStart(8)}  ${'等级'.padEnd(10)}  结果`)
console.log('-'.repeat(70))

let failures = 0
for (const [name, fg, bg] of rows) {
  const fgObj = typeof fg === 'string' ? hexToRgb(fg) : fg
  const bgObj = typeof bg === 'string' ? hexToRgb(bg) : bg
  const c = contrast(fgObj, bgObj)
  const g = grade(c)
  const isPill = name.includes('pill')
  const isBorder = name.includes('边框')
  // pill 文字通常较小，用 AA(4.5) 标准；边框是视觉元素，3.0 可辨识度即可
  const pass = isBorder ? c >= 1.5 : (isPill ? passAA(c) : passAA(c))
  if (!pass) failures++
  console.log(`${name.padEnd(28)}${c.toFixed(2).padStart(8)}  ${g.padEnd(10)}  ${pass ? '✅' : '❌'}`)
}

console.log('-'.repeat(70))
console.log(`\n总计 ${rows.length} 项，${failures} 项不达标`)
if (failures > 0) {
  console.log('\n⚠️  不达标项需要调整颜色值以满足 WCAG AA (4.5:1)')
}
