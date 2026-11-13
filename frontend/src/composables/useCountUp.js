/**
 * S-KPI 指标连增：把真实拉取到的数字从 0 平滑滚动到目标值，仅首次进视图播一次。
 *
 * 注意（G6）：这里只是「数字展示的滚动动画」，目标值就是后端返回的真实值，
 * 不伪造、不补数。reduced-motion / 降级模式下直接显示最终值。
 * 通过 font-variant-numeric: tabular-nums 保证宽度恒定，避免数字跳动造成 CLS。
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const reduceQuery = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)')
  : null

/** easeOutCubic：起快停稳，符合读数「先快后慢」的直觉。 */
function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3) }

/**
 * @param {import('vue').Ref<number|null>} targetRef 目标值的 ref（可能为 null/非数字）
 * @param {object} [options]
 * @param {number} [options.duration=900] 滚动时长 ms
 * @param {number} [options.decimals=0] 小数位数
 * @returns {import('vue').Ref<string>} 展示用字符串
 */
export function useCountUp(targetRef, { duration = 900, decimals = 0 } = {}) {
  const display = ref(format(targetRef.value, decimals))
  let rafId = null
  let started = false

  function format(value, dec) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
    return Number(value).toFixed(dec)
  }

  function animate(to) {
    if (reduceQuery?.matches) {
      display.value = format(to, decimals)
      return
    }
    const from = 0
    const start = performance.now()
    const tick = now => {
      const elapsed = now - start
      const t = Math.min(elapsed / duration, 1)
      const current = from + (to - from) * easeOutCubic(t)
      display.value = format(current, decimals)
      if (t < 1) {
        rafId = requestAnimationFrame(tick)
      } else {
        display.value = format(to, decimals)
      }
    }
    rafId = requestAnimationFrame(tick)
  }

  function stop() {
    if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
  }

  // KPI 数据是异步拉取的：挂载时多为 null/「—」，Number(null)===0 不能当作有效起点。
  // 首个有效数字到达时才滚一次；之后的刷新直接更新，不反复滚动。
  function toNumber(value) {
    if (value === null || value === undefined || value === '') return null
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }

  function startIfNeeded() {
    if (started) return
    const val = toNumber(targetRef.value)
    if (val === null) {
      display.value = format(targetRef.value, decimals)
      return
    }
    started = true
    animate(val)
  }

  onMounted(startIfNeeded)

  watch(targetRef, value => {
    if (!started) { startIfNeeded(); return }
    stop()
    display.value = format(value, decimals)
  })

  onBeforeUnmount(stop)

  return { display, stop }
}
