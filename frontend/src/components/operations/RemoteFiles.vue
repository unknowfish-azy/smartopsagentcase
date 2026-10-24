<template>
  <section class="remote-files">
    <h3>远程文件 / {{ sessionName }}</h3>
    <form @submit.prevent="load"><label>目录 <input v-model="path" :disabled="busy" /></label><button :disabled="busy">打开 / 刷新</button></form>
    <p>仅按指定目录读取。上传可能覆盖同名文件。</p>
    <label>上传文件 <input type="file" :disabled="busy || !loaded" @change="upload" /></label>
    <p role="status">{{ status }}</p>
    <p v-if="error" role="alert">{{ error }} <button :disabled="busy" @click="load">重试</button></p>
    <p v-if="loaded && !busy && !error && !files.length">此目录暂无文件</p>
    <table v-if="files.length"><thead><tr><th>名称</th><th>大小</th><th>操作</th></tr></thead>
      <tbody><tr v-for="file in files" :key="file.path"><td>{{ file.name }}</td><td>{{ file.directory ? '目录' : `${file.size} B` }}</td><td><button :disabled="busy" @click="open(file)">{{ file.directory ? '打开目录' : '下载' }}</button></td></tr></tbody>
    </table>
  </section>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { listRemoteFiles, downloadRemoteFile, uploadRemoteFile } from '../../api/operations.js'
import { remoteChild } from './connectionWorkspace.js'
const props = defineProps({ runtimeId: String, sessionName: String })
const path = ref('.'), files = ref([]), busy = ref(false), error = ref(''), status = ref(''), loaded = ref(false)
let loadedPath = '.'
async function load() {
  if (busy.value) return
  busy.value = true; loaded.value = false; error.value = ''; status.value = '正在读取目录…'; files.value = []
  const requestedPath = path.value
  try {
    const response = await listRemoteFiles(props.runtimeId, requestedPath)
    const result = response.data ?? response
    if (!Array.isArray(result)) throw new Error('文件列表格式异常')
    files.value = result; loadedPath = requestedPath; loaded.value = true; status.value = `${result.length} 项`
  } catch (ex) { error.value = ex.message; status.value = '' }
  finally { busy.value = false }
}
async function open(file) {
  if (file.directory) { path.value = file.path; return load() }
  if (!window.confirm(`下载 ${props.sessionName}:${file.path}？请确认允许读取此文件。`)) return
  busy.value = true; error.value = ''; status.value = '正在下载…'
  try {
    const blob = await downloadRemoteFile(props.runtimeId, file.path)
    const url = URL.createObjectURL(blob); const link = document.createElement('a')
    link.href = url; link.download = file.name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    status.value = '文件已交给浏览器下载'
  } catch (ex) { error.value = ex.message; status.value = '下载失败' }
  finally { busy.value = false }
}
async function upload(event) {
  const file = event.target.files?.[0]; event.target.value = ''
  if (!file) return
  let target
  try { target = remoteChild(loadedPath, file.name) } catch (ex) { error.value = ex.message; return }
  if (!window.confirm(`上传至 ${props.sessionName}:${target}？将覆盖同名文件，请确认备份。`)) return
  busy.value = true; error.value = ''; status.value = '正在上传…'
  try {
    await uploadRemoteFile(props.runtimeId, target, file, progress => {
      status.value = progress.total ? `已发送 ${Math.floor(progress.loaded / progress.total * 100)}%，等待服务端确认` : `已发送 ${progress.loaded} 字节`
    })
    status.value = '上传完成，请刷新目录核对文件'
  } catch (ex) { error.value = ex.message; status.value = '上传失败，目标可能存在部分文件，请检查' }
  finally { busy.value = false }
}
onMounted(load)
</script>
<style scoped>
.remote-files { padding:16px; color:#e8f2f7; background:#071018; overflow:auto; }
form { display:flex; flex-wrap:wrap; gap:8px; } input,button { max-width:100%; color:inherit; background:#0a1118; border:1px solid #526575; padding:7px; } p { color:#a8bbc8; font-size:12px; } table { width:100%; text-align:left; border-collapse:collapse; } td,th { padding:8px; border-bottom:1px solid #263541; overflow-wrap:anywhere; } [role=alert] { color:#fca5a5; }
</style>
