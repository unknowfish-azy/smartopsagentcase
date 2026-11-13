<template>
  <div v-if="activeRemoteDialog" class="remote-tool-overlay" role="dialog" aria-modal="true" :aria-labelledby="`remote-dialog-${activeRemoteDialog}`" @click.self="closeRemoteDialog">
    <section class="remote-tool-dialog">
      <header class="remote-tool-dialog-header">
        <div>
          <p class="eyebrow">SMARTOPS REMOTE / TOOL WINDOW</p>
          <h2 :id="`remote-dialog-${activeRemoteDialog}`">{{ remoteDialogTitle }}</h2>
          <p class="remote-dialog-subtitle">{{ remoteDialogSubtitle }}</p>
        </div>
        <button class="remote-dialog-close" type="button" aria-label="关闭工具窗口" title="关闭" @click="closeRemoteDialog">×</button>
      </header>

      <div class="remote-tool-dialog-body">
        <template v-if="activeRemoteDialog === 'terminal'">
          <div class="remote-stat-grid"><div><strong>{{ openTabs.length }}</strong><span>已打开会话</span></div><div><strong>{{ onlineTabs.length }}</strong><span>在线终端</span></div></div>
          <div v-if="runtimeId" class="remote-tool-note">当前终端：{{ selectedSession?.name || '未命名会话' }}。点击下方按钮返回终端工作区，终端输出仍由真实运行时提供。</div><div v-else class="remote-empty">当前没有在线终端，请先连接一个真实 SSH 会话。</div>
          <button class="primary-action" type="button" :disabled="!runtimeId" @click="closeRemoteDialog(); activeWorkspace = 'TERMINAL'">打开终端工作区</button>
        </template>

        <template v-else-if="activeRemoteDialog === 'session'">
          <form class="remote-inline-form" @submit.prevent="showCreate = true; closeRemoteDialog()">
            <label>快速新建 SSH / SFTP 会话<input v-model="draft.name" placeholder="例如：prod-web-01" /></label>
            <button class="primary-action" type="submit">打开会话向导</button>
          </form>
          <div class="remote-tool-note">保存后会显示在左侧会话树；系统不会伪造连接状态，连接需由后端桥接服务确认。</div>
        </template>

        <template v-else-if="activeRemoteDialog === 'server'">
          <div class="remote-stat-grid"><div><strong>{{ sessions.length }}</strong><span>已保存服务器</span></div><div><strong>{{ openTabs.length }}</strong><span>当前会话</span></div><div><strong>{{ onlineTabs.length }}</strong><span>在线目标</span></div><div><strong>{{ capabilities.length }}</strong><span>连接能力</span></div></div>
          <div class="remote-tool-list"><div v-for="capability in capabilities" :key="capability.protocol" class="remote-tool-row"><span>{{ capability.protocol }}</span><span :class="['remote-state', capability.status === 'SUPPORTED' ? 'online' : 'offline']">{{ capabilityLabelZh(capability) }}</span></div></div>
          <button type="button" @click="closeRemoteDialog(); query = ''; document.querySelector('.session-search input')?.focus()">定位左侧服务器列表</button>
        </template>

        <template v-else-if="activeRemoteDialog === 'tools'">
          <div class="remote-tool-grid"><button type="button" @click="closeRemoteDialog(); activeWorkspace = 'TERMINAL'">终端<small>查看真实终端输出</small></button><button type="button" :disabled="!runtimeId" @click="closeRemoteDialog(); activeWorkspace = 'FILES'">远程文件<small>浏览、下载、上传</small></button><button type="button" @click="closeRemoteDialog(); openMultiExec()">批量命令<small>多目标审批执行</small></button><button type="button" :disabled="!runtimeId" @click="closeRemoteDialog(); activeWorkspace = 'TUNNELS'">SSH 隧道<small>端口转发与日志</small></button><button type="button" @click="closeRemoteDialog(); document.querySelector('.server-inspector')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })">主机巡检<small>查看会话能力与 Agent 上下文</small></button><button type="button" @click="closeRemoteDialog(); connectionError = '日志诊断工具需要先连接真实会话'">日志诊断<small>连接后才可读取日志</small></button></div>
        </template>

        <template v-else-if="activeRemoteDialog === 'favorites'">
          <label class="remote-search-field">搜索我的会话<input v-model="query" placeholder="名称 / 主机 / 协议" /></label>
          <div v-if="filteredSessions.length" class="remote-favorite-list"><button v-for="session in filteredSessions" :key="session.id" type="button" class="remote-favorite-row" @click="selectSession(session); closeRemoteDialog()"><span class="session-protocol">{{ session.protocol }}</span><span><strong>{{ session.name }}</strong><small>{{ session.username }}@{{ session.host }}:{{ session.port }}</small></span><span class="remote-chevron">›</span></button></div><div v-else class="remote-empty">暂无已保存会话。请先创建 SSH / SFTP 会话。</div>
        </template>

        <template v-else-if="activeRemoteDialog === 'view'">
          <div class="remote-setting-list"><label><input v-model="showSessionTree" type="checkbox" /> 左侧会话树 <small>隐藏后可恢复，当前会话不会关闭</small></label><label><input type="checkbox" checked disabled /> 中央终端工作区 <small>始终保留为主要操作区</small></label><label><input v-model="showServerInspector" type="checkbox" /> 右侧会话检查器 <small>用于显示真实连接信息</small></label><button type="button" @click="closeRemoteDialog(); document.querySelector('.server-inspector')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })">查看会话检查器</button></div>
        </template>

        <template v-else-if="activeRemoteDialog === 'split'">
          <div class="split-choice-grid"><button type="button" :class="{ selected: layout === 'SINGLE' }" @click="layout = 'SINGLE'; closeRemoteDialog()">单屏<small>显示当前会话</small></button><button type="button" :disabled="openTabs.length < 2" :class="{ selected: layout === 'SPLIT_VERTICAL' }" @click="layout = 'SPLIT_VERTICAL'; closeRemoteDialog()">左右分屏<small>并排查看两个会话</small></button><button type="button" :disabled="openTabs.length < 2" :class="{ selected: layout === 'SPLIT_HORIZONTAL' }" @click="layout = 'SPLIT_HORIZONTAL'; closeRemoteDialog()">上下分屏<small>上下查看两个会话</small></button></div><p class="remote-tool-note">需要至少打开两个真实运行时才能启用分屏。</p>
        </template>

        <template v-else-if="activeRemoteDialog === 'multi-exec'"><div class="remote-tool-note">批量执行会沿用现有风险预览、人工确认和审计流程。当前在线目标：{{ onlineTabs.length }} 个。</div><button class="primary-action" type="button" :disabled="!onlineTabs.length" @click="closeRemoteDialog(); openMultiExec()">打开批量执行窗口</button></template>

        <template v-else-if="activeRemoteDialog === 'tunnel'"><TunnelWorkspace v-if="runtimeId" :tunnels="tunnels.filter(tunnel => tunnel.runtimeId === runtimeId)" :runtime-online="runtimeOnline" :selected-tunnel="selectedTunnel" @create="createTunnel" @start="startTunnel" @stop="stopTunnel" @edit="editTunnel" @remove="removeTunnel" @logs="showTunnelLogs" /><div v-else class="remote-empty">请先连接真实 SSH 会话，隧道工作台会显示在这里。</div></template>

        <template v-else-if="activeRemoteDialog === 'files'"><RemoteFiles v-if="runtimeId" :key="runtimeId" :runtime-id="runtimeId" :session-name="selectedSession?.name" /><div v-else class="remote-empty">请先连接真实 SSH / SFTP 会话，才能浏览远程文件。</div></template>

        <template v-else-if="activeRemoteDialog === 'settings'"><div class="remote-setting-list"><label>默认协议<select v-model="draft.protocol"><option v-for="item in capabilities" :key="item.protocol" :value="item.protocol">{{ item.protocol }}</option></select></label><label>终端工作区<select v-model="layout"><option value="SINGLE">单屏</option><option value="SPLIT_VERTICAL">左右分屏</option><option value="SPLIT_HORIZONTAL">上下分屏</option></select></label><label>刷新连接资源<button type="button" @click="loadResources">重新读取会话与桥接能力</button></label></div><p class="remote-tool-note">设置只影响当前页面上下文；密码、Token 和私钥不会在页面中明文展示。</p></template>

        <template v-else-if="activeRemoteDialog === 'xserver'"><div class="remote-status-banner"><span class="remote-status-dot offline"></span><div><strong>X服务器未配置</strong><p>当前后端未提供 X11 / X服务器桥接能力，因此不会伪造启动状态。</p></div></div><div class="remote-tool-note">如需图形化 Linux 应用，请先在本机安装并启动 X Server，再由后端桥接配置 DISPLAY、SSH X11 转发和权限。配置完成后状态会从后端能力接口更新。</div><button type="button" @click="loadResources">重新检查桥接能力</button></template>

        <template v-else-if="activeRemoteDialog === 'macros'"><div class="remote-status-banner"><span class="remote-status-dot offline"></span><div><strong>暂无已保存宏</strong><p>宏执行能力尚未接入后端，当前不会保存或执行未经审批的命令序列。</p></div></div><div class="remote-tool-note">后续宏功能将支持命令序列、参数校验、风险分级、人工确认和全链路审计；接入前请继续使用批量执行窗口。</div><button type="button" @click="closeRemoteDialog(); openMultiExec()">使用批量执行替代宏</button></template>

        <template v-else><div class="remote-help-content"><h3>远程运维工具说明</h3><p>顶部图标会打开独立悬浮窗口，窗口右上角关闭按钮始终固定可见，内容超出时只滚动窗口内部。</p><p>所有服务器、会话、文件、隧道和命令结果均来自真实后端。未连接时显示“未连接”，不会生成虚假数据。</p><p>批量命令、隧道启动和文件上传仍需要后端能力与人工确认；高风险操作会保留预览、审批和审计记录。</p></div></template>
      </div>
    </section>
  </div>
</template>

<script setup>
import { inject } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'
import RemoteFiles from './RemoteFiles.vue'
import TunnelWorkspace from './TunnelWorkspace.vue'

const {
  query,
  openTabs,
  sessions,
  draft,
  showCreate,
  activeRemoteDialog,
  capabilities,
  selectedSession,
  runtimeId,
  connectionError,
  layout,
  activeWorkspace,
  showSessionTree,
  showServerInspector,
  tunnels,
  selectedTunnel,
  runtimeOnline,
  filteredSessions,
  onlineTabs,
  remoteDialogTitle,
  remoteDialogSubtitle,
  capabilityLabelZh,
  closeRemoteDialog,
  selectSession,
  createTunnel,
  startTunnel,
  stopTunnel,
  editTunnel,
  removeTunnel,
  showTunnelLogs,
  openMultiExec,
  loadResources
} = inject(CONNECTIONS_WORKSPACE_KEY)
</script>

<style scoped>
.eyebrow {
  margin: 0;
  color: #8c9ba5;
  font: 10px var(--font-mono);
  letter-spacing: .08em;
}

.primary-action {
  border-color: #246b50;
  background: #123124;
  color: #a9e8c3;
}

button:disabled {
  opacity: .42;
  cursor: not-allowed;
}

.remote-status-banner{display:flex;align-items:flex-start;gap:12px;padding:16px;border:1px solid var(--smart-border);background:var(--smart-bg)}.remote-status-banner strong{color:var(--smart-text);font-size:14px}.remote-status-banner p{margin:6px 0 0;color:var(--smart-muted);font-size:12px;line-height:1.6}.remote-status-dot{width:9px;height:9px;margin-top:5px;border-radius:50%;background:#f4c879;box-shadow:0 0 10px color-mix(in srgb,#f4c879 45%,transparent)}.remote-status-dot.offline{background:#f4c879}
.remote-tool-overlay{position:fixed;inset:0;z-index:40;display:grid;place-items:center;padding:clamp(12px,3vw,36px);background:rgba(2,7,12,.72)}
.remote-tool-dialog{display:flex;width:min(880px,100%);max-height:min(760px,calc(100vh - 32px));flex-direction:column;border:1px solid var(--smart-border-strong);background:var(--smart-surface);box-shadow:0 24px 80px rgba(0,0,0,.5);overflow:hidden}
.remote-tool-dialog-header{display:flex;justify-content:space-between;gap:18px;padding:20px 24px;border-bottom:1px solid var(--smart-border);background:linear-gradient(90deg,color-mix(in srgb,var(--smart-primary-strong) 9%,var(--smart-surface)),var(--smart-surface))}
.remote-tool-dialog-header h2{margin:4px 0 5px;color:var(--smart-text);font-size:22px;font-weight:550}.remote-dialog-subtitle{margin:0;color:var(--smart-muted);font-size:12px}.remote-dialog-close{position:sticky;top:0;align-self:flex-start;display:grid;place-items:center;width:34px;height:34px;padding:0;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);font-size:23px;line-height:1;cursor:pointer}.remote-dialog-close:hover,.remote-dialog-close:focus-visible{border-color:var(--smart-primary-strong);color:var(--smart-primary-strong);outline:2px solid color-mix(in srgb,var(--smart-primary-strong) 30%,transparent);outline-offset:2px}
.remote-tool-dialog-body{min-height:0;padding:22px 24px;overflow:auto;color:var(--smart-text)}.remote-inline-form{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.remote-inline-form label,.remote-search-field,.remote-setting-list label{display:grid;gap:7px;color:var(--smart-muted);font-size:12px}.remote-inline-form label{flex:1;min-width:240px}.remote-tool-dialog input,.remote-tool-dialog select{min-height:36px;padding:8px 10px;border:1px solid var(--smart-border-strong);background:var(--smart-bg);color:var(--smart-text);font:12px var(--font-cn);outline:none}.remote-tool-dialog input:focus,.remote-tool-dialog select:focus{border-color:var(--smart-primary-strong)}.remote-tool-note{margin:16px 0 0;padding:12px 14px;border-left:3px solid var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 7%,transparent);color:var(--smart-muted);font-size:12px;line-height:1.6}.remote-stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:20px}.remote-stat-grid div{display:grid;gap:5px;padding:14px;border:1px solid var(--smart-border);background:var(--smart-bg)}.remote-stat-grid strong{color:var(--smart-primary-strong);font:24px var(--font-mono)}.remote-stat-grid span{color:var(--smart-muted);font-size:11px}.remote-tool-list,.remote-favorite-list{display:grid;gap:8px;margin-bottom:18px}.remote-tool-row{display:flex;justify-content:space-between;padding:11px 12px;border-bottom:1px solid var(--smart-border);font-size:12px}.remote-state{font-size:11px}.remote-state.online{color:#86d6a7}.remote-state.offline{color:#f4c879}.remote-tool-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.remote-tool-grid button,.split-choice-grid button{display:grid;gap:6px;min-height:76px;padding:13px;text-align:left;border:1px solid var(--smart-border);background:var(--smart-bg);color:var(--smart-text);font:13px var(--font-cn);cursor:pointer}.remote-tool-grid button:hover:not(:disabled),.split-choice-grid button:hover:not(:disabled),.split-choice-grid button.selected{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 9%,var(--smart-bg))}.remote-tool-grid small,.split-choice-grid small{color:var(--smart-muted);font-size:10px}.remote-tool-grid button:disabled,.split-choice-grid button:disabled{cursor:not-allowed;opacity:.42}.remote-search-field{margin-bottom:14px}.remote-favorite-row{display:flex;align-items:center;gap:12px;width:100%;padding:12px;border:1px solid var(--smart-border);background:var(--smart-bg);color:var(--smart-text);text-align:left;cursor:pointer}.remote-favorite-row:hover{border-color:var(--smart-primary-strong)}.remote-favorite-row span:nth-child(2){display:grid;gap:4px;flex:1}.remote-favorite-row small{color:var(--smart-muted);font-size:11px}.remote-chevron{font-size:24px;color:var(--smart-muted)}.remote-empty{padding:34px 12px;border:1px dashed var(--smart-border-strong);color:var(--smart-muted);text-align:center;font-size:12px}.remote-setting-list{display:grid;gap:14px}.remote-setting-list label{grid-template-columns:1fr auto;align-items:center}.remote-setting-list label input[type=checkbox]{justify-self:start;grid-column:1}.remote-setting-list label small{grid-column:1 / -1;color:var(--smart-muted);font-size:10px}.remote-setting-list select{min-width:180px}.remote-setting-list button{min-height:36px;padding:0 12px;border:1px solid var(--smart-border-strong);background:var(--smart-bg);color:var(--smart-text);cursor:pointer}.split-choice-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.remote-help-content{max-width:680px;color:var(--smart-muted);font-size:13px;line-height:1.8}.remote-help-content h3{margin-top:0;color:var(--smart-text)}
.session-protocol{color:#38bdf8;font:10px var(--font-mono)}
@media(max-width:700px){.remote-tool-dialog-header{padding:16px}.remote-tool-dialog-body{padding:16px}.remote-stat-grid,.remote-tool-grid,.split-choice-grid{grid-template-columns:1fr 1fr}.remote-tool-grid button{min-height:66px}.remote-setting-list label{grid-template-columns:1fr}.remote-setting-list select{width:100%}}@media(max-width:460px){.remote-stat-grid,.remote-tool-grid,.split-choice-grid{grid-template-columns:1fr}}
</style>
