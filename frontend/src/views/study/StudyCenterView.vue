<template>
  <section class="study-center">
    <header class="page-header">
      <div>
        <p class="eyebrow">STUDY CENTER</p>
        <h1>学习中心</h1>
        <p class="muted">教材与实验资料蒸馏成「课程 → 章节 → 知识点」语料，勾选掌握度形成个人学习画像。</p>
      </div>
      <div class="header-actions">
        <RouterLink class="primary" to="/network-lab">网络实验</RouterLink>
        <RouterLink class="primary ghost" to="/ai-perf-lab">AI 性能实验</RouterLink>
      </div>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>

    <section v-if="overview" class="stat-band" aria-label="学习概览">
      <div class="stat"><span class="stat-value">{{ overview.courseCount }}</span><span class="stat-label">课程</span></div>
      <div class="stat"><span class="stat-value">{{ overview.pointCount }}</span><span class="stat-label">知识点</span></div>
      <div class="stat"><span class="stat-value">{{ overview.masteredCount }}</span><span class="stat-label">已掌握</span></div>
      <div class="stat grow">
        <span class="stat-value">{{ overview.masteredPercent }}%</span>
        <span class="stat-label">总掌握度</span>
        <progress :value="overview.masteredPercent" max="100" aria-label="总掌握度" />
      </div>
    </section>
    <p v-else class="muted loading">正在读取学习总览…</p>

    <section v-for="[category, courses] in groupedCourses" :key="category" class="category">
      <header class="category-head">
        <h2>{{ category }}</h2>
        <span>{{ courses.length }} 门课</span>
      </header>
      <div class="cards">
        <RouterLink
          v-for="course in courses"
          :key="course.code"
          class="card"
          :to="`/study/course/${encodeURIComponent(course.code)}`"
        >
          <div class="card-top">
            <span class="icon">{{ COURSE_ICONS[course.icon] || '📘' }}</span>
            <span class="count">{{ course.pointCount }} 点</span>
          </div>
          <h3>{{ course.title }}</h3>
          <p class="summary">{{ course.summary }}</p>
          <div class="progress-row">
            <progress :value="percent(course)" max="100" :aria-label="`${course.title} 掌握度`" />
            <span>{{ percent(course) }}%</span>
          </div>
          <small class="source">{{ course.source }}</small>
        </RouterLink>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getStudyOverview } from '../../api/study.ts'

const COURSE_ICONS = {
  pattern: '🧩',
  coffee: '☕',
  leaf: '🍃',
  layers: '🥞',
  tree: '🌳',
  cpu: '🖥️',
  snake: '🐍',
  terminal: '⌨️',
  database: '🗄️',
  cart: '🛒',
  network: '🌐',
  chip: '⚡',
  book: '📘'
}

const overview = ref(null)
const error = ref('')
const notice = ref('')

const groupedCourses = computed(() => Object.entries(overview.value?.categories || {}))

function percent(course) {
  return course.pointCount === 0 ? 0 : Math.round((100 * course.masteredCount) / course.pointCount)
}

onMounted(async () => {
  try {
    const result = overview.value = unwrap(await getStudyOverview())
    if (!result.categories || !Object.keys(result.categories).length) {
      notice.value = '课程目录还是空的，请先确认数据库迁移 V20261125.30 已执行。'
    }
  } catch (cause) {
    error.value = cause.message || '读取学习总览失败'
  }
})

function unwrap(value) {
  return value?.data ?? value
}
</script>

<style scoped>
.study-center{max-width:1320px;margin:0 auto;padding:clamp(16px,3vw,32px);color:var(--smart-text);overflow-wrap:anywhere}
.page-header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.header-actions{display:flex;gap:8px;flex-wrap:wrap;flex:0 0 auto}
.eyebrow{font:10px var(--font-mono);letter-spacing:.12em;color:var(--smart-primary-strong)}
h1{margin:8px 0;font-size:clamp(24px,3vw,30px)}
.muted{color:var(--smart-muted);font-size:12px;line-height:1.7}
.primary{min-height:42px;display:inline-flex;align-items:center;padding:9px 13px;border:1px solid transparent;border-radius:7px;background:var(--smart-primary-strong);color:var(--smart-bg);text-decoration:none;font-size:13px}
.primary.ghost{background:var(--smart-surface);color:var(--smart-text);border-color:var(--smart-border)}
button,.primary:focus-visible{outline-offset:2px}
.stat-band{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}
.stat{border:1px solid var(--smart-border);background:var(--smart-surface);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:6px;min-width:0}
.stat.grow{grid-column:span 2}
.stat-value{font:600 clamp(20px,2.4vw,28px)/1.1 var(--font-mono);color:var(--smart-primary-strong)}
.stat-label{font-size:11px;color:var(--smart-muted)}
.stat progress{width:100%;height:8px;margin-top:auto}
.category{margin-top:26px}
.category-head{display:flex;align-items:baseline;gap:10px;border-bottom:1px solid var(--smart-border);padding-bottom:8px}
.category-head h2{margin:0;font-size:17px}
.category-head span{font:10px var(--font-mono);color:var(--smart-muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-top:16px}
.card{display:block;border:1px solid var(--smart-border);background:var(--smart-surface);border-radius:10px;padding:16px;text-decoration:none;color:inherit;transition:border-color .18s,transform .18s}
.card:hover{border-color:var(--smart-primary-strong);transform:translateY(-2px)}
.card-top{display:flex;justify-content:space-between;align-items:center}
.icon{font-size:22px}
.count{font:10px var(--font-mono);color:var(--smart-muted)}
.card h3{margin:12px 0 6px;font-size:15px;overflow-wrap:anywhere}
.summary{margin:0;color:var(--smart-muted);font-size:12px;line-height:1.7;min-height:40px;overflow:hidden}
.progress-row{display:flex;align-items:center;gap:10px;margin-top:12px;font:11px var(--font-mono);color:var(--smart-muted)}
.progress-row progress{flex:1;height:6px}
.source{display:block;margin-top:10px;font:10px var(--font-mono);color:var(--smart-muted);overflow-wrap:anywhere}
.loading{padding:20px 0}
.error{color:var(--smart-danger);font-size:12px}
.notice{color:var(--smart-primary-strong);font-size:12px}
progress{accent-color:var(--smart-primary-strong);border-radius:999px}
@media(max-width:900px){.page-header{flex-direction:column}.header-actions{width:100%}.header-actions .primary{flex:1;justify-content:center}.stat-band{grid-template-columns:repeat(2,minmax(0,1fr))}.stat.grow{grid-column:span 2}}
</style>
