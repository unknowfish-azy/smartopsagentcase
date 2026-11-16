<template>
  <section class="terminal-shell">
    <header><span>{{ sessionName }}</span><span>{{ status }}</span>
      <span v-if="recording" class="record-indicator" role="status">● 录制中 {{ recordedSize }}</span>
      <span class="header-actions">
        <button v-if="!recording" @click="startRecording">录制</button>
        <button v-else @click="stopRecording">停止录制</button>
        <button :disabled="!recorded.length || recording" @click="exportRecording">导出日志</button>
        <button @click="terminal?.clear()">清屏</button>
      </span>
    </header>
    <div ref="host" class="terminal-host" :aria-label="`${sessionName} 终端`"></div>
  </section>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { terminalEndpoint } from './connectionWorkspace.js'
import { registerTerminalInput, unregisterTerminalInput } from './terminalInputBus.js'
import '@xterm/xterm/css/xterm.css'
const props = defineProps({ runtimeId: { type: String, required: true }, sessionName: String })
const emit = defineEmits(['status'])
const host = ref(null), status = ref('正在连接终端')
const recording = ref(false)
const recorded = ref([])
const recordedSize = computed(() => {
  const bytes = recorded.value.reduce((sum, chunk) => sum + (chunk?.length || 0), 0)
  return bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`
})
let terminal, socket, observer, frame, disposed = false
function setStatus(value) { status.value = value; emit('status', value) }
function startRecording() { recorded.value = []; recording.value = true }
function stopRecording() { recording.value = false }
function exportRecording() {
  if (!recorded.value.length) return
  const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
  const blob = new Blob(recorded.value, { type: 'text/plain;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${props.sessionName || 'terminal'}-${stamp}.log`
  link.click()
  URL.revokeObjectURL(link.href)
}
onMounted(() => {
  terminal = new Terminal({ fontSize: 13, scrollback: 5000, fontFamily: 'Consolas, monospace', theme: { background: '#05090d', foreground: '#e8f2f7', cursor: '#7ad7f5' } })
  const fit = new FitAddon()
  terminal.loadAddon(fit); terminal.open(host.value)
  const backend = globalThis.__SMARTOPS_BRIDGE_WS__ || (import.meta.env.DEV ? '' : import.meta.env.VITE_API_BASE_URL)
  socket = new WebSocket(terminalEndpoint(backend, location.origin))
  const send = (type, extra = {}) => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type, runtimeId: props.runtimeId, ...extra })) }
  registerTerminalInput(props.runtimeId, send)
  const resize = () => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(() => {
      if (!host.value?.clientWidth || !host.value?.clientHeight) return
      fit.fit(); send('RESIZE', { columns: terminal.cols, rows: terminal.rows })
    })
  }
  socket.addEventListener('open', () => { send('OPEN'); resize() })
  socket.addEventListener('message', event => {
    if (disposed) return
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'OUTPUT') {
        terminal.write(message.data || '')
        if (recording.value && message.data) recorded.value.push(message.data)
      }
      if (message.type === 'STATUS') setStatus(message.data === 'ONLINE' ? '在线' : message.data)
      if (message.type === 'ERROR') { setStatus('异常'); terminal.writeln(`\r\n[${message.data || '桥接异常'}]`) }
      if (message.type === 'EXIT') setStatus('已结束')
    } catch { setStatus('输出格式异常') }
  })
  socket.addEventListener('close', () => { if (!disposed) { setStatus('已断开'); terminal.writeln('\r\n[连接已断开，输出已保留，请重新连接]') } })
  socket.addEventListener('error', () => { if (!disposed) setStatus('连接异常') })
  terminal.onData(data => send('INPUT', { data }))
  observer = new ResizeObserver(resize); observer.observe(host.value); resize()
})
onBeforeUnmount(() => { disposed = true; unregisterTerminalInput(props.runtimeId); observer?.disconnect(); cancelAnimationFrame(frame); socket?.close(); terminal?.dispose() })
</script>
<style scoped>
.terminal-shell { min-width:0; background:#05090d; border:1px solid #18222d; }
header { display:flex; flex-wrap:wrap; gap:12px; padding:8px; font-size:12px; color:#a8bbc8; }
.header-actions { margin-left:auto; display:flex; gap:6px; }
header button { color:inherit; background:none; border:1px solid #526575; cursor:pointer; }
header button:disabled { opacity:.4; cursor:not-allowed; }
.record-indicator { color:#ff8a80; font-size:11px; }
.terminal-host { height:400px; padding:8px; min-width:0; }
</style>
