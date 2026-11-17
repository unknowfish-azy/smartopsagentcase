<template>
  <div class="sciverse-page">
    <header class="sv-head">
      <div>
        <p class="eyebrow">SCIVERSE INGEST · 科学文献蒸馏</p>
        <h1>SciVerse 文献接入</h1>
        <p class="lede">
          对接 SciVerse Sci-Base 层：输入蒸馏主题，平台做语义检索返回
          <b>证据片段 + 原文定位</b>，勾选后一键蒸馏入库生成知识候选，人工审核后进入知识库。
        </p>
      </div>
      <div class="sv-head__right">
        <div class="sv-status" :class="statusConfigured ? 'sv-status--ok' : 'sv-status--off'">
          <i></i>{{ statusConfigured ? '平台已接入' : '未配置 API Key' }}
        </div>
        <button type="button" class="sv-mini" @click="keyPanelOpen = !keyPanelOpen">
          {{ keyPanelOpen ? '收起配置' : '配置密钥' }}
        </button>
      </div>
    </header>

    <section class="sv-search" aria-label="蒸馏检索">
      <input
        v-model="query"
        class="sv-search__input"
        type="text"
        placeholder="蒸馏主题，如：大模型辅助根因定位 的研究进展"
        @keyup.enter="doSearch"
      />
      <button type="button" class="sv-search__btn" :disabled="busy || !query.trim()" @click="doSearch">
        {{ busy ? '检索中…' : '语义检索' }}
      </button>
    </section>

    <section v-if="keyPanelOpen" class="sv-keypanel" aria-label="配置文献密钥">
      <div class="sv-keypanel__row">
        <span class="sv-keypanel__label">当前密钥</span>
        <code>{{ statusKeyPreview || '未配置' }}</code>
        <span class="sv-keypanel__label">长期保存</span>
        <span :class="statusPersistent ? 'sv-keypanel__ok' : 'sv-keypanel__warn'">
          {{ statusPersistent ? '已写入后端 .env.local，重启后仍生效' : '未持久化（仅当前进程生效）' }}
        </span>
      </div>
      <div class="sv-keypanel__row">
        <input
          v-model="keyValue"
          class="sv-search__input sv-keypanel__input"
          type="password"
          autocomplete="off"
          placeholder="粘贴 SciVerse 控制台密钥（sci_ 开头）"
          @keyup.enter="doSaveKey"
        />
        <button
          type="button"
          class="sv-search__btn"
          :disabled="keySaving || !keyValue.trim()"
          @click="doSaveKey"
        >{{ keySaving ? '保存中…' : '保存密钥' }}</button>
      </div>
      <p class="sv-hint">
        密钥只在本地后端落盘（<code>backend/.env.local</code>，已 gitignore），不经第三方转发；
        保存后立即生效，无需重启。密钥来源：<a href="https://sciverse.opendatalab.com/tokens" target="_blank" rel="noreferrer">SciVerse 控制台「密钥」页</a>。
      </p>
      <p v-if="keyError" class="sv-note sv-note--warn">{{ keyError }}</p>
    </section>

    <p v-if="!statusConfigured && statusLoaded" class="sv-note sv-note--warn">
      后端未配置 <code>SMARTOPS_SCIVERSE_API_KEY</code>：到 SciVerse 控制台「密钥」创建 API Key（sci_ 开头）后，
      点右上角「配置密钥」粘贴保存即可启用，无需重启后端。
    </p>
    <p v-if="notice" class="sv-note">{{ notice }}</p>

    <section v-if="evidences.length" class="sv-results" aria-label="检索证据">
      <div class="sv-results__bar">
        <span>证据 {{ evidences.length }} 条 · 已选 {{ selected.size }}</span>
        <div>
          <button type="button" class="sv-mini" @click="toggleAll">{{ allSelected ? '全不选' : '全选' }}</button>
          <button
            type="button"
            class="sv-mini sv-mini--primary"
            :disabled="!selected.size || ingesting"
            @click="doIngest"
          >{{ ingesting ? '蒸馏中…' : '蒸馏入库 →' }}</button>
        </div>
      </div>
      <label v-for="item in evidences" :key="item.index" class="sv-card" :class="{ 'sv-card--on': selected.has(item.index) }">
        <input type="checkbox" class="sv-card__check" :checked="selected.has(item.index)" @change="toggle(item.index)" />
        <span class="sv-card__body">
          <strong class="sv-card__title">{{ item.title }}</strong>
          <span class="sv-card__meta">doc_id：<code>{{ item.docId || '—' }}</code> · 定位：<code>{{ item.locator || '—' }}</code></span>
          <span class="sv-card__text">{{ item.text }}</span>
        </span>
      </label>
      <p class="sv-hint">入库结果可在「知识审核」页查看，人工 promote 后进入个人知识库；重复证据自动幂等去重。</p>
    </section>

    <div v-if="toast" class="sv-toast" :class="{ 'sv-toast--on': toast }">{{ toast.msg }}</div>
  </div>
</template>

<script setup>
/**
 * KnowledgeSciverseView — SciVerse 科学文献蒸馏接入页
 *
 * 数据红线：只展示平台真实返回的证据片段与定位，不本地伪造任何文献内容；
 * 蒸馏入库走既有知识候选审核闸门（PENDING_REVIEW → promote），不直写知识库。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getSciverseStatus, searchSciverse, ingestSciverse, saveSciverseKey } from '../../api/operations.ts'
import { validateSciverseKey } from '../../domain/knowledge/sciverseKey.js'

const router = useRouter()

function unwrap(resp) {
  return resp && resp.data !== undefined ? resp.data : resp
}

const statusConfigured = ref(false)
const statusLoaded = ref(false)
const statusKeyPreview = ref('')
const statusPersistent = ref(false)

/* 手动配置密钥面板 */
const keyPanelOpen = ref(false)
const keyValue = ref('')
const keySaving = ref(false)
const keyError = ref('')

const query = ref('')
const busy = ref(false)
const ingesting = ref(false)
const evidences = ref([])
const selected = ref(new Set())
const notice = ref('')
const toast = ref(null)

const allSelected = computed(() => evidences.value.length > 0 && selected.value.size === evidences.value.length)

let toastTimer = null
function showToast(msg) {
  toast.value = { msg }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3200)
}

function applyStatus(status) {
  statusConfigured.value = Boolean(status?.configured)
  statusKeyPreview.value = status?.keyPreview || ''
  statusPersistent.value = Boolean(status?.persistent)
}

async function refreshStatus() {
  try {
    applyStatus(unwrap(await getSciverseStatus()))
  } catch {
    statusConfigured.value = false
    statusKeyPreview.value = ''
    statusPersistent.value = false
  } finally {
    statusLoaded.value = true
  }
}

onMounted(refreshStatus)

async function doSaveKey() {
  const check = validateSciverseKey(keyValue.value)
  if (!check.ok) {
    keyError.value = check.reason
    return
  }
  keySaving.value = true
  keyError.value = ''
  try {
    applyStatus(unwrap(await saveSciverseKey(check.value)))
    keyValue.value = ''
    keyPanelOpen.value = false
    showToast('密钥已保存并立即生效（长期保存至后端 .env.local）')
  } catch (error) {
    keyError.value = error?.response?.data?.message || error?.message || '保存失败，请稍后重试'
  } finally {
    keySaving.value = false
  }
}

async function doSearch() {
  const keyword = query.value.trim()
  // 只挡空输入与并发点击；不再因本地 status 状态拦截请求——
  // status 是页面加载时的快照，后端修复后会过期，拦下来会让用户看到「点了没反应」的假死。
  if (!keyword || busy.value) return
  busy.value = true
  notice.value = ''
  evidences.value = []
  selected.value = new Set()
  try {
    const result = unwrap(await searchSciverse(keyword, 8))
    evidences.value = Array.isArray(result?.evidences) ? result.evidences : []
    notice.value = result?.notice || ''
    // 徽标只由 /status 决定，不因单次检索失败翻转（旧实现会把「HTTP 404」误显示成「未配置 API Key」）。
  } catch (failure) {
    notice.value = `检索失败：${failure?.response?.data?.error || failure?.message || '未知错误'}`
  } finally {
    busy.value = false
  }
}

function toggle(index) {
  const next = new Set(selected.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  selected.value = next
}
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(evidences.value.map(item => item.index))
}

async function doIngest() {
  if (!selected.value.size || ingesting.value) return
  const picked = evidences.value.filter(item => selected.value.has(item.index))
  ingesting.value = true
  try {
    const result = unwrap(await ingestSciverse({ query: query.value.trim(), evidences: picked }))
    const created = result?.created ?? 0
    const duplicated = result?.duplicated ?? 0
    showToast(`蒸馏入库完成：新增 ${created} 条候选${duplicated ? `，幂等去重 ${duplicated} 条` : ''}`)
    evidences.value = []
    selected.value = new Set()
    setTimeout(() => router.push('/knowledge/review'), 1200)
  } catch (failure) {
    showToast(`入库失败：${failure?.response?.data?.error || failure?.message || '未知错误'}`)
  } finally {
    ingesting.value = false
  }
}
</script>

<style scoped>
.sciverse-page {
  display: grid;
  gap: 16px;
  padding: 22px;
  color: var(--smart-text, #e8f2f7);
  background: var(--smart-bg, #071018);
  border: 1px solid var(--smart-border, rgba(159, 190, 207, .18));
  border-radius: 12px;
}
.sv-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 14px; }
.eyebrow { margin: 0 0 6px; color: var(--smart-primary-strong, #7ad7f5); font: 11px ui-monospace, monospace; letter-spacing: .1em; }
.sv-head h1 { margin: 0; font-size: 26px; font-weight: 500; }
.lede { margin: 6px 0 0; color: var(--smart-muted, #92a6b5); font-size: 13px; line-height: 1.65; max-width: 640px; }
.lede b { color: var(--smart-text, #e8f2f7); font-weight: 600; }
.sv-status { display: inline-flex; align-items: center; gap: 7px; padding: 6px 12px; border-radius: 999px; font-size: 12px; border: 1px solid var(--smart-border, rgba(159, 190, 207, .18)); }
.sv-status i { width: 8px; height: 8px; border-radius: 50%; }
.sv-status--ok { color: #8bcfb4; } .sv-status--ok i { background: #8bcfb4; box-shadow: 0 0 8px #8bcfb4; }
.sv-status--off { color: #d9b96d; } .sv-status--off i { background: #d9b96d; }
.sv-head__right { display: flex; align-items: center; gap: 10px; }
/* 手动配置密钥面板 */
.sv-keypanel { display: grid; gap: 10px; padding: 14px 16px; border: 1px solid rgba(122, 215, 245, .25); border-radius: 10px; background: rgba(122, 215, 245, .04); }
.sv-keypanel__row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sv-keypanel__label { color: var(--smart-muted, #92a6b5); font-size: 12px; }
.sv-keypanel__row code { color: var(--smart-primary-strong, #7ad7f5); font-family: ui-monospace, monospace; font-size: 12px; }
.sv-keypanel__ok { color: #8bcfb4; font-size: 12px; }
.sv-keypanel__warn { color: #d9b96d; font-size: 12px; }
.sv-keypanel__input { flex: 1; min-width: 260px; }
.sv-hint { margin: 0; color: var(--smart-muted, #92a6b5); font-size: 12px; }
.sv-hint a { color: var(--smart-primary-strong, #7ad7f5); }
/* 检索条 */
.sv-search { display: flex; gap: 10px; }
.sv-search__input { flex: 1; padding: 11px 14px; border: 1px solid var(--smart-border-strong, rgba(159, 190, 207, .34)); border-radius: 9px; background: var(--smart-surface-raised, #0b1721); color: inherit; font-size: 14px; }
.sv-search__input:focus { outline: 2px solid var(--smart-focus-ring, #b8eeff); outline-offset: 1px; }
.sv-search__btn { padding: 11px 22px; border: 1px solid var(--smart-primary-strong, #7ad7f5); border-radius: 9px; background: var(--smart-primary-soft, rgba(122, 215, 245, .12)); color: var(--smart-primary-strong, #7ad7f5); font-size: 14px; cursor: pointer; }
.sv-search__btn:disabled { opacity: .45; cursor: not-allowed; }
/* 提示条 */
.sv-note { margin: 0; padding: 10px 14px; border-radius: 9px; border: 1px solid var(--smart-border, rgba(159, 190, 207, .18)); color: var(--smart-muted, #92a6b5); font-size: 13px; background: var(--smart-surface, #071018); }
.sv-note--warn { color: #d9b96d; border-color: rgba(217, 185, 109, .4); }
.sv-note code { color: var(--smart-primary-strong, #7ad7f5); font-family: ui-monospace, monospace; }
/* 证据卡 */
.sv-results { display: grid; gap: 10px; }
.sv-results__bar { display: flex; justify-content: space-between; align-items: center; color: var(--smart-muted, #92a6b5); font-size: 12px; }
.sv-results__bar > div { display: flex; gap: 8px; }
.sv-mini { padding: 6px 14px; border-radius: 8px; border: 1px solid var(--smart-border, rgba(159, 190, 207, .18)); background: transparent; color: var(--smart-muted, #92a6b5); font-size: 12px; cursor: pointer; }
.sv-mini--primary { color: var(--smart-primary-strong, #7ad7f5); border-color: var(--smart-primary-strong, #7ad7f5); }
.sv-mini:disabled { opacity: .4; cursor: not-allowed; }
.sv-card { display: flex; gap: 12px; padding: 14px; border: 1px solid var(--smart-border, rgba(159, 190, 207, .18)); border-radius: 10px; background: var(--smart-surface, #071018); cursor: pointer; transition: border-color 150ms ease; }
.sv-card--on { border-color: var(--smart-primary-strong, #7ad7f5); }
.sv-card__check { margin-top: 3px; }
.sv-card__body { display: grid; gap: 6px; }
.sv-card__title { font-size: 15px; font-weight: 600; }
.sv-card__meta { color: var(--smart-muted, #92a6b5); font-size: 12px; }
.sv-card__meta code { color: var(--smart-primary-strong, #7ad7f5); font-family: ui-monospace, monospace; }
.sv-card__text { color: var(--smart-text, #e8f2f7); font-size: 13px; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.sv-hint { margin: 0; color: var(--smart-muted, #92a6b5); font-size: 12px; }
/* toast */
.sv-toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); padding: 10px 20px; border-radius: 999px; background: var(--smart-surface-raised, #0b1721); border: 1px solid var(--smart-primary-strong, #7ad7f5); color: var(--smart-text, #e8f2f7); font-size: 13px; box-shadow: 0 10px 32px rgba(0, 0, 0, .4); z-index: 30; }
@media (max-width: 767px) { .sciverse-page { padding: 16px; } .sv-search { flex-direction: column; } }
@media (prefers-reduced-motion: reduce) { .sv-card, .sv-mini { transition: none; } }
</style>
