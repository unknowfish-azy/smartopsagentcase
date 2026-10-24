const FIVE_MINUTES_MS = 5 * 60 * 1000
import { computed, ref } from 'vue'

const CATEGORY_LABELS = Object.freeze({
  CONFIGURATION: '\u914d\u7f6e\u4e0d\u5b8c\u6574',
  AUTHORIZATION: '\u65e0\u6743\u8bbf\u95ee',
  TIMEOUT: '\u68c0\u67e5\u8d85\u65f6',
  NETWORK: '\u7f51\u7edc\u8fde\u63a5\u5931\u8d25',
  ASSERTION: '\u65ad\u8a00\u4e0d\u5339\u914d',
  NOT_CHECKED: '\u524d\u7f6e\u68c0\u67e5\u672a\u6267\u884c',
  UNKNOWN: '\u68c0\u67e5\u5931\u8d25'
})
const KNOWN_CATEGORIES = new Set(Object.keys(CATEGORY_LABELS).filter(category => category !== 'UNKNOWN'))

export { FIVE_MINUTES_MS }

export function isFreshCheck(checkedAt, now = Date.now()) {
  const timestamp = typeof checkedAt === 'number' ? checkedAt : Date.parse(checkedAt || '')
  return Number.isFinite(timestamp) && timestamp <= now && now - timestamp <= FIVE_MINUTES_MS
}

export function healthStateLabel(status, stale = false) {
  if (stale) return '\u7ed3\u679c\u53ef\u80fd\u5df2\u8fc7\u671f'
  return ({
    HEALTHY: '\u6b63\u5e38',
    UNHEALTHY: '\u5f02\u5e38',
    UNCONFIGURED: '\u672a\u914d\u7f6e',
    FORBIDDEN: '\u65e0\u6743\u9650',
    NOT_CHECKED: '\u672a\u68c0\u67e5'
  })[status] || status || '\u672a\u68c0\u67e5'
}

export function normalizeDiagnosticFailure(error) {
  const candidate = error?.errorCategory || error?.category || error?.response?.data?.errorCategory || error?.response?.data?.data?.errorCategory
  const normalizedCandidate = typeof candidate === 'string' ? candidate.toUpperCase() : ''
  let category = KNOWN_CATEGORIES.has(normalizedCandidate) ? normalizedCandidate : ''
  const status = Number(error?.status || error?.response?.status || error?.code)
  if (!category && [401, 403].includes(status)) category = 'AUTHORIZATION'
  if (!category && ['ECONNABORTED', 'ETIMEDOUT'].includes(error?.originalError?.code || error?.code)) category = 'TIMEOUT'
  const text = [error?.code, error?.message, error?.response?.data?.message].filter(Boolean).join(' ').toLowerCase()
  if (!category && /timeout|timed out|超时/.test(text)) category = 'TIMEOUT'
  if (!category && /assert|mismatch|断言/.test(text)) category = 'ASSERTION'
  if (!category && /forbidden|unauthori|permission|无权|权限/.test(text)) category = 'AUTHORIZATION'
  if (!category && /config|未配置|配置/.test(text)) category = 'CONFIGURATION'
  if (!category && /not.?checked|前置/.test(text)) category = 'NOT_CHECKED'
  if (!category) category = 'NETWORK'
  return { category, message: CATEGORY_LABELS[category] || CATEGORY_LABELS.UNKNOWN }
}

export function createDiagnosticState(fetchStatus, now) {
  const status = ref(null)
  const checkedAt = ref(null)
  const loading = ref(false)
  const error = ref('')
  const failed = ref(false)
  const stale = computed(() => Boolean(status.value) && (failed.value || !isFreshCheck(checkedAt.value, now.value)))
  async function load() {
    if (loading.value) return
    loading.value = true
    error.value = ''
    try {
      status.value = await fetchStatus()
      checkedAt.value = now.value
      failed.value = false
    } catch (failure) {
      failed.value = true
      error.value = `${normalizeDiagnosticFailure(failure).message}，请重试。`
    } finally { loading.value = false }
  }
  return { status, checkedAt, loading, error, stale, load }
}
