<template>
  <div v-if="open" class="snippets-overlay" @click.self="$emit('close')">
    <div class="snippets-dialog" role="dialog" aria-modal="true" aria-label="命令片段库">
      <header class="snippets-header">
        <div>
          <h2>命令片段</h2>
          <p>对标 MobaXterm macros：保存常用命令，一键回填或发送到当前终端。仅保存在本机浏览器。</p>
        </div>
        <button type="button" class="close-btn" aria-label="关闭命令片段库" @click="$emit('close')">×</button>
      </header>

      <div v-if="!runtimeId" class="snippets-hint" role="status">没有在线终端：可以先维护片段列表，连接后「回填 / 执行」可用。</div>

      <ul v-if="snippets.length" class="snippet-list">
        <li v-for="snippet in snippets" :key="snippet.id">
          <div class="snippet-copy">
            <strong>{{ snippet.name }}</strong>
            <code>{{ snippet.command }}</code>
          </div>
          <div class="snippet-actions">
            <button type="button" :disabled="!runtimeId" title="把命令文本写入终端（不执行）" @click="fill(snippet)">回填</button>
            <button type="button" :disabled="!runtimeId" title="写入并按回车执行（需确认）" @click="run(snippet)">执行</button>
            <button type="button" class="ghost" @click="startEdit(snippet)">编辑</button>
            <button type="button" class="danger" @click="destroy(snippet)">删除</button>
          </div>
        </li>
      </ul>
      <p v-else class="snippets-hint">还没有片段。把常用命令（如 systemctl status smartops）保存到这里，避免重复敲。</p>

      <form class="snippet-form" @submit.prevent="submit">
        <label>名称<input v-model="form.name" type="text" maxlength="60" placeholder="如：查看服务状态" /></label>
        <label>命令<textarea v-model="form.command" rows="3" placeholder="支持多行；回填不执行，执行会发送回车" /></label>
        <div class="form-actions">
          <button type="submit" class="primary" :disabled="!formValid">{{ editing ? '保存修改' : '添加片段' }}</button>
          <button v-if="editing" type="button" @click="cancelEdit">取消编辑</button>
          <span v-if="notice" class="form-notice" role="status">{{ notice }}</span>
        </div>
      </form>
    </div>
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { loadSnippets, removeSnippet, saveSnippets, upsertSnippet } from './snippetStore.js'
import { writeToTerminal } from './terminalInputBus.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  runtimeId: { type: String, default: '' }
})

const snippets = ref(loadSnippets())
const form = ref({ id: '', name: '', command: '' })
const editing = ref(false)
const notice = ref('')

const formValid = computed(() => form.value.name.trim() && form.value.command.trim())

watch(() => props.open, value => { if (!value) { editing.value = false; notice.value = ''; form.value = { id: '', name: '', command: '' } } })

function persist() {
  if (!saveSnippets(snippets.value)) notice.value = '保存失败：浏览器存储不可用'
}

function submit() {
  if (!formValid.value) return
  snippets.value = upsertSnippet(snippets.value, form.value)
  persist()
  editing.value = false
  form.value = { id: '', name: '', command: '' }
}

function startEdit(snippet) {
  editing.value = true
  form.value = { id: snippet.id, name: snippet.name, command: snippet.command }
}

function cancelEdit() {
  editing.value = false
  form.value = { id: '', name: '', command: '' }
}

function destroy(snippet) {
  snippets.value = removeSnippet(snippets.value, snippet.id)
  persist()
}

function fill(snippet) {
  if (!props.runtimeId) return
  notice.value = writeToTerminal(props.runtimeId, snippet.command) ? `已回填「${snippet.name}」，回车前请再检查一遍。` : '发送失败：终端可能已断开'
}

function run(snippet) {
  if (!props.runtimeId) return
  if (!window.confirm(`向当前终端发送并执行「${snippet.name}」？\n\n${snippet.command}`)) return
  notice.value = writeToTerminal(props.runtimeId, `${snippet.command}\r`) ? `已发送「${snippet.name}」` : '发送失败：终端可能已断开'
}
</script>
<style scoped>
.snippets-overlay { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; background: rgba(2,6,10,.62); }
.snippets-dialog { display: grid; gap: 14px; width: min(640px, calc(100vw - 40px)); max-height: min(80vh, 640px); overflow-y: auto; padding: 20px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface-raised); }
.snippets-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.snippets-header h2 { margin: 0; color: var(--smart-text); font-size: 15px; font-weight: 550; }
.snippets-header p { margin: 6px 0 0; color: var(--smart-muted); font-size: 11px; }
.close-btn { width: 32px; height: 32px; border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-muted); font-size: 16px; cursor: pointer; }
.snippet-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.snippet-list li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px; border: 1px solid var(--smart-border); }
.snippet-copy { display: grid; min-width: 0; gap: 4px; }
.snippet-copy strong { color: var(--smart-text); font-size: 12px; }
.snippet-copy code { overflow: hidden; color: var(--smart-muted); font: 11px var(--font-mono); text-overflow: ellipsis; white-space: pre-wrap; overflow-wrap: anywhere; }
.snippet-actions { display: flex; flex-shrink: 0; gap: 4px; }
.snippet-actions button, .form-actions button { min-height: 28px; padding: 0 9px; border: 1px solid var(--smart-border-strong); background: transparent; color: var(--smart-text); font: 11px var(--font-cn); cursor: pointer; }
.snippet-actions button:disabled { opacity: .4; cursor: not-allowed; }
.snippet-actions button:not(:disabled):hover, .form-actions button:not(:disabled):hover { border-color: var(--smart-primary-strong); color: var(--smart-primary-strong); }
.snippet-actions .danger:hover { border-color: var(--ds-semantic-danger); color: var(--ds-semantic-danger); }
.snippet-actions .ghost { color: var(--smart-muted); }
.snippets-hint { color: var(--smart-muted); font-size: 11px; line-height: 1.6; }
.snippet-form { display: grid; gap: 8px; padding-top: 12px; border-top: 1px solid var(--smart-border); }
.snippet-form label { display: grid; gap: 4px; color: var(--smart-muted); font-size: 11px; }
.snippet-form input, .snippet-form textarea { padding: 7px 9px; border: 1px solid var(--smart-border-strong); background: var(--smart-surface); color: var(--smart-text); font: 12px var(--font-cn); outline: none; }
.snippet-form input:focus, .snippet-form textarea:focus { border-color: var(--smart-primary-strong); }
.snippet-form textarea { font-family: var(--font-mono); resize: vertical; }
.form-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.form-actions .primary { border-color: color-mix(in srgb, var(--smart-success) 50%, var(--smart-border-strong)); color: color-mix(in srgb, var(--smart-success) 55%, var(--smart-text)); }
.form-notice { color: var(--smart-warning); font-size: 11px; }
@media (max-width: 640px) { .snippet-list li { flex-direction: column; align-items: stretch; } }
</style>
