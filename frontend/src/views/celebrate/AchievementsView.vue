<template>
  <!-- 兼容壳：里程碑战报已并入「用量与额度」?view=milestones；路由 /milestones 由 redirect 承接。
       保留本组件仅为旧 import 路径不报错，正文统一由 MilestoneReportPanel 提供。 -->
  <section class="achievements-compat">
    <header class="hall-heading">
      <div>
        <p class="eyebrow">MILESTONE HALL / 里程碑战报</p>
        <h1>里程碑战报</h1>
        <p class="intro">每一项里程碑都来自真实调用账本。这里只庆祝已经发生的事实，不展示收益、回撤等无法诚实产出的指标。</p>
      </div>
      <RouterLink class="outline-button" to="/token-usage?view=milestones">在用量与额度中查看 <span aria-hidden="true">↗</span></RouterLink>
    </header>
    <div v-if="error" class="state-panel error-panel" role="alert">
      <h2>暂时无法读取账本</h2>
      <p>{{ error }}</p>
      <button type="button" class="outline-button" :disabled="loading" @click="loadReport()">重新加载</button>
    </div>
    <div v-else-if="loading" class="state-panel" role="status">正在读取 {{ month }} 的调用账本…</div>
    <MilestoneReportPanel v-else-if="report" :report="report" :month="month" :ambient="ambientOn" :preview="preview" />
  </section>
</template>

<script setup>
/** 兼容壳：数据链路与新面板一致（同一个 getModelAnalytics），不复制任何档位计算逻辑。 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import MilestoneReportPanel from '../../components/model/MilestoneReportPanel.vue'
import { getModelAnalytics } from '../../api/modelAnalytics.ts'

const route = useRoute()
const month = ref(new Date().toISOString().slice(0, 7))
const report = ref(null)
const loading = ref(false)
const error = ref('')
const ambientOn = ref(route.query.ambient !== '0')
const preview = computed(() => route.query.preview === '1')
let disposed = false

const unwrap = response => response?.data ?? response
async function loadReport() {
  error.value = ''
  loading.value = true
  try {
    const data = unwrap(await getModelAnalytics(month.value))
    if (!disposed) report.value = data
  } catch (err) {
    if (!disposed) error.value = err.message || '账本服务暂不可用，请重试。'
  } finally {
    if (!disposed) loading.value = false
  }
}
onMounted(loadReport)
onBeforeUnmount(() => { disposed = true })
</script>

<style scoped>
.achievements-compat { max-width: 1280px; margin: 0 auto; padding: 12px 0 36px; color: var(--smart-text); font-family: var(--font-cn); }
.hall-heading { display: flex; justify-content: space-between; gap: 24px; align-items: center; }
.eyebrow { margin: 0 0 10px; color: var(--smart-primary-strong); font: 10px var(--font-mono); letter-spacing: .13em; }
h1 { margin: 0; font-size: clamp(26px, 3vw, 36px); font-weight: 550; letter-spacing: -.03em; }
.intro { color: var(--smart-muted); font-size: 13px; line-height: 1.8; margin: 12px 0 0; max-width: 640px; }
.outline-button { display: inline-flex; align-items: center; justify-content: center; gap: 14px; min-height: 40px; padding: 9px 16px; border: 1px solid var(--smart-border); border-radius: 8px; font: inherit; font-size: 12px; color: var(--smart-text); background: var(--smart-surface); text-decoration: none; cursor: pointer; white-space: nowrap; }
.state-panel { padding: 54px 24px; text-align: center; border: 1px solid var(--smart-border); border-radius: 12px; background: var(--smart-surface); color: var(--smart-muted); font-size: 13px; margin-top: 24px; }
@media (max-width: 767px) { .hall-heading { align-items: start; flex-direction: column; gap: 16px; } }
</style>
