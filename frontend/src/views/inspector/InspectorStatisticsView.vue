<template>
  <div class="page">
    <header>
      <div>
        <h1>Inspector Statistics</h1>
        <p>仅展示数据库中的真实纠察数据</p>
      </div>
      <RouterLink to="/inspector">返回中心</RouterLink>
      <RouterLink to="/inspector/desk?view=stats">在洞察台打开</RouterLink>
    </header>

    <InspectorSummary :summary="data.summary || {}" />

    <div class="grid">
      <section>
        <h2>By Category</h2>
        <div v-if="!data.byCategory?.length" class="statistics-empty">
          <AppEmpty description="暂无统计" />
        </div>
        <p v-for="item in data.byCategory" :key="item.category">
          <span>{{ item.category }}</span>
          <strong>{{ item.count }}</strong>
        </p>
      </section>
      <section>
        <h2>By Target</h2>
        <div v-if="!data.byTarget?.length" class="statistics-empty">
          <AppEmpty description="暂无统计" />
        </div>
        <p v-for="item in data.byTarget" :key="item.target">
          <span>{{ item.target }}</span>
          <strong>{{ item.count }}</strong>
        </p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { getInspectorStatistics } from '../../api/inspector'
import InspectorSummary from '../../components/inspector/InspectorSummary.vue'
import AppEmpty from '../../components/common/AppEmpty.vue'

const data = ref({})

onMounted(async () => {
  try {
    const response = await getInspectorStatistics()
    data.value = response.data || {}
  } catch {
    data.value = {}
  }
})
</script>

<style scoped>
.page {
  display: grid;
  gap: 20px;
  padding: 22px;
  color: var(--smart-text);
  background: var(--smart-surface);
  border: 1px solid var(--smart-border);
  border-radius: 12px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

header h1 {
  margin: 0;
  color: var(--smart-text);
  font-size: 22px;
}

header p {
  margin: 8px 0 0;
  color: var(--smart-muted);
}

header a {
  color: var(--smart-primary-strong);
  text-decoration-color: color-mix(in srgb, var(--smart-primary-strong) 55%, transparent);
  text-underline-offset: 4px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.grid section {
  min-width: 0;
  padding: 20px;
  background: var(--smart-bg);
  border: 1px solid var(--smart-border);
  border-radius: 10px;
}

.grid h2 {
  margin: 0 0 8px;
  color: var(--smart-text);
  font-size: 16px;
  font-weight: 650;
}

.grid p {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  color: var(--smart-muted);
  border-bottom: 1px solid var(--smart-border);
}

.grid p strong {
  color: var(--smart-primary-strong);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.statistics-empty {
  display: grid;
  min-height: 128px;
  margin-top: 14px;
  place-items: center;
  background: var(--smart-bg);
  border: 1px solid var(--smart-border);
  border-radius: 8px;
}

.statistics-empty :deep(.empty) {
  padding: 28px;
  color: var(--smart-muted);
}

.statistics-empty :deep(.icon) {
  opacity: .72;
}

.statistics-empty :deep(.text) {
  color: var(--smart-muted);
}

@media (max-width: 700px) {
  .page {
    padding: 16px;
  }

  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
