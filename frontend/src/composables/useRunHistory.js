import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { createKnowledgeCandidateFromRun, getOperationRun, getOperationRuns } from '../api/operations.ts'
import { cleanRunQuery, normalizeDateTime, validateRunTimeRange } from '../components/operations/operationRunHistory.js'
import { findRunHistoryGuide, runPageWithGuides } from '../components/operations/runHistoryGuides.js'

export function useRunHistory() {
  const filters = ref({ traceId: '', toolId: '', status: '', startedFrom: '', startedTo: '' })
  const page = ref({ items: [], total: 0, page: 1, pageSize: 20 })
  const selectedId = ref(null)
  const detail = ref(null)
  const loading = ref(false)
  const detailLoading = ref(false)
  const error = ref('')
  const detailError = ref('')
  const copied = ref(false)
  const candidateLoading = ref(false)
  const candidate = ref(null)
  const candidateError = ref('')
  const guideMode = ref(false)
  const formError = ref('')
  const copyFailed = ref(false)
  let copyToken = 0
  let copyTimer
  let listToken = 0
  let detailToken = 0
  const totalPages = computed(() => Math.max(1, Math.ceil(page.value.total / page.value.pageSize)))
  const unwrap = response => response?.data ?? response

  async function loadRuns(targetPage = 1) {
    formError.value = Object.values(validateRunTimeRange(filters.value.startedFrom, filters.value.startedTo))[0] || ''
    if (formError.value) return
    const token = ++listToken
    ++detailToken
    detailError.value = ''
    detailLoading.value = false
    loading.value = true
    error.value = ''
    try {
      const query = cleanRunQuery({ ...filters.value, startedFrom: normalizeDateTime(filters.value.startedFrom), startedTo: normalizeDateTime(filters.value.startedTo), page: targetPage, pageSize: page.value.pageSize })
      const nextPage = runPageWithGuides(unwrap(await getOperationRuns(query)), query)
      if (token !== listToken) return
      page.value = nextPage
      guideMode.value = page.value.guideMode
      if (!page.value.items.some(item => item.id === selectedId.value)) { selectedId.value = page.value.items[0]?.id ?? null; detail.value = null; resetCopy(); candidate.value = null; candidateError.value = '' }
      if (selectedId.value) await loadDetail(selectedId.value)
    } catch (cause) { if (token === listToken) error.value = cause.message || '请检查后端服务和数据库连接。' } finally { if (token === listToken) loading.value = false }
  }

  async function loadDetail(id) {
    if (id == null) return
    const token = ++detailToken
    detailLoading.value = true
    detailError.value = ''
    try {
      const nextDetail = findRunHistoryGuide(id) || unwrap(await getOperationRun(id))
      if (token === detailToken) detail.value = nextDetail
    } catch (cause) {
      if (token === detailToken) { detailError.value = cause.message || '运行详情加载失败。'; detail.value = null }
    } finally {
      if (token === detailToken) detailLoading.value = false
    }
  }

  function selectRun(id) {
    if (id !== selectedId.value) {
      resetCopy()
      selectedId.value = id
      candidate.value = null
      candidateError.value = ''
      loadDetail(id)
    }
  }

  async function createCandidate() {
    if (!detail.value?.run?.id || detail.value.run.isGuide || candidateLoading.value) return
    candidateLoading.value = true
    candidateError.value = ''
    try {
      candidate.value = unwrap(await createKnowledgeCandidateFromRun(detail.value.run.id))
    } catch (cause) {
      candidate.value = null
      candidateError.value = cause.message || '请稍后重试，运行记录不会被修改。'
    } finally {
      candidateLoading.value = false
    }
  }

  function resetFilters() { filters.value = { traceId: '', toolId: '', status: '', startedFrom: '', startedTo: '' }; loadRuns(1) }

  function resetCopy() {
    ++copyToken
    window.clearTimeout(copyTimer)
    copied.value = false
    copyFailed.value = false
  }

  async function copyTrace(value) {
    resetCopy()
    const token = copyToken
    try {
      await navigator.clipboard.writeText(value)
      if (token !== copyToken) return
      copied.value = true
      copyTimer = window.setTimeout(resetCopy, 1400)
    } catch {
      if (token === copyToken) copyFailed.value = true
    }
  }

  onBeforeUnmount(() => { ++detailToken; ++listToken; resetCopy() })
  onMounted(() => loadRuns(1))

  return {
    filters,
    page,
    selectedId,
    detail,
    loading,
    detailLoading,
    error,
    detailError,
    copied,
    candidateLoading,
    candidate,
    candidateError,
    guideMode,
    formError,
    copyFailed,
    totalPages,
    loadRuns,
    loadDetail,
    selectRun,
    createCandidate,
    resetFilters,
    copyTrace
  }
}
