<template>
  <router-view />
</template>

<script setup>
import { provide } from 'vue'
import { createVoiceActionBus, VoiceActionBusSymbol } from './components/persona/voiceActionRegistry.js'

// 给语音控屏的按钮级动作总线：页面组件用 provide 注册，PersonaPet 用 resolve 匹配后 dispatch
const voiceActionBus = createVoiceActionBus()
provide(VoiceActionBusSymbol, voiceActionBus)
// 同时挂 globalThis 兜底，方便测试 / 非 Vue 上下文
globalThis.__voice_action_bus__ = voiceActionBus
</script>