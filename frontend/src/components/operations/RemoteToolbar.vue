<template>
  <nav class="remote-toolbar" aria-label="远程运维工具栏">
    <button type="button" title="新建会话" @click="$emit('open-dialog', 'session')"><Monitor /><span>会话</span></button>
    <button type="button" title="服务器与连接资源" @click="$emit('open-dialog', 'server')"><User /><span>服务器</span></button>
    <button type="button" title="远程工具" @click="$emit('open-dialog', 'tools')"><Tools /><span>工具</span></button>
    <button type="button" title="最近会话" @click="$emit('open-dialog', 'favorites')"><Star /><span>我的会话</span></button>
    <button type="button" title="工作区视图" @click="$emit('open-dialog', 'view')"><View /><span>视图</span></button>
    <button type="button" title="切换分屏" @click="$emit('open-dialog', 'split')"><FullScreen /><span>分屏</span></button>
    <button type="button" title="批量执行" @click="$emit('open-dialog', 'multi-exec')"><Switch /><span>多重执行</span></button>
    <button type="button" title="SSH 隧道" @click="$emit('open-dialog', 'tunnel')"><Connection /><span>隧道</span></button>
    <button type="button" title="远程文件" @click="$emit('open-dialog', 'files')"><Folder /><span>文件</span></button>
    <button type="button" title="连接设置" @click="$emit('open-dialog', 'settings')"><Setting /><span>设置</span></button>
    <button type="button" title="使用帮助" @click="$emit('open-dialog', 'help')"><QuestionFilled /><span>帮助</span></button>
  </nav>
</template>

<script setup>
import { Connection, Folder, FullScreen, Monitor, QuestionFilled, Setting, Star, Switch, Tools, User, View } from '@element-plus/icons-vue'

defineEmits(['open-dialog'])
</script>

<style scoped>
.remote-toolbar{display:flex;align-items:stretch;gap:2px;padding:8px 10px;border:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 92%,transparent);overflow-x:auto}.remote-toolbar button{display:grid;justify-items:center;gap:4px;min-width:70px;padding:6px 11px;border:0;border-right:1px solid var(--smart-border);background:transparent;color:var(--smart-muted);font:10px var(--font-cn);cursor:pointer;white-space:nowrap}.remote-toolbar button:hover,.remote-toolbar button:focus-visible{color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 8%,transparent);outline:none}.remote-toolbar button:disabled{opacity:.35;cursor:not-allowed}.remote-toolbar svg{width:22px;height:22px;color:var(--smart-primary-strong)}
@media(max-width:760px){.remote-toolbar button{min-width:58px;padding-inline:7px}}
</style>
