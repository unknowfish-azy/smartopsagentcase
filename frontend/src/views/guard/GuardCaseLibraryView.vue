<template>
  <div class="ag-shell">
    <header class="ag-head">
      <div>
        <p class="ag-eyebrow">CASE LIBRARY · 声明式 · 可复现</p>
        <h1 class="ag-title">测评用例库</h1>
        <p class="ag-lede">
          内置 6 大类共 {{ cases.length }} 条攻击用例，覆盖 OWASP LLM Top10 的提示注入、敏感信息泄露与过度代理。
          用例只描述输入与期望行为，判定口径统一由确定性检测器执行。
        </p>
      </div>
      <div class="ag-actions">
        <router-link class="ag-btn" to="/guard">返回总览</router-link>
        <router-link class="ag-btn ag-btn--primary" to="/guard/runs">用这套用例发起测评</router-link>
      </div>
    </header>

    <div v-if="error" class="ag-error">{{ error }}</div>

    <div class="ag-filters">
      <button
        v-for="item in categoryFilters"
        :key="item.value"
        class="ag-chip"
        :class="{ 'is-active': category === item.value }"
        @click="category = item.value"
      >{{ item.label }}</button>
    </div>

    <div class="ag-filters">
      <button
        v-for="item in severityFilters"
        :key="item.value"
        class="ag-chip"
        :class="{ 'is-active': severity === item.value }"
        @click="severity = item.value"
      >{{ item.label }}</button>
      <input
        v-model="keyword"
        type="search"
        placeholder="搜索标题、用例 ID 或提示词"
        aria-label="搜索用例"
        style="min-width: 220px; padding: 5px 11px; border: 1px solid var(--ag-line); border-radius: 999px; background: transparent; color: var(--ag-text); font-size: 11px"
      />
    </div>

    <p class="ag-note">共 {{ filtered.length }} 条用例{{ loading ? ' · 加载中…' : '' }}</p>

    <div v-if="filtered.length" style="margin-top: 12px">
      <article v-for="item in filtered" :key="item.id" class="ag-item">
        <div class="ag-item__head">
          <p class="ag-item__title">{{ item.title }}</p>
          <div class="ag-actions">
            <span class="ag-pill" :class="severityPillClass(item.severity)">{{ item.severityLabel }}</span>
            <span class="ag-pill ag-pill--muted">{{ item.categoryLabel }}</span>
          </div>
        </div>
        <div class="ag-item__meta">
          <span class="ag-mono">{{ item.id }}</span>
          <span>{{ item.owasp }}</span>
          <span>检测器 {{ item.detector }}</span>
        </div>
        <pre class="ag-pre"><span class="ag-pre__label">测试输入</span>{{ item.prompt }}</pre>
        <p class="ag-note" style="margin: 8px 0 0">期望行为：{{ item.expected }}</p>
      </article>
    </div>

    <div v-else-if="!loading" class="ag-empty">
      <h2>没有匹配的用例</h2>
      <p>调整分类、严重度或关键词后再试。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getGuardCases } from '../../api/guard'
import type { GuardCaseItem } from '../../api/guard'
import './guard.css'

const cases = ref<GuardCaseItem[]>([])
const category = ref('ALL')
const severity = ref('ALL')
const keyword = ref('')
const loading = ref(false)
const error = ref('')

const categoryFilters = [
  { value: 'ALL', label: '全部分类' },
  { value: 'PROMPT_INJECTION', label: '提示注入' },
  { value: 'JAILBREAK', label: '越狱与角色劫持' },
  { value: 'DATA_EXFILTRATION', label: '敏感数据外泄' },
  { value: 'TOOL_ABUSE', label: '工具滥用' },
  { value: 'PRIVILEGE_ESCALATION', label: '越权与审计绕过' },
  { value: 'ROBUSTNESS', label: '编码与鲁棒性' }
]

const severityFilters = [
  { value: 'ALL', label: '全部严重度' },
  { value: 'CRITICAL', label: '严重' },
  { value: 'HIGH', label: '高危' },
  { value: 'MEDIUM', label: '中危' },
  { value: 'LOW', label: '低危' }
]

const filtered = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  return cases.value.filter((item) => {
    if (category.value !== 'ALL' && item.category !== category.value) return false
    if (severity.value !== 'ALL' && item.severity !== severity.value) return false
    if (!query) return true
    return `${item.id} ${item.title} ${item.prompt} ${item.expected}`.toLowerCase().includes(query)
  })
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await getGuardCases()
    cases.value = response.data as GuardCaseItem[]
  } catch (exception: unknown) {
    error.value = exception instanceof Error ? exception.message : '加载用例库失败'
  } finally {
    loading.value = false
  }
}

function severityPillClass(value: string) {
  if (value === 'CRITICAL' || value === 'HIGH') return 'ag-pill--fail'
  if (value === 'MEDIUM') return 'ag-pill--warn'
  return 'ag-pill--info'
}

onMounted(load)
</script>
