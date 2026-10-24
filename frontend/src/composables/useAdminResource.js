import { onBeforeUnmount, ref } from 'vue'

export function useAdminResource(fetcher) {
  const data = ref(null)
  const loading = ref(false)
  const error = ref('')
  let version = 0
  async function load() {
    const requestVersion = ++version
    loading.value = true
    error.value = ''
    data.value = null
    try {
      const result = await fetcher()
      if (requestVersion === version) data.value = result
    } catch (failure) {
      if (requestVersion === version) error.value = failure.message || '加载失败，请重试'
    } finally {
      if (requestVersion === version) loading.value = false
    }
  }
  onBeforeUnmount(() => { version += 1 })
  return { data, loading, error, load }
}

export function formatAdminTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false })
}
