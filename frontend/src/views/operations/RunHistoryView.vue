<template>
  <section class="run-history" aria-labelledby="run-history-title">
    <header class="page-heading">
      <div>
        <p class="eyebrow">RUN HISTORY / 运行证据</p>
        <h1 id="run-history-title">运行记录中心</h1>
        <p>查询远程运维工具的命令、退出码、标准输出、错误输出与证据链。</p>
      </div>
      <button class="button" type="button" :disabled="loading" @click="loadRuns(page.page)">{{ loading ? '刷新中…' : '刷新记录' }}</button>
    </header>
    <RunHistoryFilters v-model:filters="filters" :form-error="formError" @search="loadRuns(1)" @reset="resetFilters" />
    <div v-if="error" class="state error" role="alert">
      <strong>运行记录暂时无法加载</strong>
      <p>{{ error }}</p>
      <button class="button" @click="loadRuns(page.page)">重新加载</button>
    </div>
    <div v-else class="layout">
      <RunHistoryListPanel
        :page="page"
        :loading="loading"
        :guide-mode="guideMode"
        :selected-id="selectedId"
        :total-pages="totalPages"
        @select="selectRun"
        @load="loadRuns"
      />
      <RunHistoryDetailPanel
        :detail="detail"
        :detail-loading="detailLoading"
        :detail-error="detailError"
        :selected-id="selectedId"
        :candidate="candidate"
        :candidate-error="candidateError"
        :candidate-loading="candidateLoading"
        :copied="copied"
        :copy-failed="copyFailed"
        @retry="loadDetail(selectedId)"
        @create-candidate="createCandidate"
        @copy-trace="copyTrace"
      />
    </div>
  </section>
</template>

<script setup>
import { useRunHistory } from '../../composables/useRunHistory.js'
import RunHistoryFilters from '../../components/operations/RunHistoryFilters.vue'
import RunHistoryListPanel from '../../components/operations/RunHistoryListPanel.vue'
import RunHistoryDetailPanel from '../../components/operations/RunHistoryDetailPanel.vue'

const {
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
} = useRunHistory()
</script>

<style scoped>
.run-history {
  max-width: 1480px;
  margin: 0 auto;
  padding: 12px 0 40px;
  color: var(--smart-text);
  font-family: var(--font-cn);
  padding-bottom: 0;
  /* 抵消 .content 底部留白，避免整页多出一条滚动条 */
  margin-bottom: -96px;
}
.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}
.eyebrow {
  margin: 0 0 9px;
  color: var(--smart-primary-strong);
  font: 10px var(--font-mono);
  letter-spacing: .14em;
}
.page-heading h1 {
  margin: 0;
  font-size: clamp(28px,3vw,38px);
  font-weight: 560;
}
.page-heading p:not(.eyebrow) {
  color: var(--smart-muted);
  font-size: 13px;
}
.button {
  min-height: 40px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  padding: 8px 15px;
  color: var(--smart-text);
  background: var(--smart-surface);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
button:disabled {
  opacity: .45;
  cursor: wait;
}
button:focus-visible {
  outline: 2px solid var(--smart-primary-strong);
  outline-offset: 3px;
}
.layout {
  display: grid;
  grid-template-columns: minmax(300px,380px) minmax(0,1fr);
  gap: 18px;
  height: clamp(420px, calc(100dvh - 420px), 880px);
  align-items: stretch;
}
.state {
  padding: 60px 24px;
  text-align: center;
  color: var(--smart-muted);
  font-size: 12px;
}
.state strong {
  color: var(--smart-text);
  font-size: 14px;
}
.error {
  border: 1px solid var(--smart-border);
  border-left: 3px solid #e06b72;
  border-radius: 12px;
  background: var(--smart-surface);
}
@media(max-width:1180px) {
  .layout {
    grid-template-columns: 320px minmax(0,1fr);
  }
}
@media(max-width:800px) {
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .layout {
    grid-template-columns: 1fr;
    height: auto;
  }
}
/* 两栏独立滚动：执行记录与 Trace 详情各自一条滚动条，面板头吸顶 */
@media (max-width: 1023px) {
  .run-history {
    margin-bottom: -64px;
  }
}
@media (max-width: 767px) {
  .run-history {
    margin-bottom: -56px;
  }
}
</style>
