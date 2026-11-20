import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getAiRuntimeStatus, startAiRuntime, stopAiRuntime } from '../api/runtime'
import type { AiRuntimeStatus, AiRuntimeState } from '../api/runtime'

const POLL_IDLE = 15000
const POLL_ACTIVE = 1500
const OPERATION_DEADLINE = 220000

/**
 * 本地 AI 能力链的启停状态机。
 *
 * - 空闲 15s 轮询，操作中 1.5s 轮询；页面隐藏时暂停请求
 * - 仅当后端返回 controllable=true（ADMIN + 本地开关）时展示操作入口
 */
export function useAiRuntime() {
  const status = ref<AiRuntimeStatus | null>(null)
  const pending = ref<'' | 'start' | 'stop'>('')
  const error = ref('')
  let timer: ReturnType<typeof setTimeout> | null = null
  let disposed = false

  const state = computed<AiRuntimeState>(() => {
    if (pending.value) return pending.value === 'start' ? 'starting' : 'stopping'
    return status.value?.state || 'unknown'
  })
  const controllable = computed(() => !!status.value?.controllable)
  const transitioning = computed(() => state.value === 'starting' || state.value === 'stopping')
  const canStart = computed(() => controllable.value && !pending.value
    && ['stopped', 'partial', 'error', 'unknown', 'disabled'].includes(state.value))
  const canStop = computed(() => controllable.value && !pending.value
    && ['running', 'partial'].includes(state.value))

  async function refresh() {
    try {
      const payload: any = await getAiRuntimeStatus()
      status.value = payload?.data ?? payload
      error.value = ''
    } catch (failure: any) {
      error.value = failure?.response?.data?.message || failure?.message || '运行时状态获取失败'
    }
  }

  function schedule(delay = POLL_IDLE) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      if (disposed) return
      if (status.value?.controlEnabled === false) return
      if (!document.hidden) await refresh()
      schedule(transitioning.value ? POLL_ACTIVE : POLL_IDLE)
    }, delay)
  }

  async function run(action: 'start' | 'stop') {
    if (pending.value || !controllable.value) return
    pending.value = action
    error.value = ''
    try {
      await (action === 'start' ? startAiRuntime() : stopAiRuntime())
      const deadline = Date.now() + OPERATION_DEADLINE
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 1200))
        await refresh()
        if (!transitioning.value) break
      }
    } catch (failure: any) {
      error.value = failure?.response?.data?.message || failure?.message || '操作失败'
    } finally {
      pending.value = ''
      schedule()
    }
  }

  onMounted(async () => {
    await refresh()
    if (status.value?.controlEnabled === false) return
    schedule()
  })

  onBeforeUnmount(() => {
    disposed = true
    if (timer) clearTimeout(timer)
  })

  return {
    status, state, pending, error, controllable, transitioning, canStart, canStop,
    refresh, start: () => run('start'), stop: () => run('stop'),
  }
}
