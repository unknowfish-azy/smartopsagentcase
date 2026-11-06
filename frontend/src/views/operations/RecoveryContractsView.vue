<template>
  <section class="recovery-view" aria-labelledby="recovery-title">
    <header class="page-heading">
      <div>
        <p class="eyebrow">RECOVERY CONTRACTS / 恢复契约</p>
        <h1 id="recovery-title">恢复契约中心</h1>
        <p>按恢复契约 v1 语义展示平台已登记的契约、回执、义务缺口与回放差分；四轴状态互不替代。</p>
      </div>
      <div class="mode-switch" role="tablist" aria-label="数据来源">
        <button
          v-for="item in modes"
          :key="item.key"
          type="button"
          class="mode-tab"
          :class="{ active: mode === item.key }"
          role="tab"
          :aria-selected="mode === item.key"
          @click="switchMode(item.key)"
        >{{ item.label }}</button>
      </div>
    </header>

    <!-- 真实数据模式 -->
    <template v-if="mode === 'live'">
      <div class="toolbar">
        <label class="filter">
          <span>运行 ID</span>
          <input v-model.trim="runIdInput" inputmode="numeric" placeholder="留空则列出全部" @keyup.enter="reload" />
        </label>
        <button type="button" class="primary" :disabled="loading" @click="reload">
          {{ loading ? '加载中…' : '刷新' }}
        </button>
        <span class="hint">数据来自平台已登记的恢复契约记录；本页不做三值判定。</span>
      </div>

      <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

      <div v-if="!loading && contracts.length === 0 && !error" class="empty-state" role="status">
        <strong>暂无已登记的恢复契约</strong>
        <p>
          平台只展示内部写入方（agent / 只读探针，经 <code>X-SmartOps-Internal-Token</code>）上报的契约与回执。
          当前没有任何记录，说明尚未有运行完成契约登记与核验；这里不会用样例数据填补空态。
        </p>
      </div>

      <div class="live-layout">
        <aside v-if="contracts.length" class="contract-list" aria-label="契约列表">
          <button
            v-for="item in contracts"
            :key="item.id"
            type="button"
            class="contract-item"
            :class="{ active: item.id === selectedId }"
            @click="select(item.id)"
          >
            <span class="item-title">{{ item.contractId }}</span>
            <span class="item-target">{{ item.targetId }}</span>
            <span class="item-meta">
              <span class="chip" :class="verdictTone(item.verdict)">{{ item.verdict || '未核验' }}</span>
              <span class="chip" :class="stateTone(item.receiptState)">{{ item.receiptState || 'NOT_ISSUED' }}</span>
            </span>
            <span class="item-time">运行 #{{ item.runId }} · {{ item.createdAt || '时间未记录' }}</span>
          </button>
        </aside>

        <div v-if="detailLoading" class="loading-block" role="status">正在加载契约详情…</div>
        <p v-else-if="detailError" class="error-banner" role="alert">{{ detailError }}</p>
        <div v-else-if="liveCase" class="cards">
          <ContractCard
            :contract="liveCase.contract"
            :claim="liveCase.claim"
            :receipt="liveCase.receipt"
            :action="liveCase.action"
            :inspection-passed="liveCase.inspection_passed"
            :authorization="liveCase.authorization"
            :source="liveCase.source"
          />
          <GapCard
            :obligations="liveCase.contract?.obligations ?? []"
            :obligation-results="liveCase.obligation_results"
            :probe-decision="liveCase.probe_decision"
            :budget="liveCase.contract?.budgets ?? null"
            :verdict="liveCase.verdict"
            :source="liveCase.source"
          />
          <ReplayCard
            :bundle="liveCase.replay_bundle"
            :replay="liveCase.replay"
            :baseline-results="liveCase.obligation_results"
            :source="liveCase.source"
          />
        </div>
      </div>
    </template>

    <!-- 演示样例模式：与真实数据明确隔离 -->
    <template v-else>
      <div class="case-switch" role="tablist" aria-label="样例切换">
        <button
          v-for="item in cases"
          :key="item.key"
          type="button"
          class="case-tab"
          :class="{ active: item.key === activeKey }"
          role="tab"
          :aria-selected="item.key === activeKey"
          @click="activeKey = item.key"
        >{{ item.label }}</button>
      </div>

      <p class="fixture-banner" role="note">{{ activeCase.note }}</p>

      <div class="cards">
        <ContractCard
          :contract="activeCase.contract"
          :claim="activeCase.claim"
          :receipt="activeCase.receipt"
          :action="activeCase.action"
          :inspection-passed="activeCase.inspection_passed"
          :authorization="activeCase.authorization"
          :source="activeCase.source"
        />
        <GapCard
          :obligations="activeCase.contract.obligations"
          :obligation-results="activeCase.obligation_results"
          :probe-decision="activeCase.probe_decision"
          :budget="activeCase.contract.budgets"
          :verdict="activeCase.receipt.verdict"
          :source="activeCase.source"
        />
        <ReplayCard
          :bundle="activeCase.replay_bundle"
          :replay="activeCase.replay"
          :baseline-results="activeCase.receipt.obligation_results"
          :source="activeCase.source"
        />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ContractCard from '../../components/operations/recovery/ContractCard.vue'
import GapCard from '../../components/operations/recovery/GapCard.vue'
import ReplayCard from '../../components/operations/recovery/ReplayCard.vue'
import { BUSINESS_FALSE_CASE, VERIFIED_CASE } from '../../components/operations/recovery/fixtures.js'
import { liveCaseFromDetail } from '../../components/operations/recovery/liveCase.js'
import { getRecoveryContract, listRecoveryContracts } from '../../api/recovery.ts'

const unwrap = response => response?.data ?? response

const modes = Object.freeze([
  { key: 'live', label: '真实数据' },
  { key: 'fixture', label: '演示样例' }
])
const mode = ref('live')

const cases = Object.freeze([
  { key: 'verified', label: 'VERIFIED 样例', data: VERIFIED_CASE },
  { key: 'contradicted', label: 'CONTRADICTED 样例', data: BUSINESS_FALSE_CASE }
])
const activeKey = ref(cases[0].key)
const activeCase = computed(() => cases.find(item => item.key === activeKey.value)?.data ?? cases[0].data)

const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const detailError = ref('')
const contracts = ref([])
const detail = ref(null)
const selectedId = ref(null)
const runIdInput = ref('')

function switchMode(next) {
  mode.value = next
  if (next === 'live' && contracts.value.length === 0 && !loading.value) reload()
}

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: 1, pageSize: 50 }
    if (runIdInput.value) params.runId = Number(runIdInput.value)
    const result = unwrap(await listRecoveryContracts(params))
    contracts.value = result?.items ?? []
    if (!contracts.value.some(item => item.id === selectedId.value)) {
      selectedId.value = contracts.value[0]?.id ?? null
      detail.value = null
    }
    if (selectedId.value) await select(selectedId.value)
  } catch (cause) {
    contracts.value = []
    detail.value = null
    error.value = cause?.message || '加载恢复契约失败，请检查后端服务与登录状态。'
  } finally {
    loading.value = false
  }
}

async function select(id) {
  selectedId.value = id
  detailLoading.value = true
  detailError.value = ''
  try {
    detail.value = unwrap(await getRecoveryContract(id))
  } catch (cause) {
    detail.value = null
    detailError.value = cause?.message || '加载契约详情失败。'
  } finally {
    detailLoading.value = false
  }
}

/** 平台记录 → 三卡所需的展示视图；不在前端补算 verdict 或回执。 */
const liveCase = computed(() => liveCaseFromDetail(detail.value))

function verdictTone(verdict) {
  if (verdict === 'VERIFIED') return 'ok'
  if (verdict === 'CONTRADICTED') return 'bad'
  return 'unknown'
}

function stateTone(state) {
  if (state === 'ACTIVE') return 'ok'
  if (state === 'INVALIDATED' || state === 'EXPIRED') return 'warn'
  return 'unknown'
}

onMounted(reload)
</script>

<style scoped>
.recovery-view {
  display: grid;
  gap: 16px;
  padding: 20px;
  color: var(--smart-text);
  font: 13px/1.6 var(--font-cn);
}
.page-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--smart-primary-strong);
  font: 10px var(--font-mono);
  letter-spacing: .14em;
}
h1 { margin: 0 0 6px; font-size: 20px; font-weight: 600; }
.page-heading p { margin: 0; color: var(--smart-muted); }
.mode-switch, .case-switch {
  display: flex;
  gap: 8px;
  flex: none;
}
.mode-tab, .case-tab {
  padding: 6px 14px;
  border: 1px solid var(--smart-border);
  border-radius: 999px;
  background: var(--smart-bg);
  color: var(--smart-text);
  font: 12px var(--font-cn);
  cursor: pointer;
}
.mode-tab.active, .case-tab.active {
  border-color: var(--smart-primary-strong);
  color: var(--smart-primary-strong);
  font-weight: 650;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--smart-muted);
}
.filter input {
  width: 180px;
  padding: 6px 10px;
  border: 1px solid var(--smart-border);
  border-radius: 8px;
  background: var(--smart-bg);
  color: var(--smart-text);
  font: 12px var(--font-mono);
}
.primary {
  padding: 7px 16px;
  border: 1px solid var(--smart-primary-strong);
  border-radius: 8px;
  background: var(--smart-primary-strong);
  color: #fff;
  font: 12px var(--font-cn);
  cursor: pointer;
}
.primary:disabled { opacity: .6; cursor: default; }
.hint { font-size: 11px; color: var(--smart-muted); }
.empty-state {
  padding: 28px;
  border: 1px dashed var(--smart-border);
  border-radius: 12px;
  background: var(--smart-surface);
  text-align: center;
}
.empty-state p { margin: 8px auto 0; max-width: 560px; color: var(--smart-muted); font-size: 12px; }
.empty-state code { font-family: var(--font-mono); color: var(--smart-primary-strong); }
.live-layout {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.contract-list {
  display: grid;
  gap: 8px;
  max-height: 70vh;
  overflow: auto;
}
.contract-item {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--smart-border);
  border-radius: 10px;
  background: var(--smart-surface);
  color: var(--smart-text);
  text-align: left;
  cursor: pointer;
}
.contract-item.active { border-color: var(--smart-primary-strong); }
.item-title { font: 600 12px var(--font-mono); }
.item-target { font-size: 11px; color: var(--smart-muted); }
.item-meta { display: flex; gap: 6px; }
.item-time { font-size: 10px; color: var(--smart-muted); }
.chip {
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid var(--smart-border);
  font: 10px var(--font-mono);
}
.chip.ok { color: var(--smart-success); border-color: var(--smart-success); }
.chip.bad { color: var(--smart-danger); border-color: var(--smart-danger); }
.chip.warn { color: var(--smart-warning); border-color: var(--smart-warning); }
.chip.unknown { color: var(--smart-muted); }
.loading-block { padding: 24px; color: var(--smart-muted); }
.error-banner {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--smart-danger);
  border-radius: 10px;
  color: var(--smart-danger);
  background: var(--smart-surface);
  font-size: 12px;
}
.fixture-banner {
  margin: 0;
  padding: 10px 14px;
  border: 1px dashed var(--smart-warning);
  border-radius: 10px;
  color: var(--smart-warning);
  background: var(--smart-surface);
  font-size: 12px;
}
.cards {
  display: grid;
  gap: 16px;
}
@media (max-width: 900px) {
  .live-layout { grid-template-columns: 1fr; }
  .contract-list { max-height: none; }
}
</style>
