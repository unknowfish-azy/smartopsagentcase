<template>
  <div class="atlas-page">
    <header class="atlas-head">
      <p class="atlas-eyebrow">KNOWLEDGE ATLAS / 知识蒸馏图谱</p>
      <h1>运维知识蒸馏图谱</h1>
      <p class="atlas-lede">
        把 <strong>{{ snapshot.sourceRoot }}</strong> 语料库（{{ snapshot.totals.documents }} 篇课程笔记）
        蒸馏成一张可探索的知识地图：课程环 → 文档节点 → 高频命令。数据是
        <strong>{{ snapshotTime }}</strong> 蒸馏的快照，不是实时数据；语料更新后执行
        <code class="atlas-mono">npm run atlas:distill</code> 重新生成。
        蒸馏过程只读文件、不执行其中任何命令。
      </p>
    </header>

    <div v-if="isEmpty" class="atlas-empty">
      <h3>还没有蒸馏快照</h3>
      <p>
        在 frontend 目录执行 <code class="atlas-mono">npm run atlas:distill</code>，
        会扫描语料库并生成 atlasDistilled.json。本页不编造演示数据。
      </p>
    </div>

    <template v-else>
      <dl class="atlas-stats">
        <div><dt>课程模块</dt><dd>{{ snapshot.totals.courses }}</dd></div>
        <div><dt>文档</dt><dd>{{ snapshot.totals.documents }}</dd></div>
        <div><dt>章节标题</dt><dd>{{ snapshot.totals.headings }}</dd></div>
        <div><dt>代码块</dt><dd>{{ snapshot.totals.codeBlocks }}</dd></div>
        <div><dt>字符量</dt><dd>{{ formatChars(snapshot.totals.chars) }}</dd></div>
      </dl>

      <div class="atlas-main">
        <section class="atlas-canvas-panel" aria-label="知识图谱主图">
          <div class="atlas-canvas-head">
            <strong>知识图谱</strong>
            <span v-if="selectedCourse" class="atlas-filter-note">
              已聚焦「{{ selectedCourse.label }}」
              <button type="button" class="atlas-link-btn" @click="clearFilter">显示全部</button>
            </span>
            <span v-else class="atlas-muted">点击课程卡片聚焦 · 悬停/点击节点看详情</span>
          </div>
          <div ref="canvasBox" class="atlas-canvas-box">
            <canvas ref="canvasEl" @mousemove="onHover" @mouseleave="onLeave" @click="onClick"></canvas>
          </div>
          <div v-if="selectedDoc" class="atlas-doc-panel">
            <div class="atlas-doc-head">
              <strong>{{ selectedDoc.title }}</strong>
              <button type="button" class="atlas-link-btn" @click="selectedDocId = null">关闭</button>
            </div>
            <p class="atlas-muted atlas-doc-path">{{ selectedDoc.path }} · {{ formatChars(selectedDoc.chars) }} · {{ selectedDoc.codeBlocks }} 个代码块</p>
            <div class="atlas-chips">
              <span v-for="heading in selectedDoc.headings" :key="heading.text" class="atlas-chip">{{ heading.text }}</span>
            </div>
            <div v-if="selectedDoc.commands.length" class="atlas-chips">
              <code v-for="item in selectedDoc.commands" :key="item.cmd" class="atlas-code-chip">{{ item.cmd }} ×{{ item.count }}</code>
            </div>
          </div>
        </section>

        <aside class="atlas-side" aria-label="课程模块">
          <article
            v-for="course in snapshot.courses"
            :key="course.id"
            class="atlas-course"
            :class="{ 'atlas-course--active': selectedCourseId === course.id }"
            @click="toggleCourse(course.id)"
          >
            <div class="atlas-course__head">
              <span class="atlas-dot" :style="{ background: courseColor(course.id) }"></span>
              <strong>{{ course.label }}</strong>
              <span class="atlas-muted">{{ course.documentCount }} 篇</span>
            </div>
            <p class="atlas-muted">{{ formatChars(course.chars) }} · {{ course.codeBlocks }} 个代码块</p>
            <div class="atlas-chips">
              <code v-for="item in course.topCommands.slice(0, 4)" :key="item.cmd" class="atlas-code-chip">{{ item.cmd }} ×{{ item.count }}</code>
            </div>
          </article>
        </aside>
      </div>

      <div class="atlas-bottom">
        <section class="atlas-panel" aria-label="高频命令蒸馏">
          <h2>高频命令 Top 12</h2>
          <p class="atlas-muted">从 {{ snapshot.totals.codeBlocks }} 个代码块中按白名单蒸馏，只统计真实命令行。</p>
          <ul class="atlas-bars">
            <li v-for="item in topCommandsShown" :key="item.cmd">
              <code class="atlas-mono atlas-bars__cmd">{{ item.cmd }}</code>
              <span class="atlas-bars__track"><span class="atlas-bars__fill" :style="{ width: barWidth(item.count) }"></span></span>
              <span class="atlas-bars__num">{{ item.count }}</span>
            </li>
          </ul>
        </section>
        <section class="atlas-panel" aria-label="蒸馏说明">
          <h2>这份快照怎么来的</h2>
          <ul class="atlas-list">
            <li><strong>蒸馏器</strong><span>scripts/atlas/distill-atlas.mjs，纯 Node 读取，输出 schemaVersion {{ snapshot.schemaVersion }} 快照</span></li>
            <li><strong>文档骨架</strong><span>每篇取 1-3 级标题（最多 8 条）作为主题标签</span></li>
            <li><strong>命令统计</strong><span>只统计 fenced code block 内、命中白名单的命令行；sudo 前缀归并到真实命令</span></li>
            <li><strong>边界</strong><span>快照是只读蒸馏，不运行语料里的命令；页面不把快照冒充实时数据</span></li>
          </ul>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import snapshot from './atlasDistilled.json'

const COURSE_COLORS = ['#2563eb', '#0e7490', '#b45309', '#7c3aed', '#64748b', '#9a3412']

const canvasEl = ref(null)
const canvasBox = ref(null)
const hoverId = ref(null)
const selectedDocId = ref(null)
const selectedCourseId = ref(null)

const isEmpty = computed(() => !snapshot || snapshot.totals.documents === 0)
const snapshotTime = computed(() => new Date(snapshot.generatedAt).toLocaleString('zh-CN', { hour12: false }))
const selectedDoc = computed(() => snapshot.documents.find(doc => doc.id === selectedDocId.value) ?? null)
const selectedCourse = computed(() => snapshot.courses.find(course => course.id === selectedCourseId.value) ?? null)
const topCommandsShown = computed(() => snapshot.topCommands.slice(0, 12))
const maxCommandCount = computed(() => topCommandsShown.value[0]?.count ?? 1)

const courseIdList = snapshot.courses.map(course => course.id)
const courseColor = id => COURSE_COLORS[Math.max(0, courseIdList.indexOf(id)) % COURSE_COLORS.length]
const formatChars = chars => chars >= 10000 ? `${(chars / 10000).toFixed(1)} 万字` : `${chars} 字`
const barWidth = count => `${Math.max(4, Math.round((count / maxCommandCount.value) * 100))}%`

function toggleCourse(id) {
  selectedCourseId.value = selectedCourseId.value === id ? null : id
  drawGraph()
}
function clearFilter() {
  selectedCourseId.value = null
  drawGraph()
}

/* ── 图谱布局（确定性旭日式布局，无物理模拟、无动画循环） ───────────── */

let layout = []

function buildLayout(width, height) {
  const margin = 48
  const R = Math.min(width, height) / 2 - margin
  const cx = width / 2
  const cy = height / 2
  const totalDocs = snapshot.documents.length
  const docAngle = (Math.PI * 2) / totalDocs
  const hubRadius = R * 0.42
  const docRadius = R * 0.8
  const maxChars = Math.max(...snapshot.courses.map(course => course.chars), 1)
  const maxDocChars = Math.max(...snapshot.documents.map(doc => doc.chars), 1)

  // 课程按 chars 降序（快照已排序）顺时针排扇区，扇区宽 = 文档数占比
  let cursor = -Math.PI / 2
  const nodes = []
  const edges = []
  const courseAngle = new Map()
  for (const course of snapshot.courses) {
    const span = docAngle * snapshot.documents.filter(doc => doc.courseId === course.id).length
    const mid = cursor + span / 2
    courseAngle.set(course.id, mid)
    const hubR = 14 + 20 * Math.sqrt(course.chars / maxChars)
    nodes.push({
      kind: 'course', id: `course:${course.id}`, course: course.id, label: course.label,
      x: cx + Math.cos(mid) * hubRadius, y: cy + Math.sin(mid) * hubRadius, r: hubR
    })
    cursor += span
  }
  let index = 0
  for (const doc of snapshot.documents) {
    const angle = -Math.PI / 2 + docAngle * (index + 0.5)
    const dotR = 3 + 4 * Math.sqrt(doc.chars / maxDocChars)
    const hub = nodes.find(node => node.kind === 'course' && node.course === doc.courseId)
    nodes.push({
      kind: 'doc', id: doc.id, course: doc.courseId, label: doc.title,
      x: cx + Math.cos(angle) * docRadius, y: cy + Math.sin(angle) * docRadius, r: dotR
    })
    if (hub) edges.push({ from: hub, to: nodes[nodes.length - 1], color: courseColor(doc.courseId) })
    index += 1
  }
  return { nodes, edges }
}

function nodeStyle(node) {
  const dimmed = selectedCourseId.value && node.course !== selectedCourseId.value
  const color = courseColor(node.course)
  const hovered = hoverId.value === node.id
  const active = node.kind === 'doc' && node.id === selectedDocId.value
  return {
    color,
    alpha: dimmed ? 0.15 : hovered || active ? 1 : node.kind === 'course' ? 0.9 : 0.75,
    halo: hovered || active
  }
}

function drawGraph() {
  const canvas = canvasEl.value
  const box = canvasBox.value
  if (!canvas || !box) return
  const dpr = window.devicePixelRatio || 1
  const rect = box.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  const width = Math.round(rect.width)
  const height = Math.round(rect.height)
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
  }
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)
  layout = buildLayout(width, height)

  // 连线：课程 → 文档
  for (const edge of layout.edges) {
    const dim = selectedCourseId.value && edge.from.course !== selectedCourseId.value
    ctx.globalAlpha = dim ? 0.05 : 0.3
    ctx.strokeStyle = edge.color
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(edge.from.x, edge.from.y)
    ctx.lineTo(edge.to.x, edge.to.y)
    ctx.stroke()
  }
  ctx.globalAlpha = 1

  for (const node of layout.nodes) {
    const style = nodeStyle(node)
    ctx.globalAlpha = style.alpha
    ctx.fillStyle = style.color
    if (style.halo) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, node.r + 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.globalAlpha = style.alpha * 0.35
    }
    ctx.beginPath()
    ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2)
    ctx.fill()
    // 课程节点常显标签；文档节点悬停/选中时才画标签，避免 60 个标签互相遮挡
    ctx.globalAlpha = style.alpha
    ctx.fillStyle = getComputedStyle(canvas).color || '#1f2937'
    ctx.font = node.kind === 'course' ? '600 12px system-ui, sans-serif' : '11px system-ui, sans-serif'
    if (node.kind === 'course') {
      ctx.textAlign = 'center'
      ctx.fillText(node.label, node.x, node.y - node.r - 8)
    } else if (style.halo) {
      ctx.textAlign = node.x > width / 2 ? 'left' : 'right'
      const text = node.label.length > 14 ? `${node.label.slice(0, 13)}…` : node.label
      ctx.fillText(text, node.x + (node.x > width / 2 ? node.r + 6 : -(node.r + 6)), node.y + 4)
    }
  }
  ctx.globalAlpha = 1
}

function pickNode(event) {
  const rect = canvasEl.value.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  // 文档节点优先（半径小，放上层判定）
  return [...layout.nodes].reverse().find(node => Math.hypot(node.x - x, node.y - y) <= node.r + 4) ?? null
}

function onHover(event) {
  const node = pickNode(event)
  const next = node ? node.id : null
  if (next !== hoverId.value) {
    hoverId.value = next
    canvasEl.value.style.cursor = node ? 'pointer' : 'default'
    drawGraph()
  }
}
function onLeave() {
  if (hoverId.value) {
    hoverId.value = null
    drawGraph()
  }
}
function onClick(event) {
  const node = pickNode(event)
  if (!node) return
  if (node.kind === 'doc') selectedDocId.value = selectedDocId.value === node.id ? null : node.id
  else toggleCourse(node.course)
  drawGraph()
}

/* ── 尺寸自适应（ResizeObserver 模板，无动画循环） ─────────────────── */

let resizeObserver = null
function handleResize() {
  if (canvasBox.value) drawGraph()
}

onMounted(() => {
  if (isEmpty.value) return
  drawGraph()
  resizeObserver = new ResizeObserver(handleResize)
  resizeObserver.observe(canvasBox.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<style scoped>
.atlas-page {
  display: grid;
  gap: 20px;
  color: var(--smart-text, #1f2937);
  padding-bottom: 32px;
}

.atlas-eyebrow {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--smart-primary-strong, #2563eb);
}

.atlas-head h1 { margin: 0 0 8px; font-size: 22px; }
.atlas-lede { margin: 0; max-width: 880px; font-size: 13.5px; line-height: 1.8; color: var(--smart-muted, #6b7280); }
.atlas-mono { font-family: var(--font-mono, Consolas, monospace); font-size: 12.5px; background: rgba(37, 99, 235, 0.08); padding: 1px 6px; border-radius: 4px; }
.atlas-muted { color: var(--smart-muted, #6b7280); }

.atlas-stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin: 0;
}

.atlas-stats > div {
  padding: 12px 16px;
  border: 1px solid var(--smart-border, #e5e7eb);
  border-radius: 10px;
  background: var(--smart-surface, #fff);
}

.atlas-stats dt { font-size: 12px; color: var(--smart-muted, #6b7280); }
.atlas-stats dd { margin: 4px 0 0; font-size: 22px; font-weight: 700; }

.atlas-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 344px;
  gap: 16px;
  align-items: start;
}

.atlas-canvas-panel {
  border: 1px solid var(--smart-border, #e5e7eb);
  border-radius: 12px;
  background: var(--smart-surface, #fff);
  overflow: hidden;
}

.atlas-canvas-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--smart-border, #e5e7eb);
  font-size: 13px;
}

.atlas-canvas-head strong { font-size: 14px; }
.atlas-canvas-head > span { margin-left: auto; font-size: 12.5px; }
.atlas-filter-note { color: var(--smart-primary-strong, #2563eb); }

.atlas-link-btn {
  border: 0;
  background: none;
  color: var(--smart-primary-strong, #2563eb);
  font-size: 12.5px;
  cursor: pointer;
  padding: 0 4px;
  text-decoration: underline;
}

.atlas-canvas-box { position: relative; height: 460px; }
.atlas-canvas-box canvas { display: block; width: 100%; height: 100%; }

.atlas-doc-panel {
  border-top: 1px solid var(--smart-border, #e5e7eb);
  padding: 12px 16px;
  display: grid;
  gap: 8px;
  font-size: 13px;
}

.atlas-doc-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.atlas-doc-path { margin: 0; font-size: 12px; }

.atlas-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.atlas-chip {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--smart-muted-soft, rgba(107, 114, 128, 0.1));
  color: var(--smart-muted, #6b7280);
}

.atlas-code-chip {
  font-family: var(--font-mono, Consolas, monospace);
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--smart-border, #e5e7eb);
  color: var(--smart-text, #1f2937);
}

.atlas-side { display: grid; gap: 12px; }

.atlas-course {
  border: 1px solid var(--smart-border, #e5e7eb);
  border-radius: 10px;
  padding: 12px 14px;
  display: grid;
  gap: 8px;
  cursor: pointer;
  background: var(--smart-surface, #fff);
}

.atlas-course--active { border-color: var(--smart-primary-strong, #2563eb); box-shadow: 0 0 0 1px var(--smart-primary-strong, #2563eb); }

.atlas-course__head { display: flex; align-items: center; gap: 8px; font-size: 13.5px; }
.atlas-course__head > span:last-child { margin-left: auto; font-size: 12px; }
.atlas-course p { margin: 0; font-size: 12.5px; }
.atlas-dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }

.atlas-bottom {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
}

.atlas-panel {
  border: 1px solid var(--smart-border, #e5e7eb);
  border-radius: 12px;
  background: var(--smart-surface, #fff);
  padding: 16px;
}

.atlas-panel h2 { margin: 0 0 4px; font-size: 15px; }
.atlas-panel > p { margin: 0 0 12px; font-size: 12.5px; }

.atlas-bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.atlas-bars li { display: grid; grid-template-columns: 110px 1fr 40px; align-items: center; gap: 10px; }
.atlas-bars__cmd { font-size: 12.5px; }
.atlas-bars__track { height: 8px; border-radius: 999px; background: var(--smart-muted-soft, rgba(107, 114, 128, 0.12)); overflow: hidden; }
.atlas-bars__fill { display: block; height: 100%; border-radius: 999px; background: var(--smart-primary-strong, #2563eb); }
.atlas-bars__num { font-size: 12.5px; text-align: right; font-variant-numeric: tabular-nums; }

.atlas-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.atlas-list li { display: grid; grid-template-columns: 88px 1fr; gap: 10px; font-size: 13px; line-height: 1.6; }
.atlas-list strong { font-size: 13px; }
.atlas-list span { color: var(--smart-muted, #6b7280); }

.atlas-empty {
  border: 1px dashed var(--smart-border-strong, #d1d5db);
  border-radius: 12px;
  padding: 32px;
  text-align: center;
}

.atlas-empty h3 { margin: 0 0 8px; }
.atlas-empty p { margin: 0; color: var(--smart-muted, #6b7280); font-size: 13px; }

@media (max-width: 1100px) {
  .atlas-main { grid-template-columns: 1fr; }
  .atlas-bottom { grid-template-columns: 1fr; }
  .atlas-stats { grid-template-columns: repeat(3, 1fr); }
  .atlas-canvas-box { height: 340px; }
}
</style>
