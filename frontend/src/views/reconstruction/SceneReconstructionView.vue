<template>
  <div class="rec-page">
    <header class="rec-head">
      <div>
        <p class="eyebrow">EXTENSIONS · SCENE RECONSTRUCTION</p>
        <h1>真实场景还原</h1>
        <p class="lede">
          把扫描件（点云 / 实景影像 / 网格模型）接入还原流水线，产出可被 3D 机房孪生页消费的场景。
          当前版本只完成 <b>素材接入与流程编排</b>，还原引擎尚未接入，不会伪造任何重建结果。
        </p>
      </div>
      <div class="rec-head__right">
        <span class="rec-badge rec-badge--off">还原引擎未接入</span>
        <span class="rec-badge">{{ totalSizeText }}</span>
      </div>
    </header>

    <div class="rec-grid">
      <section class="rec-panel">
        <h2>1 · 上传扫描素材</h2>
        <label
          class="rec-drop"
          :class="{ 'rec-drop--on': dragging }"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input
            ref="fileInput"
            class="rec-drop__input"
            type="file"
            multiple
            accept=".ply,.pcd,.las,.laz,.e57,.xyz,.glb,.gltf,.obj,.fbx,.stl,.jpg,.jpeg,.png,.tif,.tiff,.dng,.zip,.7z,.tar,.gz"
            @change="onPick"
          />
          <span class="rec-drop__title">拖入文件或点击选择</span>
          <span class="rec-drop__hint">
            点云 ply/pcd/las · 网格 glb/gltf/obj · 实景影像 jpg/png/tif · 压缩包 zip
          </span>
          <span class="rec-drop__limit">单文件上限 {{ maxSizeText }}</span>
        </label>

        <ul v-if="job.assets.length" class="rec-files">
          <li v-for="asset in job.assets" :key="asset.name">
            <span class="rec-files__kind">{{ asset.kindLabel }}</span>
            <span class="rec-files__name">{{ asset.name }}</span>
            <span class="rec-files__size">{{ formatBytes(asset.size) }}</span>
          </li>
        </ul>
        <ul v-if="job.rejected.length" class="rec-files rec-files--rejected">
          <li v-for="item in job.rejected" :key="item.name">
            <span class="rec-files__kind">已跳过</span>
            <span class="rec-files__name">{{ item.name }}</span>
            <span class="rec-files__size">{{ item.reason }}</span>
          </li>
        </ul>

        <div class="rec-actions">
          <button
            type="button"
            class="rec-btn rec-btn--primary"
            :disabled="!job.assets.length"
            @click="onStart"
          >开始还原</button>
          <button type="button" class="rec-btn" :disabled="!job.assets.length" @click="onClear">清空</button>
          <span class="rec-actions__note">
            覆盖度：{{ job.coverage.ready ? '具备几何来源' : job.coverage.reason || '尚未上传' }}
          </span>
        </div>
        <p v-if="notice" class="rec-note" :class="{ 'rec-note--warn': job.status === 'BLOCKED' }">{{ notice }}</p>
      </section>

      <section class="rec-panel rec-panel--preview">
        <h2>2 · 还原预览</h2>
        <div class="rec-preview" role="img" aria-label="还原预览占位区">
          <div class="rec-preview__grid"></div>
          <div class="rec-preview__body">
            <strong>占位预览</strong>
            <span>还原引擎接入后，这里渲染点云 / 网格重建结果</span>
            <span>当前不展示任何虚构几何</span>
          </div>
        </div>
        <ol class="rec-stages">
          <li v-for="stage in job.stages" :key="stage.key" :class="`is-${stage.status}`">
            <span class="rec-stages__dot"></span>
            <span class="rec-stages__body">
              <b>{{ stage.label }}</b>
              <small>{{ stage.detail }}</small>
            </span>
            <span class="rec-stages__state">{{ stageText(stage.status) }}</span>
          </li>
        </ol>
      </section>
    </div>

    <section class="rec-panel rec-panel--roadmap">
      <h2>3 · 与 3D 机房的衔接</h2>
      <div class="rec-roadmap">
        <div class="rec-roadmap__step">
          <b>扫描采集</b>
          <span>激光扫描仪 / 机器狗相机巡检，输出多站点云与影像</span>
        </div>
        <div class="rec-roadmap__arrow">→</div>
        <div class="rec-roadmap__step">
          <b>配准与重建</b>
          <span>多站点云配准、网格化，生成厂房与机柜几何</span>
        </div>
        <div class="rec-roadmap__arrow">→</div>
        <div class="rec-roadmap__step">
          <b>语义与传感绑定</b>
          <span>标注机柜/冷通道，绑定温度、湿度、功率点位</span>
        </div>
        <div class="rec-roadmap__arrow">→</div>
        <div class="rec-roadmap__step">
          <b>发布孪生</b>
          <span>发布后由「云服务器厂房 3D 孪生」页消费，延迟预算 2.5 秒</span>
        </div>
      </div>
      <p class="rec-note">
        发布前的实时演示可先看 <RouterLink to="/sentinel/twin">云服务器厂房 3D 孪生</RouterLink>（虚拟场景）。
      </p>
    </section>
  </div>
</template>

<script setup>
/**
 * SceneReconstructionView — 真实场景还原接入页
 *
 * 红线：还原引擎未接入时，页面只呈现「素材 + 流程 + 技术路线」，
 * 预览区明确标注占位，不渲染任何虚构的点云或网格。
 */
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  MAX_ASSET_BYTES,
  createReconstructionJob,
  formatBytes,
  startReconstruction
} from '../../domain/reconstruction/sceneReconstruction.js'

const fileInput = ref(null)
const dragging = ref(false)
const notice = ref('')
const job = ref(createReconstructionJob([]))

const maxSizeText = formatBytes(MAX_ASSET_BYTES)
const totalSizeText = computed(() => (
  job.value.assets.length ? `共 ${job.value.assets.length} 个素材 · ${formatBytes(job.value.totalBytes)}` : '尚未上传素材'
))

const STAGE_TEXT = { pending: '待执行', blocked: '依赖缺失', running: '进行中', done: '已完成' }
function stageText(status) {
  return STAGE_TEXT[status] || status
}

function ingest(fileList) {
  job.value = createReconstructionJob(fileList)
  notice.value = job.value.rejected.length
    ? `已跳过 ${job.value.rejected.length} 个文件，原因见下方列表`
    : ''
}

function onPick(event) {
  const files = event.target?.files
  if (files && files.length) ingest([...files])
  if (fileInput.value) fileInput.value.value = ''
}

function onDrop(event) {
  dragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length) ingest([...files])
}

function onStart() {
  const next = startReconstruction(job.value)
  job.value = next
  notice.value = next.notice || ''
}

function onClear() {
  job.value = createReconstructionJob([])
  notice.value = ''
}
</script>

<style scoped>
.rec-page {
  display: grid;
  gap: 16px;
  padding: 22px;
  color: var(--smart-text, #e8f2f7);
  background: var(--smart-bg, #071018);
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 12px;
}
.rec-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 14px; }
.eyebrow { margin: 0 0 6px; color: var(--smart-primary-strong, #7ad7f5); font: 11px ui-monospace, monospace; letter-spacing: .1em; }
.rec-head h1 { margin: 0; font-size: 26px; font-weight: 500; }
.lede { margin: 6px 0 0; max-width: 680px; color: var(--smart-muted, #92a6b5); font-size: 13px; line-height: 1.65; }
.lede b { color: var(--smart-text, #e8f2f7); font-weight: 600; }
.rec-head__right { display: flex; flex-wrap: wrap; gap: 8px; }
.rec-badge {
  padding: 6px 11px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 999px;
  color: var(--smart-muted, #92a6b5);
  font-size: 11px;
}
.rec-badge--off { color: #d9b96d; border-color: rgba(217, 185, 109, .35); }
.rec-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); gap: 14px; }
.rec-panel {
  display: grid;
  gap: 12px;
  align-content: start;
  padding: 16px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 10px;
  background: rgba(122, 215, 245, .03);
}
.rec-panel h2 { margin: 0; font-size: 12px; font-weight: 500; letter-spacing: .06em; color: var(--smart-muted, #92a6b5); }
.rec-drop {
  position: relative;
  display: grid;
  gap: 6px;
  justify-items: center;
  padding: 26px 16px;
  border: 1px dashed rgba(122, 215, 245, .35);
  border-radius: 10px;
  background: rgba(122, 215, 245, .03);
  text-align: center;
  cursor: pointer;
}
.rec-drop--on,
.rec-drop:focus-within { border-color: var(--smart-primary-strong, #7ad7f5); background: rgba(122, 215, 245, .1); }
/* 视觉隐藏而非 display:none：保留键盘可达性与读屏语义 */
.rec-drop__input {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}
.rec-drop__title { color: var(--smart-text, #e8f2f7); font-size: 13px; }
.rec-drop__hint { color: var(--smart-muted, #92a6b5); font-size: 11px; line-height: 1.6; }
.rec-drop__limit { color: var(--smart-muted, #92a6b5); font-size: 11px; }
.rec-files { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.rec-files li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 11px;
  background: rgba(255, 255, 255, .02);
}
.rec-files__kind { flex: 0 0 auto; color: var(--smart-primary-strong, #7ad7f5); }
.rec-files__name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rec-files__size { flex: 0 0 auto; color: var(--smart-muted, #92a6b5); }
.rec-files--rejected li { background: rgba(217, 185, 109, .07); }
.rec-files--rejected .rec-files__kind { color: #d9b96d; }
.rec-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.rec-actions__note { color: var(--smart-muted, #92a6b5); font-size: 11px; }
.rec-btn {
  padding: 6px 14px;
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 8px;
  background: transparent;
  color: var(--smart-text, #e8f2f7);
  font-size: 12px;
  cursor: pointer;
}
.rec-btn:disabled { opacity: .45; cursor: not-allowed; }
.rec-btn--primary { border-color: rgba(122, 215, 245, .45); color: var(--smart-primary-strong, #7ad7f5); }
.rec-note { margin: 0; color: var(--smart-muted, #92a6b5); font-size: 11px; line-height: 1.7; }
.rec-note--warn { color: #d9b96d; }
.rec-preview {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 220px;
  border: 1px solid rgba(159, 190, 207, .18);
  border-radius: 10px;
  overflow: hidden;
}
.rec-preview__grid {
  position: absolute;
  inset: -20%;
  background-image:
    linear-gradient(rgba(122, 215, 245, .1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(122, 215, 245, .1) 1px, transparent 1px);
  background-size: 28px 28px;
  transform: perspective(420px) rotateX(58deg);
  opacity: .7;
}
.rec-preview__body {
  position: relative;
  display: grid;
  gap: 4px;
  text-align: center;
  padding: 14px;
}
.rec-preview__body strong { color: #d9b96d; font-size: 13px; font-weight: 500; }
.rec-preview__body span { color: var(--smart-muted, #92a6b5); font-size: 11px; }
.rec-stages { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.rec-stages li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 7px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .02);
}
.rec-stages__dot { flex: 0 0 auto; width: 8px; height: 8px; margin-top: 5px; border-radius: 50%; background: #4a5b66; }
.rec-stages__body { display: grid; gap: 2px; flex: 1; min-width: 0; }
.rec-stages__body b { font-size: 12px; font-weight: 500; }
.rec-stages__body small { color: var(--smart-muted, #92a6b5); font-size: 11px; line-height: 1.5; }
.rec-stages__state { flex: 0 0 auto; color: var(--smart-muted, #92a6b5); font-size: 11px; }
.rec-stages li.is-blocked .rec-stages__dot { background: #d9b96d; }
.rec-stages li.is-blocked .rec-stages__state { color: #d9b96d; }
.rec-stages li.is-done .rec-stages__dot { background: #8bcfb4; }
.rec-stages li.is-done .rec-stages__state { color: #8bcfb4; }
.rec-stages li.is-running .rec-stages__dot { background: #7ad7f5; }
.rec-roadmap { display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; }
.rec-roadmap__step {
  flex: 1 1 180px;
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(159, 190, 207, .14);
  border-radius: 8px;
  background: rgba(255, 255, 255, .02);
}
.rec-roadmap__step b { font-size: 12px; font-weight: 500; color: var(--smart-primary-strong, #7ad7f5); }
.rec-roadmap__step span { color: var(--smart-muted, #92a6b5); font-size: 11px; line-height: 1.6; }
.rec-roadmap__arrow { align-self: center; color: var(--smart-muted, #92a6b5); font-size: 12px; }
@media (max-width: 980px) {
  .rec-grid { grid-template-columns: minmax(0, 1fr); }
  .rec-roadmap__arrow { display: none; }
}
</style>
