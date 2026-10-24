<template><section class="health-center"><header><p class="editorial-label">SERVICE DIAGNOSTICS / 健康诊断</p><h1>配置非<span class="h1-key">证据</span></h1><p>只显示当前账号有权查看的证据；未执行主动检查的服务不会被标记为正常。</p></header><HealthCheckList /><section class="tool-stack"><NetworkDiagnosticTool /><NetworkDiagnosticTool certificate-mode /><ConfigDiffTool /></section></section></template>
<script setup>
import HealthCheckList from '../../components/diagnostics/HealthCheckList.vue'
import NetworkDiagnosticTool from '../../components/diagnostics/NetworkDiagnosticTool.vue'
import ConfigDiffTool from '../../components/diagnostics/ConfigDiffTool.vue'
</script>
<style scoped>.health-center{max-width:1100px;margin:0 auto;padding:48px 0 70px;color:var(--smart-text)}.health-center header h1{max-width:700px;margin:16px 0 12px;font:400 clamp(2.4rem,5vw,5rem)/.95 var(--font-display);letter-spacing:-.04em;text-wrap:balance}.health-center header h1 .h1-key{color:var(--smart-primary-strong)}.health-center header>p:not(.editorial-label){max-width:680px;color:var(--smart-muted);line-height:1.7}.editorial-label{color:var(--smart-primary-strong);font:10px var(--font-mono);letter-spacing:.13em}.tool-stack{display:grid;gap:18px;margin-top:18px}@media(max-width:767px){.health-center{padding:28px 0 50px}.health-center header h1{font-size:clamp(2.2rem,12vw,4rem)}}
</style>
