import { onBeforeUnmount, ref, watch } from 'vue'
import { currentSession } from '../security/session.js'

/**
 * 管理端只读资源加载。
 *
 * 首次加载与新查询清空数据并显示加载态；`load({ preserve: true })` 表示同一
 * 查询的普通刷新，保留旧数据、标注“更新中”和最近成功时间，避免列表闪成空白。
 * 请求版本号丢弃过期响应；会话身份变化时立即清空缓存，防止把上一账号的数据
 * 留在界面。
 */
export function useAdminResource(fetcher) {
  const data = ref(null)
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref('')
  const updatedAt = ref(null)
  const loaded = ref(false)
  let version = 0

  async function load({ preserve = false } = {}) {
    const requestVersion = ++version
    const firstLoad = !loaded.value
    loading.value = !preserve || firstLoad
    refreshing.value = preserve && !firstLoad
    error.value = ''
    if (!preserve) data.value = null
    try {
      const result = await fetcher()
      if (requestVersion !== version) return
      data.value = result
      loaded.value = true
      updatedAt.value = new Date()
    } catch (failure) {
      if (requestVersion === version) error.value = failure.message || '加载失败，请重试'
    } finally {
      if (requestVersion === version) {
        loading.value = false
        refreshing.value = false
      }
    }
  }

  function clear() {
    version += 1
    data.value = null
    loaded.value = false
    loading.value = false
    refreshing.value = false
    error.value = ''
    updatedAt.value = null
  }

  watch(() => currentSession.value?.id, (next, previous) => {
    if (previous !== undefined && next !== previous) clear()
  })
  onBeforeUnmount(() => { version += 1 })

  return { data, loading, refreshing, error, updatedAt, load, clear }
}

export function formatAdminTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false })
}
