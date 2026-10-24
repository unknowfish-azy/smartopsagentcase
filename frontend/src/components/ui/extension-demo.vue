<template>
  <section class="extension-demo">
    <div class="demo-toggle"><p>{{ isPlugin ? '体验插件如何组织运维能力' : '体验 Skill 如何明确 Agent 的目标' }}</p><button type="button" :aria-expanded="open" @click="open = !open">{{ open ? '收起虚构案例' : '查看虚构案例' }}</button></div>
    <div v-if="open" class="demo-content">
      <span class="demo-badge">演示模式 · 虚构案例</span><h2>{{ isPlugin ? '星桥 · Nginx 故障证据插件' : 'nginx-incident-coach · 排障教练 Skill' }}</h2><p>模拟场景：订单服务发布后出现 Nginx 502，需要收集证据、缩小范围并生成排查建议。</p>
      <div class="demo-columns">
        <article><h3>{{ isPlugin ? '插件档案' : '任务目标与验收' }}</h3>
          <template v-if="isPlugin"><dl><dt>版本</dt><dd>1.2.0（虚构）</dd><dt>分类</dt><dd>诊断分析</dd><dt>能力依赖</dt><dd>运维知识引擎、远程连接工作台</dd><dt>提供能力</dt><dd>日志线索归类、上游检查清单、证据摘要</dd></dl><p>设想的插件将日志与连接观察组织为证据包，供 Agent 分析。此演示不连接主机、不读取日志。</p></template>
          <template v-else><p><b>目标：</b>分析订单服务 502 的可能原因，先给证据，再给假设。</p><ul><li>确认异常时间、影响范围和最近变更。</li><li>区分已知事实、待验证假设与缺失证据。</li><li>输出三条优先级明确的只读验证建议。</li><li>没有验证结果时，不宣称已定位根因。</li></ul></template>
          <div class="simulation-state"><span>{{ simulated ? '模拟已启用（仅本案例）' : '模拟未启用' }}</span><button type="button" :aria-pressed="simulated" @click="simulated = !simulated">{{ simulated ? '模拟停用' : '模拟启用' }}</button></div>
        </article>
        <article><h3>{{ isPlugin ? '模拟协作流程' : '虚构输出示例' }}</h3>
          <ol v-if="isPlugin"><li><b>连接工作台</b><span>假设用户提供一段服务连接观察。</span></li><li><b>星桥证据插件</b><span>将虚构的 upstream timeout 日志归类为上游响应线索。</span></li><li><b>知识引擎</b><span>关联超时、连接池与服务健康检查手册。</span></li><li><b>Agent 建议</b><span>核对上游延迟与发布变更，再确定下一步验证。</span></li></ol>
          <template v-else><p><b>证据（虚构）：</b>14:05 发布后出现 502，示例日志包含 upstream timed out。</p><p><b>假设：</b>上游响应变慢；尚不能排除网络或连接池问题。</p><p><b>下一步：</b>比对发布前后耗时、检查上游健康状态、核对同时间段连接池指标。</p><p><b>验收：</b>验证结果能够支持或排除上述假设，并记录证据来源。</p></template>
        </article>
      </div>
      <details><summary>{{ isPlugin ? '查看虚构插件清单' : '查看示例 SKILL.md' }}</summary><pre>{{ isPlugin ? pluginManifest : skillMarkdown }}</pre></details>
      <p class="demo-boundary">全部名称、状态、日志与输出均为虚构演示。模拟启停仅影响此案例，不安装插件或 Skill、不更改任务目标、不写入真实工作区，也不会发送模型请求。</p>
    </div>
  </section>
</template>
<script setup>
import { computed, ref } from 'vue'
const props = defineProps({ kind: { type: String, required: true } })
const isPlugin = computed(() => props.kind === 'plugin')
const open = ref(false), simulated = ref(false)
const pluginManifest = JSON.stringify({ id: 'demo-nginx-evidence', name: '星桥 · Nginx 故障证据插件（虚构）', version: '1.2.0', category: '诊断分析', description: '虚构案例：组织 Nginx 排障证据与检查清单。', entry: 'knowledge', dependencies: ['ops-knowledge', 'ops-connections'] }, null, 2)
const skillMarkdown = `---
name: demo-nginx-incident-coach
description: 虚构案例，演示如何用证据驱动 Nginx 502 排查。
---

# 目标
区分已知事实与原因假设，给出可验证的下一步。

# 步骤
1. 询问异常时间、影响范围与最近变更。
2. 核对错误日志、上游服务状态和响应耗时。
3. 按优先级列出假设，逐条注明支持证据和缺失信息。

# 输出格式
证据摘要 → 原因假设 → 只读验证建议 → 验收标准。

# 边界
不执行命令；证据不足时不宣称已定位或修复故障。`
</script>
<style scoped>
.extension-demo{margin:22px 0;color:var(--smart-text)}.demo-toggle{display:flex;justify-content:space-between;align-items:center;gap:16px}.demo-toggle p{font-size:12px;color:var(--smart-muted);line-height:1.8}.extension-demo button{min-height:42px;padding:10px 14px;border:1px solid var(--smart-border);border-radius:7px;background:var(--smart-surface);color:var(--smart-primary-strong);font:12px var(--font-cn);cursor:pointer;white-space:nowrap}.extension-demo button:focus-visible,summary:focus-visible{outline:2px solid var(--smart-primary-strong);outline-offset:3px}.demo-content{margin-top:16px;padding:24px;border:1px solid var(--smart-primary-strong);border-radius:14px;background:var(--smart-surface)}.demo-badge{display:inline-block;color:var(--smart-primary-strong);font-size:11px;margin-bottom:12px}.demo-content h2{font-size:21px;font-weight:550;line-height:1.5;margin:0}.demo-content h3{font-size:14px;margin:0 0 16px}.demo-content p,.demo-content li,.demo-content dl{font-size:12px;line-height:1.9;color:var(--smart-muted)}.demo-columns{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:24px 0}.demo-columns article{min-width:0;background:var(--smart-bg);border:1px solid var(--smart-border);border-radius:10px;padding:20px}.demo-content dl{display:grid;grid-template-columns:75px 1fr;gap:9px}.demo-content dd{margin:0;color:var(--smart-text)}.demo-content ul,.demo-content ol{padding-left:20px}.demo-content li{margin-bottom:12px}.demo-content li span{display:block}.demo-content b{color:var(--smart-text);font-weight:500}.simulation-state{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;border-top:1px solid var(--smart-border);padding-top:16px;margin-top:18px;font-size:11px;color:var(--smart-primary-strong)}summary{cursor:pointer;font-size:12px;width:fit-content;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:380px;overflow:auto;padding:16px;border-radius:8px;background:var(--smart-bg);font:12px/1.8 var(--font-mono)}.demo-boundary{margin:18px 0 0;padding-top:16px;border-top:1px solid var(--smart-border)}@media(max-width:767px){.demo-columns{grid-template-columns:minmax(0,1fr);gap:14px}.demo-content{padding:18px 14px}.demo-columns article{padding:16px}.demo-content h2{font-size:18px}.demo-toggle{align-items:start;flex-wrap:wrap;gap:4px}}
</style>
