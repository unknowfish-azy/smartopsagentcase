<template>
  <section class="course-detail">
    <header class="page-header">
      <div>
        <p class="eyebrow">COURSE / {{ course?.category || '课程' }}</p>
        <h1>{{ course?.title || '加载中…' }}</h1>
        <p class="muted">{{ course?.summary }}</p>
        <small class="source">{{ course?.source }}</small>
      </div>
      <div class="header-actions">
        <RouterLink class="ghost" to="/study">返回课程目录</RouterLink>
        <button type="button" @click="resetProgress">清空本课程进度</button>
      </div>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>

    <nav class="chapter-nav" aria-label="章节目录">
      <button
        v-for="(chapter, index) in chapters"
        :key="chapter.chapterNo"
        :class="{ active: activeChapter === index }"
        type="button"
        @click="scrollTo(index)"
      >
        <span class="chapter-no">{{ String(chapter.chapterNo).padStart(2, '0') }}</span>
        <span class="chapter-body">
          <strong>{{ chapter.chapterTitle }}</strong>
          <small>{{ masteredIn(chapter) }}/{{ chapter.points.length }} 掌握</small>
        </span>
      </button>
    </nav>

    <div v-if="chapters.length" class="chapters">
      <section v-for="(chapter, index) in chapters" :key="chapter.chapterNo" :ref="setChapterRef(index)" class="chapter">
        <header class="chapter-head">
          <h2>第 {{ chapter.chapterNo }} 章 · {{ chapter.chapterTitle }}</h2>
          <span class="chapter-meta">{{ masteredIn(chapter) }}/{{ chapter.points.length }}</span>
        </header>

        <article v-for="point in chapter.points" :key="point.id" class="point" :class="{ mastered: point.mastered }">
          <label class="check">
            <input
              type="checkbox"
              :checked="point.mastered"
              :aria-label="`标记「${point.title}」为已掌握`"
              :disabled="busyId === point.id"
              @change="toggle(point, $event.target.checked)"
            />
          </label>
          <div class="point-body">
            <div class="point-title">
              <h3>{{ point.title }}</h3>
              <span class="badge" :class="point.difficulty.toLowerCase()">{{ DIFFICULTY_LABELS[point.difficulty] || point.difficulty }}</span>
              <span v-if="point.examWeight >= 4" class="badge hot">高频</span>
            </div>
            <p class="point-text">{{ point.body }}</p>
            <textarea
              v-if="point.mastered"
              v-model="point.note"
              class="note"
              rows="2"
              placeholder="记忆点 / 易错点备注（可选）"
              :aria-label="`「${point.title}」备注`"
              @blur="saveNote(point)"
            />
            <small v-if="point.updatedAt" class="updated">最近更新 {{ formatTime(point.updatedAt) }}</small>
          </div>
        </article>
      </section>
    </div>
    <p v-else-if="!loading" class="muted empty">这门课还没有知识点，请检查语料灌入脚本。</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getStudyCourse, resetStudyCourse, saveStudyProgress } from '../../api/study.ts'

const DIFFICULTY_LABELS = { EASY: '基础', MEDIUM: '进阶', HARD: '难点' }

const route = useRoute()
const code = decodeURIComponent(route.params.code)

const detail = ref(null)
const chapters = ref([])
const activeChapter = ref(0)
const chapterRefs = ref([])
const busyId = ref(null)
const loading = ref(true)
const error = ref('')
const notice = ref('')

const course = computed(() => detail.value?.course || null)

function setChapterRef(index) {
  return element => {
    chapterRefs.value[index] = element
  }
}

function masteredIn(chapter) {
  return chapter.points.filter(point => point.mastered).length
}

function scrollTo(index) {
  activeChapter.value = index
  chapterRefs.value[index]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function formatTime(value) {
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return value
  }
}

async function toggle(point, mastered) {
  busyId.value = point.id
  error.value = ''
  try {
    await saveStudyProgress(point.id, mastered, point.note)
    point.mastered = mastered
    if (!mastered) point.note = ''
    notice.value = mastered ? `已标记掌握：${point.title}` : `已取消掌握：${point.title}`
  } catch (cause) {
    error.value = cause.message || '保存掌握度失败'
  } finally {
    busyId.value = null
  }
}

async function saveNote(point) {
  if (!point.note?.trim()) return
  try {
    await saveStudyProgress(point.id, true, point.note)
    notice.value = `备注已保存：${point.title}`
  } catch (cause) {
    error.value = cause.message || '保存备注失败'
  }
}

async function resetProgress() {
  if (!window.confirm(`确定清空《${course.value?.title}》的全部个人进度？`)) return
  try {
    const result = unwrap(await resetStudyCourse(code))
    chapters.value = chapters.value.map(chapter => ({
      ...chapter,
      points: chapter.points.map(point => ({ ...point, mastered: false, note: '' }))
    }))
    notice.value = `已清空 ${result.cleared ?? 0} 条掌握记录`
    error.value = ''
  } catch (cause) {
    error.value = cause.message || '清空进度失败'
  }
}

onMounted(async () => {
  try {
    const result = detail.value = unwrap(await getStudyCourse(code))
    chapters.value = result.chapters || []
  } catch (cause) {
    error.value = cause.message || '读取课程失败'
  } finally {
    loading.value = false
  }
})

function unwrap(value) {
  return value?.data ?? value
}
</script>

<style scoped>
.course-detail{max-width:1320px;margin:0 auto;padding:clamp(16px,3vw,32px);color:var(--smart-text);overflow-wrap:anywhere}
.page-header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.header-actions{display:flex;gap:8px;flex-wrap:wrap;flex:0 0 auto}
.eyebrow{font:10px var(--font-mono);letter-spacing:.12em;color:var(--smart-primary-strong)}
h1{margin:8px 0;font-size:clamp(22px,3vw,28px)}
.muted{color:var(--smart-muted);font-size:12px;line-height:1.7}
.source{display:block;margin-top:8px;font:10px var(--font-mono);color:var(--smart-muted)}
button,.ghost{min-height:42px;padding:9px 13px;border:1px solid var(--smart-border);border-radius:7px;background:var(--smart-surface);color:var(--smart-text);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;font-size:13px}
button:focus-visible,.ghost:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:2px}
.chapter-nav{display:flex;gap:8px;flex-wrap:wrap;margin-top:22px;position:sticky;top:0;z-index:2;background:var(--smart-bg);padding:10px 0}
.chapter-nav button{display:flex;align-items:center;gap:10px;min-height:44px;padding:8px 12px;text-align:left}
.chapter-nav button.active{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 10%,transparent)}
.chapter-no{font:600 12px var(--font-mono);color:var(--smart-primary-strong)}
.chapter-body{display:flex;flex-direction:column;gap:3px}
.chapter-body strong{font-size:12px}
.chapter-body small{font:10px var(--font-mono);color:var(--smart-muted)}
.chapters{margin-top:18px;display:flex;flex-direction:column;gap:26px}
.chapter-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;border-bottom:1px solid var(--smart-border);padding-bottom:8px}
.chapter-head h2{margin:0;font-size:17px}
.chapter-meta{font:10px var(--font-mono);color:var(--smart-muted)}
.point{display:grid;grid-template-columns:26px minmax(0,1fr);gap:12px;padding:14px 0;border-bottom:1px solid var(--smart-border)}
.check input{width:20px;height:20px;accent-color:var(--smart-primary-strong)}
.point.mastered .point-title h3{color:var(--smart-muted);text-decoration:line-through;text-decoration-color:color-mix(in srgb,var(--smart-muted) 55%,transparent)}
.point-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.point-title h3{margin:0;font-size:14px;overflow-wrap:anywhere}
.badge{font:10px var(--font-mono);padding:2px 7px;border-radius:999px;border:1px solid var(--smart-border);color:var(--smart-muted)}
.badge.easy{color:var(--smart-primary-strong);border-color:color-mix(in srgb,var(--smart-primary-strong) 45%,transparent)}
.badge.hard{color:var(--smart-danger);border-color:color-mix(in srgb,var(--smart-danger) 45%,transparent)}
.badge.hot{color:#b45309;border-color:color-mix(in srgb,#b45309 45%,transparent)}
.point-text{margin:8px 0 0;color:var(--smart-muted);font-size:12px;line-height:1.8;white-space:pre-line;overflow-wrap:anywhere}
.note{display:block;width:100%;box-sizing:border-box;margin-top:10px;padding:10px;resize:vertical;background:var(--smart-bg);border:1px solid var(--smart-border);border-radius:7px;color:var(--smart-text);font:12px/1.6 var(--font-cn)}
.updated{display:block;margin-top:6px;font:10px var(--font-mono);color:var(--smart-muted)}
.error{color:var(--smart-danger);font-size:12px}
.notice{color:var(--smart-primary-strong);font-size:12px}
.empty{padding:35px;text-align:center}
@media(max-width:800px){.page-header{flex-direction:column}.header-actions{width:100%}.header-actions>*{flex:1;justify-content:center}.chapter-nav{position:static}}
</style>
