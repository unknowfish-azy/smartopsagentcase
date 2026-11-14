/* useSpaceCamera.js
 *
 * 纯 composable，只封装 k/tx/ty 三个相机数 + 应用到 world DOM 的方法。
 * 外部提供 stageEl 与 worldEl；内部维护响应式状态、锚点缩放、缓动飞跳、Esc 三级回退。
 * 不 import 任何 Vue 渲染逻辑（模板/JSX），不依赖全局状态。
 */

import { ref, computed } from 'vue'

const K_MIN = 0.16
const K_MAX = 2.2
const L0_MAX = 0.42
const L1_MAX = 1.05

export function useSpaceCamera (worldRect, stageRect) {
  const k  = ref(0.28)
  const tx = ref(0)
  const ty = ref(0)
  const kMin = K_MIN
  const kMax = K_MAX

  const lod = computed(() => k.value < L0_MAX ? 0 : k.value < L1_MAX ? 1 : 2)

  function clamp (v, a, b) { return v < a ? a : v > b ? b : v }

  function apply (worldEl, { k: nk = k.value, tx: ntx = tx.value, ty: nty = ty.value } = {}) {
    k.value = clamp(nk, K_MIN, K_MAX)
    tx.value = ntx
    ty.value = nty
    if (worldEl) {
      worldEl.style.transform = `translate3d(${tx.value}px,${ty.value}px,0) scale(${k.value})`
      worldEl.dataset.lod = String(lod.value)
    }
  }

  /** 锚点缩放：mx/my 是 stage 内的像素坐标。缩放后指针下的世界点保持不动。 */
  function zoomAt (mx, my, factor, worldEl) {
    const k2 = clamp(k.value * factor, K_MIN, K_MAX)
    tx.value = mx - (mx - tx.value) * (k2 / k.value)
    ty.value = my - (my - ty.value) * (k2 / k.value)
    k.value = k2
    if (worldEl) apply(worldEl)
  }

  /** 把某个世界坐标 wx,wy 对齐到视口中心，scale=tk。 */
  function centerOn (wx, wy, tk, worldEl, stageEl) {
    const st = stageEl?.getBoundingClientRect?.() || { width: 1200, height: 800 }
    const targetK = clamp(tk, K_MIN, K_MAX)
    k.value = targetK
    tx.value = st.width / 2 - wx * targetK
    ty.value = st.height / 2 - wy * targetK
    if (worldEl) apply(worldEl)
  }

  /** 飞跳到某个域（给定 world 矩形），落在 L1 中值附近。 */
  function flyTo (zone, worldEl, stageEl) {
    const st = stageEl?.getBoundingClientRect?.() || { width: 1200, height: 800 }
    const targetK = clamp(Math.min(st.width / zone.w, st.height / zone.h) * 1.4, 0.55, 1.05)
    const cx = zone.x + zone.w / 2, cy = zone.y + zone.h / 2
    k.value = targetK
    tx.value = st.width / 2 - cx * targetK
    ty.value = st.height / 2 - cy * targetK
    if (worldEl) apply(worldEl)
  }

  /** 总览：世界在 stage 内等比 fit。 */
  function fitOverview (worldEl, stageEl, { w = 3200, h = 2000 } = {}) {
    const st = stageEl?.getBoundingClientRect?.() || { width: 1200, height: 800 }
    const tk = Math.min(st.width / w, st.height / h) * 0.94
    k.value = tk
    tx.value = (st.width - w * tk) / 2
    ty.value = (st.height - h * tk) / 2
    if (worldEl) apply(worldEl)
  }

  /** 把某个世界坐标对到视口中心 */
  function worldPointOfViewportCenter (stageEl) {
    const st = stageEl?.getBoundingClientRect?.() || { width: 1200, height: 800 }
    return { x: (-tx.value + st.width / 2) / k.value, y: (-ty.value + st.height / 2) / k.value }
  }

  /** 视口覆盖的世界矩形（迷你地图用）。 */
  function viewportWorldRect (stageEl) {
    const st = stageEl?.getBoundingClientRect?.() || { width: 1200, height: 800 }
    return {
      x: -tx.value / k.value,
      y: -ty.value / k.value,
      w: st.width / k.value,
      h: st.height / k.value,
    }
  }

  return {
    k, tx, ty, kMin, kMax, lod,
    apply, zoomAt, centerOn, flyTo, fitOverview,
    worldPointOfViewportCenter, viewportWorldRect,
  }
}
