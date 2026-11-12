/**
 * 统一响应式断点（P0）。
 *
 * CSS 自定义属性无法用于 @media 条件，因此断点以 JS 常量 + CSS 注释约定的形式
 * 作为唯一事实来源。新增媒体查询时请复用这里的数值，不要再引入 600/650/700/1050
 * 这类散落断点。
 */
export const BREAKPOINTS = Object.freeze({
  xs: 375,
  sm: 768,
  md: 1024,
  lg: 1440,
  xl: 1920,
})

/** 供 JS 侧做布局判断（例如是否在窄屏隐藏装饰层）。 */
export function isNarrowViewport(width = globalThis.innerWidth ?? BREAKPOINTS.lg) {
  return width < BREAKPOINTS.md
}

export default BREAKPOINTS
