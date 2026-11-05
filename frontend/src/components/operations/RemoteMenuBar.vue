<template>
  <nav class="remote-menu" aria-label="远程运维菜单栏">
    <button type="button" @click="$emit('open-dialog', 'terminal')">终端</button>
    <button type="button" @click="$emit('open-dialog', 'session')">会话</button>
    <button type="button" @click="$emit('open-dialog', 'view')">视图</button>
    <button type="button" @click="$emit('open-dialog', 'xserver')">X服务器</button>
    <button type="button" @click="$emit('open-dialog', 'tools')">工具</button>
    <button type="button" @click="$emit('open-dialog', 'settings')">设置</button>
    <button type="button" @click="$emit('open-dialog', 'macros')">宏</button>
    <button type="button" @click="$emit('open-dialog', 'help')">帮助</button>
  </nav>
</template>

<script setup>
defineEmits(['open-dialog'])
</script>

<style scoped>
.remote-menu{display:flex;align-items:center;gap:0;min-height:30px;padding:0 5px;border:1px solid var(--smart-border);border-bottom:0;background:var(--smart-surface);overflow-x:auto}.remote-menu button{min-height:29px;padding:3px 10px;border:0;background:transparent;color:var(--smart-muted);font:12px var(--font-cn);cursor:pointer;white-space:nowrap}.remote-menu button:hover,.remote-menu button:focus-visible{background:color-mix(in srgb,var(--smart-primary-strong) 10%,transparent);color:var(--smart-text);outline:none}
@media(max-width:760px){.remote-menu button{padding-inline:8px}}
</style>
