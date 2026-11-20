import { onBeforeUnmount, onMounted, watch } from 'vue'

/**
 * 侧栏 Dock 磁吸放大：指针到图标中心的距离驱动缩放（升余弦钟形），
 * 邻居随距离自然衰减；只在启用时跑 rAF，指针离开后回弹并停帧。
 *
 * @param {import('vue').Ref<HTMLElement | null>} railRef 承载图标轨的容器
 * @param {{
 *   radius?: number,
 *   peak?: number,
 *   easing?: number,
 *   selector?: string,
 *   enabled?: () => boolean
 * }} options
 */
export function useDockMagnification(railRef, options = {}) {
  const {
    radius = 96,
    peak = 1.26,
    easing = 0.24,
    selector = '[data-dock-item]',
    enabled = () => true
  } = options

  const entries = new Map()
  let frame = 0
  let measureFrame = 0
  let pointerInside = false
  let observer = null
  let boundRoot = null
  let stopWatch = null

  function systemReduced() {
    return typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  function active() {
    return Boolean(railRef.value) && enabled() && !systemReduced()
  }

  function reset(el) {
    el.style.setProperty('--dock-scale', '1')
  }

  function collect(root = railRef.value) {
    entries.clear()
    if (!root) return
    root.querySelectorAll(selector).forEach(el => {
      reset(el)
      entries.set(el, { rect: el.getBoundingClientRect(), value: 1, target: 1 })
    })
  }

  function measure() {
    entries.forEach((entry, el) => { entry.rect = el.getBoundingClientRect() })
  }

  function scheduleMeasure() {
    if (measureFrame) return
    measureFrame = window.requestAnimationFrame(() => {
      measureFrame = 0
      measure()
    })
  }

  function paint() {
    frame = 0
    let moving = false
    entries.forEach((entry, el) => {
      entry.value += (entry.target - entry.value) * easing
      if (Math.abs(entry.target - entry.value) < 0.002) {
        entry.value = entry.target
      } else {
        moving = true
      }
      el.style.setProperty('--dock-scale', entry.value.toFixed(3))
    })
    if (moving) frame = window.requestAnimationFrame(paint)
  }

  function ensureFrame() {
    if (frame) return
    frame = window.requestAnimationFrame(paint)
  }

  function aim(event) {
    entries.forEach(entry => {
      const centerX = entry.rect.left + entry.rect.width / 2
      const centerY = entry.rect.top + entry.rect.height / 2
      const distance = Math.hypot(event.clientX - centerX, event.clientY - centerY)
      const t = Math.min(distance / radius, 1)
      entry.target = 1 + (peak - 1) * ((1 + Math.cos(Math.PI * t)) / 2)
    })
  }

  function onPointerMove(event) {
    if (!active()) return
    if (!pointerInside) {
      pointerInside = true
      measure()
    }
    aim(event)
    ensureFrame()
  }

  function release() {
    pointerInside = false
    if (!active()) {
      entries.forEach((entry, el) => {
        entry.value = 1
        entry.target = 1
        reset(el)
      })
      return
    }
    entries.forEach(entry => { entry.target = 1 })
    ensureFrame()
  }

  /** 收起/展开切换或视觉档变化后重建缓存（元素可能刚渲染）。 */
  function refresh() {
    pointerInside = false
    collect(boundRoot)
  }

  function unbind() {
    if (!boundRoot) return
    boundRoot.removeEventListener('pointermove', onPointerMove)
    boundRoot.removeEventListener('pointerleave', release)
    boundRoot.removeEventListener('scroll', scheduleMeasure)
    observer?.disconnect()
    observer = null
    boundRoot = null
    entries.clear()
  }

  /** 容器可能随 v-if 挂载/卸载（如顶栏工具坞），跟着 ref 重新绑定。 */
  function bind(root) {
    if (boundRoot === root) return
    unbind()
    if (!root) return
    boundRoot = root
    collect(root)
    root.addEventListener('pointermove', onPointerMove)
    root.addEventListener('pointerleave', release)
    root.addEventListener('scroll', scheduleMeasure, { passive: true })
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(scheduleMeasure)
      observer.observe(root)
    }
  }

  onMounted(() => {
    stopWatch = watch(railRef, root => bind(root), { immediate: true })
  })

  onBeforeUnmount(() => {
    stopWatch?.()
    stopWatch = null
    unbind()
    if (frame) window.cancelAnimationFrame(frame)
    if (measureFrame) window.cancelAnimationFrame(measureFrame)
    frame = 0
    measureFrame = 0
  })

  return { refresh }
}
