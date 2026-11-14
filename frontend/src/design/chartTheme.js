/**
 * 图表主题：全站 ECharts 共用一套语义色与轴 / 网格 / tooltip 样式。
 *
 * 取值全部来自 CSS 令牌（variables.css 的 --ds-chart-*），因此亮暗主题切换自动跟随；
 * 语义色最多 5 个（accent / cyan / success / warning / danger），禁止彩虹配色。
 */
import { resolvedTheme } from '../theme.js'

const FALLBACK = {
  dark: {
    colors: ['#2496ed', '#7ad7f5', '#3fb950', '#d29922', '#f85149'],
    grid: 'rgba(255, 255, 255, .06)',
    axis: 'rgba(255, 255, 255, .10)',
    text: '#92a6b5',
    tooltipBg: '#1B212A',
    tooltipBorder: 'rgba(255, 255, 255, .10)',
    areaOpacity: 0.14
  },
  light: {
    colors: ['#0e5f92', '#2b8fb8', '#176b30', '#8a5a00', '#cf222e'],
    grid: 'rgba(31, 35, 40, .08)',
    axis: 'rgba(31, 35, 40, .12)',
    text: '#57606a',
    tooltipBg: '#ffffff',
    tooltipBorder: 'rgba(31, 35, 40, .18)',
    areaOpacity: 0.10
  }
}

function readToken(css, name, fallback) {
  return css.getPropertyValue(name).trim() || fallback
}

/** 从挂载节点读取当前主题的令牌；未挂载时退回 :root。 */
function tokens(root) {
  const base = FALLBACK[resolvedTheme.value === 'light' ? 'light' : 'dark']
  const css = root ? getComputedStyle(root) : getComputedStyle(document.documentElement)
  return {
    colors: [
      readToken(css, '--ds-chart-1', base.colors[0]),
      readToken(css, '--ds-chart-2', base.colors[1]),
      readToken(css, '--ds-chart-3', base.colors[2]),
      readToken(css, '--ds-chart-4', base.colors[3]),
      readToken(css, '--ds-chart-5', base.colors[4])
    ],
    grid: readToken(css, '--ds-chart-grid', base.grid),
    axis: readToken(css, '--ds-chart-axis', base.axis),
    text: readToken(css, '--ds-chart-text', base.text),
    tooltipBg: readToken(css, '--ds-chart-tooltip-bg', base.tooltipBg),
    tooltipBorder: readToken(css, '--ds-chart-tooltip-border', base.tooltipBorder),
    areaOpacity: Number(readToken(css, '--ds-chart-area-opacity', String(base.areaOpacity))) || base.areaOpacity
  }
}

/** 最多 5 色的语义调色板（按序列顺序取用，超出循环）。 */
export function chartPalette(root) {
  return tokens(root).colors
}

export function chartTextStyle(root, size = 11) {
  return { color: tokens(root).text, fontSize: size, fontFamily: 'var(--ds-font-cn)' }
}

/** 类目轴（xAxis）：无轴线、无刻度，仅保留文字。 */
export function chartCategoryAxis(root, { labels = [], formatter } = {}) {
  const t = tokens(root)
  return {
    type: 'category',
    data: labels,
    boundaryGap: false,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: t.text, margin: 14, formatter }
  }
}

/** 数值轴（yAxis）：hairline 虚线网格，数值缩写（k / M）。 */
export function chartValueAxis(root, { maximum, formatter } = {}) {
  const t = tokens(root)
  return {
    type: 'value',
    min: 0,
    max: maximum,
    axisLabel: {
      color: t.text,
      formatter: formatter || (value => value >= 1000000 ? `${value / 1000000}M` : value >= 1000 ? `${value / 1000}k` : value)
    },
    splitLine: { lineStyle: { color: t.grid, type: 'dashed' } }
  }
}

/** tooltip：overlay 表面 + hairline 描边，数值缺省显示「未上报」。 */
export function chartTooltip(root, unit = '', valueFormatter) {
  const t = tokens(root)
  return {
    trigger: 'axis',
    renderMode: 'richText',
    confine: true,
    backgroundColor: t.tooltipBg,
    borderColor: t.tooltipBorder,
    textStyle: { color: resolvedTheme.value === 'light' ? '#1f2329' : '#e8f2f7', fontSize: 12 },
    valueFormatter: valueFormatter || (value => value == null ? '未上报' : `${value}${unit ? ` ${unit}` : ''}`)
  }
}
