/**
 * 表现层 / 工具层分级与自适应视觉预算（P0）。
 *
 * 设计契约：
 *  - 表现层（登录、品牌介绍页）允许宇宙星空与果冻玻璃；
 *  - 工具层（用户控制台、管理端）保持企业级简约高密度扁平，不跑 WebGL/玻璃。
 *
 * 本模块只做「判定与建议」，不直接改全局状态，避免破坏 visualMode.js 既有
 * localStorage 契约与浏览器测试对默认档位的假设。
 */
import { BREAKPOINTS, isNarrowViewport } from './breakpoints.js'

export const SURFACES = Object.freeze(['expressive', 'tool'])

/** 登录与品牌页走表现层，其余一律工具层。 */
export function resolveSurface(path = '') {
  const normalized = String(path || '').toLowerCase()
  if (normalized === '/login' || normalized.startsWith('/login?') || normalized === '/' || normalized.startsWith('/intro')) {
    return 'expressive'
  }
  return 'tool'
}

export function isExpressiveSurface(path) {
  return resolveSurface(path) === 'expressive'
}

/** 浏览器是否支持 backdrop-filter（果冻效果的能力门禁）。 */
export function supportsBackdropFilter() {
  if (typeof globalThis.CSS === 'undefined' || typeof CSS.supports !== 'function') return false
  return CSS.supports('backdrop-filter', 'blur(1px)') || CSS.supports('-webkit-backdrop-filter', 'blur(1px)')
}

function prefersReducedMotion() {
  return typeof globalThis.matchMedia === 'function' && globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function lowEndDevice() {
  const nav = globalThis.navigator || {}
  const memory = typeof nav.deviceMemory === 'number' ? nav.deviceMemory : 8
  const cores = typeof nav.hardwareConcurrency === 'number' ? nav.hardwareConcurrency : 8
  const dpr = globalThis.devicePixelRatio || 1
  return memory <= 4 || cores <= 4 || (dpr > 2 && memory <= 8)
}

/**
 * 自适应视觉预算：返回建议档位与判定理由。
 * 仅在运行时建议，不写 localStorage；调用方（visualMode.js）决定如何应用。
 * 理由可直接展示在界面上，作为「可解释的 AI 原生界面」证据。
 */
export function visualBudgetRecommendation() {
  const reasons = []
  if (prefersReducedMotion()) {
    return { mode: 'reduced-motion', reasons: ['系统偏好：减少动态'], tier: 'static' }
  }
  if (lowEndDevice()) reasons.push('设备算力/内存较低')
  if (isNarrowViewport()) reasons.push(`视口 < ${BREAKPOINTS.md}px`)
  if (reasons.length >= 2) return { mode: 'reduced-motion', reasons, tier: 'static' }
  if (reasons.length === 1) return { mode: 'lightweight', reasons, tier: 'light' }
  return { mode: 'balanced', reasons: ['设备与视口资源充足'], tier: 'full' }
}

/** 工具层默认不加载任何装饰性逐帧层。 */
export function shouldMountDecorativeLayers(surface, tier = 'full') {
  return surface === 'expressive' && tier !== 'static'
}

export default { SURFACES, resolveSurface, isExpressiveSurface, supportsBackdropFilter, visualBudgetRecommendation, shouldMountDecorativeLayers }
