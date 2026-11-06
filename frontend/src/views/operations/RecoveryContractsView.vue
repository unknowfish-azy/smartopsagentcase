<template>
  <section class="recovery-view" aria-labelledby="recovery-title">
    <header class="page-heading">
      <div>
        <p class="eyebrow">RECOVERY CONTRACTS / 恢复契约</p>
        <h1 id="recovery-title">恢复契约中心</h1>
        <p>按恢复契约 v1 语义展示契约、回执、补证调度缺口与回放差分；四轴状态互不替代。</p>
      </div>
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
    </header>

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
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import ContractCard from '../../components/operations/recovery/ContractCard.vue'
import GapCard from '../../components/operations/recovery/GapCard.vue'
import ReplayCard from '../../components/operations/recovery/ReplayCard.vue'
import { BUSINESS_FALSE_CASE, VERIFIED_CASE } from '../../components/operations/recovery/fixtures.js'

const cases = Object.freeze([
  { key: 'verified', label: 'VERIFIED 样例', data: VERIFIED_CASE },
  { key: 'contradicted', label: 'CONTRADICTED 样例', data: BUSINESS_FALSE_CASE }
])

const activeKey = ref(cases[0].key)
const activeCase = computed(() => cases.find(item => item.key === activeKey.value)?.data ?? cases[0].data)
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
.case-switch {
  display: flex;
  gap: 8px;
  flex: none;
}
.case-tab {
  padding: 6px 14px;
  border: 1px solid var(--smart-border);
  border-radius: 999px;
  background: var(--smart-bg);
  color: var(--smart-text);
  font: 12px var(--font-cn);
  cursor: pointer;
}
.case-tab.active {
  border-color: var(--smart-primary-strong);
  color: var(--smart-primary-strong);
  font-weight: 650;
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
</style>
