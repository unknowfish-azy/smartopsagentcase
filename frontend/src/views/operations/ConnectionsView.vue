<template>
  <article class="connections-page">
    <header class="connections-header">
      <div>
        <p class="eyebrow">OPERATIONS CENTER <span>远程运维</span></p>
        <h1>连接中心</h1>
      </div>
      <div class="connection-status" :class="{ ready: bridgeReady }">
        <span class="status-dot" aria-hidden="true"></span>
        <div>
          <strong>{{ bridgeStatus }}</strong>
          <small>SSH / SFTP · 本地桥接</small>
        </div>
      </div>
    </header>

    <nav class="remote-menu" aria-label="远程运维菜单栏">
      <button type="button" @click="openRemoteDialog('terminal')">终端</button>
      <button type="button" @click="openRemoteDialog('session')">会话</button>
      <button type="button" @click="openRemoteDialog('view')">视图</button>
      <button type="button" @click="openRemoteDialog('xserver')">X服务器</button>
      <button type="button" @click="openRemoteDialog('tools')">工具</button>
      <button type="button" @click="openRemoteDialog('settings')">设置</button>
      <button type="button" @click="openRemoteDialog('macros')">宏</button>
      <button type="button" @click="openRemoteDialog('help')">帮助</button>
    </nav>

    <nav class="remote-toolbar" aria-label="远程运维工具栏">
      <button type="button" title="新建会话" @click="openRemoteDialog('session')"><Monitor /><span>会话</span></button>
      <button type="button" title="服务器与连接资源" @click="openRemoteDialog('server')"><User /><span>服务器</span></button>
      <button type="button" title="远程工具" @click="openRemoteDialog('tools')"><Tools /><span>工具</span></button>
      <button type="button" title="最近会话" @click="openRemoteDialog('favorites')"><Star /><span>我的会话</span></button>
      <button type="button" title="工作区视图" @click="openRemoteDialog('view')"><View /><span>视图</span></button>
      <button type="button" title="切换分屏" @click="openRemoteDialog('split')"><FullScreen /><span>分屏</span></button>
      <button type="button" title="批量执行" @click="openRemoteDialog('multi-exec')"><Switch /><span>多重执行</span></button>
      <button type="button" title="SSH 隧道" @click="openRemoteDialog('tunnel')"><Connection /><span>隧道</span></button>
      <button type="button" title="远程文件" @click="openRemoteDialog('files')"><Folder /><span>文件</span></button>
      <button type="button" title="连接设置" @click="openRemoteDialog('settings')"><Setting /><span>设置</span></button>
      <button type="button" title="使用帮助" @click="openRemoteDialog('help')"><QuestionFilled /><span>帮助</span></button>
    </nav>

    <p v-if="initialLoading" role="status">正在加载连接资源…</p>
    <div v-if="initialError" role="alert">连接资源加载失败：{{ initialError }} <button @click="loadResources">重试</button></div>

    <section class="operations-workspace" :class="{ 'session-tree-hidden': !showSessionTree, 'server-inspector-hidden': !showServerInspector }" aria-label="远程运维工作区">
      <aside class="session-tree" aria-label="已保存连接">
        <div class="panel-heading">
          <div>
            <h2>连接会话</h2>
            <small>{{ sessions.length }} 个已保存</small>
          </div>
          <button class="icon-action" type="button" title="新建连接" aria-label="新建连接" @click="showCreate = true">+</button>
        </div>

        <label class="session-search">
          <span>搜索连接</span>
          <input v-model="query" placeholder="名称 / 主机 / 标签" />
        </label>

        <div v-if="!filteredSessions.length && !initialLoading && !initialError" class="session-empty">
          <strong>{{ sessions.length ? '没有匹配的连接' : '暂无已保存连接' }}</strong>
          <p>{{ sessions.length ? '试试主机名、地址或协议' : '添加 SSH 会话后，可在此快速连接' }}</p>
        </div>
        <div v-else class="session-list">
          <button
            v-for="session in filteredSessions"
            :key="session.id"
            type="button"
            class="session-row"
            :class="{ selected: selectedSession?.id === session.id }"
            @click="selectSession(session)"
          >
            <span class="session-protocol">{{ session.protocol }}</span>
            <strong>{{ session.name }}</strong>
            <small>{{ session.username }}@{{ session.host }}:{{ session.port }}</small>
          </button>
        </div>

        <button class="new-session" type="button" @click="showCreate = true">新建连接</button>
      </aside>

      <section class="terminal-workspace" aria-label="终端工作区">
        <div class="workspace-toolbar">
          <div class="workspace-name">
            <span>终端工作区</span>
            <strong>{{ selectedSession?.name || '未选择会话' }}</strong>
          </div>
          <div class="toolbar-actions">
            <button type="button" class="primary-action" :disabled="!selectedSession || connecting || runtimeOnline || Boolean(hostKey)" @click="connectSelected()">
              {{ connecting ? '正在连接…' : runtimeOnline ? '已连接' : runtimeId ? '重新连接' : '连接' }}
            </button>
            <button type="button" :disabled="openTabs.length < 2" @click="layout = layout === 'SINGLE' ? 'SPLIT_VERTICAL' : layout === 'SPLIT_VERTICAL' ? 'SPLIT_HORIZONTAL' : 'SINGLE'">{{ layout === 'SINGLE' ? '左右分屏' : layout === 'SPLIT_VERTICAL' ? '上下分屏' : '单屏' }}</button>
            <button type="button" :disabled="!runtimeId" @click="activeWorkspace = activeWorkspace === 'FILES' ? 'TERMINAL' : 'FILES'">远程文件</button>
            <button type="button" :disabled="!runtimeId" @click="openMultiExec">批量命令</button>
            <button type="button" :class="{ active: activeWorkspace === 'TUNNELS' }" @click="activeWorkspace = activeWorkspace === 'TUNNELS' ? 'TERMINAL' : 'TUNNELS'">隧道</button>
          </div>
        </div>

        <div v-if="openTabs.length" class="runtime-tabs" aria-label="运行会话">
          <div v-for="tab in openTabs" :key="tab.runtimeId">
            <button :aria-pressed="tab.runtimeId === runtimeId" @click="selectSession(tab.session, tab.runtimeId)">{{ tab.session.name }} · {{ tab.status }}</button>
            <button :aria-label="`关闭 ${tab.session.name}`" @click="closeRuntimeTab(tab)">×</button>
          </div>
        </div>
        <div v-show="runtimeId && activeWorkspace === 'TERMINAL'" class="runtime-panes" :class="layout.toLowerCase()">
          <OperationsTerminal v-for="tab in openTabs" v-show="visibleRuntimes.includes(tab.runtimeId)" :key="tab.runtimeId" :runtime-id="tab.runtimeId" :session-name="tab.session.name" @status="tab.status = $event" />
        </div>
        <RemoteFiles v-if="runtimeId && activeWorkspace === 'FILES'" :key="runtimeId" :runtime-id="runtimeId" :session-name="selectedSession?.name" />
        <TunnelWorkspace
          v-if="activeWorkspace === 'TUNNELS'"
          :tunnels="tunnels.filter(tunnel => tunnel.runtimeId === runtimeId)"
          :runtime-online="runtimeOnline"
          :selected-tunnel="selectedTunnel"
          @create="createTunnel"
          @start="startTunnel"
          @stop="stopTunnel"
          @edit="editTunnel"
          @remove="removeTunnel"
          @logs="showTunnelLogs"
        />
        <div v-if="!runtimeId && activeWorkspace === 'TERMINAL'" class="workspace-idle">
          <div class="remote-welcome">
            <div class="remote-logo"><span>&gt;_</span></div>
            <h2>SmartOps Remote</h2>
            <div class="welcome-actions"><button type="button" class="primary-action" @click="showCreate = true"><span class="action-plus">+</span> 新建远程会话</button><button type="button" @click="query = ''; document.querySelector('.session-search input')?.focus()">↻ 恢复最近会话</button></div>
            <label class="welcome-search"><input v-model="query" placeholder="查找现有会话或服务器名…" aria-label="查找现有会话或服务器名" /></label>
          </div>
          <div class="idle-heading">
            <div>
              <span class="section-kicker">已保存目标</span>
              <h2>{{ recentSessions.length ? '最近连接' : '连接资源' }}</h2>
            </div>
            <button v-if="!sessions.length" type="button" class="text-action" @click="showCreate = true">添加 SSH 连接</button>
          </div>
          <div v-if="recentSessions.length" class="recent-sessions">
            <article v-for="session in recentSessions" :key="session.id" class="recent-session">
              <div class="recent-session-copy">
                <strong>{{ session.name }}</strong>
                <span>{{ session.host }}:{{ session.port }} · {{ session.protocol }}</span>
                <small>{{ session.lastConnectedAt ? `上次连接 ${formatLastConnected(session.lastConnectedAt)}` : '尚未连接' }}</small>
              </div>
              <button type="button" :disabled="connecting" @click="selectSession(session); connectSelected()">连接</button>
            </article>
          </div>
          <div v-else class="workspace-empty">
            <h3>{{ selectedSession ? '会话已选中' : '选择一个连接开始工作' }}</h3>
            <p>{{ selectedSession ? `${selectedSession.username}@${selectedSession.host}:${selectedSession.port}` : '连接后将在此显示真实终端输出。当前不会自动执行远程命令。' }}</p>
            <button v-if="selectedSession" type="button" class="primary-action" :disabled="connecting" @click="connectSelected()">{{ connecting ? '正在连接…' : '连接所选会话' }}</button>
            <button v-else type="button" class="text-action" @click="showCreate = true">新建 SSH 会话</button>
          </div>
        </div>
        <p v-if="connectionError" class="connection-error" role="alert">{{ connectionError }}</p>
      </section>

      <aside class="server-inspector" aria-label="会话检查器">
        <div class="panel-heading inspector-heading">
          <div>
            <h2>会话检查器</h2>
            <small>连接状态与目标信息</small>
          </div>
          <span class="inspector-state" :class="{ online: runtimeOnline }">{{ activeTab?.status || '空闲' }}</span>
        </div>

        <div v-if="selectedSession" class="inspector-content">
          <dl class="session-details">
            <div><dt>目标</dt><dd>{{ selectedSession.name }}</dd></div>
            <div><dt>主机</dt><dd>{{ selectedSession.host }}:{{ selectedSession.port }}</dd></div>
            <div><dt>协议</dt><dd>{{ selectedSession.protocol }}</dd></div>
            <div><dt>用户</dt><dd>{{ selectedSession.username }}</dd></div>
            <div><dt>最近连接</dt><dd>{{ formatLastConnected(selectedSession.lastConnectedAt) }}</dd></div>
            <div><dt>桥接</dt><dd>{{ bridgeStatus }}</dd></div>
          </dl>

          <section class="agent-context" aria-label="Agent 只读上下文">
            <div class="subsection-heading">
              <h3>Agent 上下文</h3>
              <span>只读</span>
            </div>
            <p v-if="!runtimeId">连接后读取允许的分析动作，不会自动执行命令。</p>
            <p v-else-if="agentContextLoading">正在读取会话上下文…</p>
            <p v-else-if="agentContextError" class="context-error">{{ agentContextError }}</p>
            <template v-else-if="agentContext">
              <ul class="allowed-actions">
                <li v-for="action in agentContext.allowedActions" :key="action">{{ agentActionLabel(action) }}</li>
              </ul>
              <p class="approval-boundary">{{ executionBoundaryLabel(agentContext.executionBoundary) }}</p>
            </template>
          </section>
        </div>
        <div v-else class="inspector-empty">选择一个已保存会话查看目标和连接信息。</div>

        <section class="capability-list">
          <div class="subsection-heading"><h3>桥接能力</h3><small>{{ capabilities.length }} 项</small></div>
          <div v-for="capability in capabilities" :key="capability.protocol" class="capability-row">
            <span>{{ capability.protocol }}</span>
            <small :class="{ supported: capability.status === 'SUPPORTED' }">{{ capabilityLabelZh(capability) }}</small>
          </div>
        </section>
      </aside>
    </section>

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

    <div v-if="hostKey" class="create-overlay" role="dialog" aria-modal="true" aria-labelledby="host-key-title">
      <section class="create-session host-key-dialog">
        <p class="eyebrow">主机密钥验证</p>
        <h2 id="host-key-title">确认远程身份</h2>
        <p class="host-key-copy">{{ selectedSession?.host }}:{{ selectedSession?.port }} 返回了新的 {{ hostKey.algorithm }} 主机密钥</p>
        <code>{{ hostKey.fingerprint }}</code>
        <div class="form-actions">
          <button type="button" @click="hostKey = null">取消</button>
          <button type="button" @click="hostKey = null; connectSelected('TRUST_ONCE')">仅信任本次</button>
          <button type="button" @click="hostKey = null; connectSelected('TRUST_AND_SAVE')">信任并保存</button>
        </div>
      </section>
    </div>

    <div v-if="showMultiExec" class="create-overlay" role="dialog" aria-modal="true" aria-labelledby="command-preview-title">
      <form class="create-session" @submit.prevent="previewCommand">
        <p class="eyebrow">批量执行 / 审批</p>
        <h2 id="command-preview-title">命令预览</h2>
        <label>命令<textarea v-model="multiCommand" rows="3" placeholder="uptime" required></textarea></label>
        <fieldset class="multi-targets"><legend>目标（{{ selectedRuntimeIds.length }}）</legend><label v-for="tab in onlineTabs" :key="tab.runtimeId"><input v-model="selectedRuntimeIds" type="checkbox" :value="tab.runtimeId" /> {{ tab.session.name }}</label></fieldset>
        <p class="host-key-copy">审批后才会发送命令；服务端只返回 SENT，表示已写入终端输入流。</p>
        <div v-if="multiPreview" class="risk-preview">
          <span>风险等级</span>
          <strong :class="multiPreview.risk.toLowerCase()">{{ riskLabel(multiPreview.risk) }}</strong>
          <small>需要 {{ multiPreview.requiredApprovals }} 次确认</small>
        </div>
        <div class="form-actions">
          <button type="button" @click="showMultiExec = false">取消</button>
          <button v-if="!multiPreview" type="submit">查看风险</button>
          <button v-else type="button" @click="approveCommand">{{ multiApprovalStep === 1 ? '进行第二次确认' : '确认并发送' }}</button>
        </div>
      </form>
    </div>

    <div v-if="showCreate" class="create-overlay" role="dialog" aria-modal="true" aria-labelledby="create-session-title" @click.self="showCreate = false">
      <form class="create-session" @submit.prevent="submitCreate">
        <p class="eyebrow">新建会话</p>
        <h2 id="create-session-title">创建连接</h2>
        <label>会话类型<select v-model="draft.protocol"><option v-for="item in capabilities" :key="item.protocol" :value="item.protocol" :disabled="!canConnect(item)">{{ item.protocol }} · {{ capabilityLabelZh(item) }}</option></select></label>
        <label>会话名称<input v-model="draft.name" required placeholder="prod-web-01" /></label>
        <label>主机<input v-model="draft.host" required placeholder="10.0.0.10" /></label>
        <label>端口<input v-model.number="draft.port" type="number" min="1" max="65535" required /></label>
        <label>用户名<input v-model="draft.username" required placeholder="operator" /></label>
        <p v-if="draft.protocol !== 'SSH' && draft.protocol !== 'SFTP'" class="capability-warning">{{ draft.protocol }} 需要本地桥接</p>
        <div class="form-actions"><button type="button" @click="showCreate = false">取消</button><button type="submit" :disabled="!canSubmit">保存会话</button></div>
      </form>
    </div>
  </article>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Connection, Folder, FullScreen, Monitor, QuestionFilled, Setting, Star, Switch, Tools, User, View } from '@element-plus/icons-vue'
import RemoteFiles from '../../components/operations/RemoteFiles.vue'
import { visibleRuntimeIds } from '../../components/operations/connectionWorkspace.js'
import OperationsTerminal from '../../components/operations/OperationsTerminal.vue'
import TunnelWorkspace from '../../components/operations/TunnelWorkspace.vue'
import {
  canConnect,
  closeOperationRuntime,
  connectOperationSession,
  createOperationSession,
  executeMultiExec,
  getOperationAgentContext,
  getOperationCapabilities,
  getOperationSessions,
  orderOperationSessions,
  previewMultiExec,
  startOperationTunnel,
  stopOperationTunnel
} from '../../api/operations.js'
import { clearActiveOperationRuntime, setActiveOperationRuntime } from '../../api/operationRuntimeState.js'

const query = ref('')
const openTabs = ref([])
const initialLoading = ref(false)
const initialError = ref('')
const showCreate = ref(false)
const activeRemoteDialog = ref('')
const capabilities = ref([])
const sessions = ref([])
const draft = ref({ protocol: 'SSH', name: '', host: '', port: 22, username: '' })
const selectedSession = ref(null)
const runtimeId = ref('')
const connecting = ref(false)
const connectionError = ref('')
const hostKey = ref(null)
const layout = ref('SINGLE')
const visibleRuntimes = computed(() => visibleRuntimeIds(openTabs.value, runtimeId.value, layout.value))
const activeWorkspace = ref('TERMINAL')
const showSessionTree = ref(true)
const showServerInspector = ref(true)
const tunnels = ref([])
const selectedTunnel = ref(null)
const activeTab = computed(() => openTabs.value.find(tab => tab.runtimeId === runtimeId.value))
const runtimeOnline = computed(() => activeTab.value?.status === '在线')
const showMultiExec = ref(false)
const multiCommand = ref('')
const multiPreview = ref(null)
const selectedRuntimeIds = ref([])
const multiApprovalStep = ref(0)
const agentContext = ref(null)
const agentContextLoading = ref(false)
const agentContextError = ref('')

const bridgeReady = computed(() => capabilities.value.some(item => item.protocol === 'SSH' && item.status === 'SUPPORTED'))
const bridgeStatus = computed(() => bridgeReady.value ? '已配置 SSH 适配器' : '桥接能力未知')
const canSubmit = computed(() => Boolean(draft.value.name && draft.value.host && draft.value.username && capabilities.value.some(item => item.protocol === draft.value.protocol && canConnect(item))))
const orderedSessions = computed(() => orderOperationSessions(sessions.value))
const recentSessions = computed(() => orderedSessions.value.slice(0, 5))
const filteredSessions = computed(() => orderedSessions.value.filter(session => !query.value || `${session.name} ${session.host} ${session.protocol} ${session.tagsJson || ''}`.toLowerCase().includes(query.value.toLowerCase())))
const onlineTabs = computed(() => openTabs.value.filter(tab => tab.status === '在线'))
const remoteDialogTitle = computed(() => ({ terminal: '终端', session: '新建远程会话', server: '服务器与连接资源', tools: '远程工具', favorites: '我的会话', view: '工作区视图', xserver: 'X服务器', split: '分屏布局', 'multi-exec': '多重执行', tunnel: 'SSH 隧道', files: '远程文件', settings: '连接设置', macros: '宏', help: '使用帮助' })[activeRemoteDialog.value] || '远程工具')
const remoteDialogSubtitle = computed(() => ({ terminal: '打开真实会话终端工作区', session: '创建并保存 SSH / SFTP 连接配置', server: '查看后端返回的真实会话和桥接能力', tools: '打开已经接入的终端、文件、隧道和诊断工具', favorites: '快速恢复最近保存的连接', view: '检查当前工作区面板状态', xserver: '检查 X11 图形转发桥接状态', split: '选择当前已打开运行时的显示方式', 'multi-exec': '对多个在线目标执行受审批保护的命令', tunnel: '查看当前 SSH 运行时的端口转发', files: '查看当前 SSH / SFTP 运行时的远程文件', settings: '调整当前页面的连接与终端偏好', macros: '命令序列功能与安全边界', help: '了解真实连接、权限和安全边界' })[activeRemoteDialog.value] || '')

function capabilityLabelZh(capability) {
  if (!capability) return '能力未知'
  if (capability.status === 'SUPPORTED') return '桥接可用'
  if (capability.status === 'REQUIRES_NATIVE_BRIDGE') return '需要本地桥接'
  return capability.status
}

function riskLabel(risk) {
  return ({ LOW: '低', MEDIUM: '中', HIGH: '高', CRITICAL: '严重' })[risk] || risk
}

function agentActionLabel(action) {
  return ({
    EXPLAIN_COMMAND: '解释命令',
    ANALYZE_OUTPUT: '分析输出',
    SEARCH_KNOWLEDGE: '搜索知识',
    SAVE_TO_MEMORY: '保存到记忆'
  })[action] || action
}

function executionBoundaryLabel(boundary) {
  if (boundary === 'EXECUTE_REQUIRES_EXPLICIT_APPROVAL') return '执行操作需要明确审批'
  return boundary || '执行操作需要审批'
}

function formatLastConnected(value) {
  if (!value) return '从未连接'
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return '连接时间未知'
  return timestamp.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function openRemoteDialog(type) {
  activeRemoteDialog.value = type
}

function closeRemoteDialog() {
  activeRemoteDialog.value = ''
}

function selectSession(session, tabId) {
  if (connecting.value || hostKey.value) return
  runtimeId.value = tabId || openTabs.value.findLast(tab => tab.session.id === session.id)?.runtimeId || ''
  agentContext.value = null; agentContextError.value = ''; selectedTunnel.value = null
  activeWorkspace.value = 'TERMINAL'
  selectedSession.value = session
  connectionError.value = ''
  if (runtimeId.value) loadAgentContext(runtimeId.value)
}

async function closeRuntimeTab(tab) {
  if (!window.confirm(`关闭 ${tab.session.name}？该连接及其隧道会结束。`)) return
  try { await closeOperationRuntime(tab.runtimeId) }
  catch (error) { if (error.status !== 404 && error.response?.status !== 404) { connectionError.value = error.message; return } }
  openTabs.value = openTabs.value.filter(item => item.runtimeId !== tab.runtimeId)
  tunnels.value = tunnels.value.filter(item => item.runtimeId !== tab.runtimeId)
  if (runtimeId.value === tab.runtimeId) {
    runtimeId.value = ''
    agentContext.value = null
    clearActiveOperationRuntime()
  }
}

async function loadAgentContext(nextRuntimeId) {
  agentContextLoading.value = true
  agentContextError.value = ''
  try {
    const response = await getOperationAgentContext(nextRuntimeId)
    if (runtimeId.value === nextRuntimeId) agentContext.value = response.data?.data || response.data
  } catch {
    if (runtimeId.value === nextRuntimeId) { agentContext.value = null; agentContextError.value = '暂时无法读取会话上下文' }
  } finally {
    if (runtimeId.value === nextRuntimeId) agentContextLoading.value = false
  }
}

function createTunnel() {
  if (!runtimeId.value) return
  const tunnel = { id: `draft-${Date.now()}`, runtimeId: runtimeId.value, name: `${selectedSession.value?.name || 'ssh'}-local`, type: 'LOCAL', listenAddress: '127.0.0.1', listenPort: 15432, targetHost: '', targetPort: 5432, sessionName: selectedSession.value?.name || 'SSH', status: 'STOPPED', autoReconnect: false, logs: [] }
  tunnels.value = [...tunnels.value, tunnel]
  selectedTunnel.value = tunnel
}

async function startTunnel(tunnel) {
  if (!tunnel || !runtimeId.value || tunnel.status === 'RUNNING') return
  tunnel.status = 'STARTING'
  selectedTunnel.value = tunnel
  try {
    if (!tunnel.targetHost) throw new Error('请先编辑隧道目标主机')
    const response = await startOperationTunnel(tunnel.runtimeId, { name: tunnel.name, listenAddress: tunnel.listenAddress, listenPort: tunnel.listenPort, targetHost: tunnel.targetHost, targetPort: tunnel.targetPort })
    const result = response.data?.data || response.data
    tunnel.bridgeId = result?.tunnelId || result?.id
    tunnel.status = result?.status === 'RUNNING' || result?.status === 'LISTENING' ? 'RUNNING' : 'ERROR'
    tunnel.logs = [...(tunnel.logs || []), `${new Date().toISOString()} START ${tunnel.status}`]
  } catch (error) {
    tunnel.status = 'ERROR'
    tunnel.logs = [...(tunnel.logs || []), `${new Date().toISOString()} ERROR ${error.message || 'START FAILED'}`]
  }
}

async function stopTunnel(tunnel) {
  if (!tunnel || !runtimeId.value || !tunnel.bridgeId) return
  try {
    await stopOperationTunnel(tunnel.runtimeId, tunnel.bridgeId)
    tunnel.status = 'STOPPED'
    tunnel.logs = [...(tunnel.logs || []), `${new Date().toISOString()} STOPPED`]
  } catch {
    tunnel.status = 'ERROR'
  }
  selectedTunnel.value = tunnel
}

function editTunnel(tunnel) {
  if (tunnel.status === 'RUNNING' || tunnel.status === 'STARTING') return
  const name = window.prompt('Tunnel name', tunnel.name)
  if (!name?.trim()) return
  const host = window.prompt('目标主机（从 SSH 服务器访问）', tunnel.targetHost)
  if (!host?.trim()) return
  const port = Number(window.prompt('目标端口', String(tunnel.targetPort)))
  const listenPort = Number(window.prompt('桥接服务器监听端口', String(tunnel.listenPort)))
  if (![port, listenPort].every(value => Number.isInteger(value) && value > 0 && value <= 65535)) return
  Object.assign(tunnel, { name: name.trim(), targetHost: host.trim(), targetPort: port, listenPort })
}

async function removeTunnel(tunnel) {
  if (!window.confirm(`Delete tunnel ${tunnel.name}?`)) return
  if (tunnel.status === 'STARTING') return
  if (tunnel.bridgeId) { await stopTunnel(tunnel); if (tunnel.status !== 'STOPPED') return }
  tunnels.value = tunnels.value.filter(item => item.id !== tunnel.id)
  if (selectedTunnel.value?.id === tunnel.id) selectedTunnel.value = null
}

function showTunnelLogs(tunnel) {
  window.alert((tunnel.logs || []).join('\n') || 'No tunnel logs')
}

async function connectSelected(decision = 'NONE') {
  if (!selectedSession.value || connecting.value || runtimeOnline.value) return
  const target = selectedSession.value
  connecting.value = true
  connectionError.value = ''
  try {
    const response = await connectOperationSession(target.id, decision)
    const result = response.data?.data || response.data
    if (result?.status === 'HOST_KEY_REQUIRED') {
      hostKey.value = result
      return
    }
    if (result?.status !== 'ONLINE') {
      connectionError.value = `${result?.stage || 'CONNECT'} ${result?.message || 'FAILED'}`
      return
    }
    if (!result.runtimeId) throw new Error('连接响应缺少运行时标识')
    openTabs.value.push({ runtimeId: result.runtimeId, session: { ...target }, status: '正在连接终端' })
    runtimeId.value = result.runtimeId
    setActiveOperationRuntime({ runtimeId: result.runtimeId, sessionName: target.name, host: target.host })
    activeWorkspace.value = 'TERMINAL'
    await loadAgentContext(result.runtimeId)
  } catch (error) {
    connectionError.value = `${target.host}:${target.port} ${target.protocol} · ${error.message || '连接失败'}`
  } finally {
    connecting.value = false
  }
}

async function previewCommand() {
  if (!multiCommand.value.trim() || !selectedRuntimeIds.value.length) { connectionError.value = '请选择至少一个在线目标并填写命令'; return }
  try {
    const targets = onlineTabs.value.filter(tab => selectedRuntimeIds.value.includes(tab.runtimeId))
    const response = await previewMultiExec({ command: multiCommand.value, runtimeIds: targets.map(tab => tab.runtimeId), productionTarget: targets.some(tab => /prod/i.test(tab.session.name || '')) })
    multiPreview.value = response.data?.data || response.data
    multiApprovalStep.value = 0
  } catch (error) { connectionError.value = error.message || '无法生成命令风险预览' }
}

async function approveCommand() {
  if (!multiPreview.value) return
  if (multiPreview.value.requiredApprovals > 1 && multiApprovalStep.value === 0) { multiApprovalStep.value = 1; return }
  try {
    const result = await executeMultiExec({ previewId: multiPreview.value.id, confirmationNonce: multiPreview.value.confirmationNonce, secondConfirmationNonce: multiPreview.value.requiredApprovals > 1 ? multiPreview.value.confirmationNonce : undefined })
    const execution = result.data?.data || result.data
    const failed = execution?.results?.filter(item => item.status !== 'SENT') || []
    if (failed.length) connectionError.value = `${failed.length} 个目标未发送`
  } catch (error) { connectionError.value = error.message || '批量命令未发送'; return }
  showMultiExec.value = false
  multiPreview.value = null
  multiCommand.value = ''
  selectedRuntimeIds.value = []
  multiApprovalStep.value = 0
}

function openMultiExec() {
  selectedRuntimeIds.value = runtimeId.value ? [runtimeId.value] : []
  multiCommand.value = ''
  multiPreview.value = null
  multiApprovalStep.value = 0
  showMultiExec.value = true
}

async function submitCreate() {
  if (!canSubmit.value) return
  try {
    const response = await createOperationSession({ ...draft.value })
    const created = response.data?.data || response.data
    if (created) sessions.value = [...sessions.value, created]
    if (created) selectSession(created)
    showCreate.value = false
    draft.value = { protocol: 'SSH', name: '', host: '', port: 22, username: '' }
  } catch (error) {
    connectionError.value = error.message || '保存会话失败'
  }
}

async function loadResources() {
  if (initialLoading.value) return
  initialLoading.value = true
  initialError.value = ''
  try {
    const [capabilityResponse, sessionResponse] = await Promise.all([getOperationCapabilities(), getOperationSessions()])
    const nextCapabilities = capabilityResponse.data?.data || capabilityResponse.data
    const nextSessions = sessionResponse.data?.data || sessionResponse.data
    if (!Array.isArray(nextCapabilities) || !Array.isArray(nextSessions)) throw new Error('连接资源响应格式异常')
    capabilities.value = nextCapabilities.filter(item => item && typeof item.protocol === 'string')
    sessions.value = nextSessions.filter(item => item && item.id != null)
  } catch (error) {
    initialError.value = error.message || '无法加载连接资源'
  } finally {
    initialLoading.value = false
  }
}
onMounted(loadResources)
</script>

<style scoped>
:global([data-theme='light'] .connections-page) { color: var(--smart-text); }
:global([data-theme='light'] .connections-page .capability-row > span) { color: var(--smart-text); }
:global([data-theme='light'] .connections-page .capability-row small.supported),
:global([data-theme='light'] .connections-page .remote-state.online) { color: var(--smart-success); }
:global([data-theme='light'] .connections-page .remote-state.offline),
:global([data-theme='light'] .connections-page .capability-warning) { color: var(--smart-warning); }
:global([data-theme='light'] .connections-page :is(.session-tree, .server-inspector, .terminal-workspace, .connection-status)) { background: var(--smart-surface); border-color: var(--smart-border-strong); }
:global([data-theme='light'] .connections-page :is(h1, h2, h3, strong, label, [role='alert'])) { color: var(--smart-text); }
:global([data-theme='light'] .connections-page :is(.section-kicker, .eyebrow, small, .workspace-name span, .workspace-empty p, .inspector-empty, .session-empty p)) { color: var(--smart-muted); }
:global([data-theme='light'] .connections-page :is(.icon-action, .new-session, .session-search input, .create-session input, .create-session select, .create-session textarea, .runtime-tabs button, .toolbar-actions button, .form-actions button)) { background: var(--smart-surface); color: var(--smart-text); border-color: var(--smart-border-strong); }
:global([data-theme='light'] .connections-page :is(.panel-heading, .subsection-heading, .workspace-toolbar, .connections-header, .workspace-empty, .inspector-section)) { border-color: var(--smart-border); }
:global([data-theme='light'] .connections-page .session-row.selected) { background: var(--smart-primary-soft); border-color: var(--smart-primary-strong); }
.connections-page {
  display: grid;
  gap: 18px;
  padding-bottom: 28px;
  color: #dce5e9;
}

.connections-header {
  display: flex;
  min-height: 66px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 8px 0 14px;
  border-bottom: 1px solid #18222d;
}

.eyebrow,
.section-kicker {
  margin: 0;
  color: #8c9ba5;
  font: 10px var(--font-mono);
  letter-spacing: .08em;
}

.eyebrow span {
  margin-left: 8px;
  color: #a8b5bc;
  font-family: var(--font-cn);
  letter-spacing: 0;
}

.connections-header h1 {
  margin: 6px 0 0;
  color: #eef4f6;
  font: 500 22px/1.25 var(--font-cn);
}

.connection-status {
  display: flex;
  min-width: 180px;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #18222d;
  background: #0b1118;
}

.status-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #f59e0b;
}

.connection-status.ready .status-dot,
.inspector-state.online::before {
  background: #22c55e;
}

.connection-status strong,
.connection-status small {
  display: block;
}

.connection-status strong {
  color: #dce5e9;
  font-size: 12px;
  font-weight: 550;
}

.connection-status small {
  margin-top: 3px;
  color: #8c9ba5;
  font-size: 11px;
}

.operations-workspace {
  display: grid;
  min-height: min(660px, calc(100vh - 190px));
  grid-template-columns: 236px minmax(0, 1fr) 250px;
  border: 1px solid #18222d;
  background: #080e14;
}
.operations-workspace.session-tree-hidden { grid-template-columns: minmax(0, 1fr) 250px; }
.operations-workspace.server-inspector-hidden { grid-template-columns: 236px minmax(0, 1fr); }
.operations-workspace.session-tree-hidden.server-inspector-hidden { grid-template-columns: minmax(0, 1fr); }
.operations-workspace.session-tree-hidden .session-tree { display: none; }
.operations-workspace.server-inspector-hidden .server-inspector { display: none; }

.session-tree,
.server-inspector {
  min-width: 0;
  padding: 16px;
  background: #0b1118;
}

.session-tree {
  border-right: 1px solid #18222d;
}

.server-inspector {
  border-left: 1px solid #18222d;
}

.panel-heading,
.inspector-heading,
.subsection-heading,
.idle-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-heading h2,
.subsection-heading h3,
.idle-heading h2 {
  margin: 0;
  color: #e2eaed;
  font-size: 13px;
  font-weight: 550;
}

.panel-heading small,
.subsection-heading small {
  display: block;
  margin-top: 4px;
  color: #84939d;
  font-size: 11px;
}

.icon-action {
  width: 34px;
  height: 34px;
  border: 1px solid #263541;
  background: #101922;
  color: #dce5e9;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}

.session-search {
  display: grid;
  gap: 6px;
  margin: 20px 0 12px;
}

.session-search span {
  color: #8998a1;
  font-size: 11px;
}

.session-search input {
  width: 100%;
  box-sizing: border-box;
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid #263541;
  border-radius: 3px;
  outline: none;
  background: #080e14;
  color: #e2eaed;
  font: 12px var(--font-cn);
}

.session-search input:focus,
.create-session input:focus,
.create-session select:focus,
.create-session textarea:focus {
  border-color: #38bdf8;
}

.session-list {
  display: grid;
  max-height: 420px;
  gap: 3px;
  overflow-y: auto;
}

.session-row {
  display: grid;
  min-width: 0;
  gap: 5px;
  padding: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: #dce5e9;
  text-align: left;
  cursor: pointer;
}

.session-row:hover,
.session-row.selected {
  border-color: #263541;
  background: #111a22;
}

.session-protocol {
  color: #38bdf8;
  font: 10px var(--font-mono);
}

.session-row strong,
.session-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-row strong {
  font-size: 12px;
  font-weight: 550;
}

.session-row small {
  color: #91a0a8;
  font: 10px var(--font-mono);
}

.session-empty,
.inspector-empty {
  padding: 14px 0;
  color: #a8b5bc;
  font-size: 12px;
}

.session-empty p {
  margin: 7px 0 0;
  color: #84939d;
  line-height: 1.5;
}

.new-session,
.text-action {
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid #263541;
  background: transparent;
  color: #c9d5da;
  font: 12px var(--font-cn);
  cursor: pointer;
}

.new-session {
  width: 100%;
  margin-top: 14px;
}

.new-session:hover,
.text-action:hover,
.icon-action:hover {
  border-color: #3a5261;
  background: #111a22;
}

.terminal-workspace {
  display: flex;
  flex-direction: column;
  min-width: 0;
  grid-template-rows: auto 1fr auto;
  background: #080e14;
}

.runtime-tabs { display:flex; flex-wrap:wrap; gap:4px; padding:8px; border-bottom:1px solid #263541; }
.runtime-tabs > div { display:flex; max-width:100%; }
.runtime-tabs button { color:#a8b5bc; background:#0b1118; border:1px solid #263541; padding:8px; overflow-wrap:anywhere; cursor:pointer; }
.runtime-tabs button[aria-pressed="true"] { color:#7ad7f5; border-color:#4d819a; }
.runtime-panes { display:grid; grid-template-columns:minmax(0,1fr); min-width:0; }
.runtime-panes.split_vertical { grid-template-columns:repeat(2,minmax(0,1fr)); }
@media (max-width:1024px) { .runtime-panes.split_vertical { grid-template-columns:minmax(0,1fr); } }

.workspace-toolbar {
  display: flex;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid #18222d;
}

.workspace-name span,
.workspace-name strong {
  display: block;
}

.workspace-name span {
  color: #84939d;
  font-size: 10px;
}

.workspace-name strong {
  margin-top: 4px;
  color: #dce5e9;
  font-size: 12px;
  font-weight: 550;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.toolbar-actions button,
.recent-session button,
.form-actions button {
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid #263541;
  border-radius: 3px;
  background: #0d151d;
  color: #b9c7cd;
  font: 11px var(--font-cn);
  cursor: pointer;
}

.toolbar-actions button.active,
.toolbar-actions button.primary-action,
.primary-action {
  border-color: #246b50;
  background: #123124;
  color: #a9e8c3;
}

button:disabled {
  opacity: .42;
  cursor: not-allowed;
}

.workspace-idle {
  display: grid;
  align-content: start;
  gap: 16px;
  min-height: 0;
  padding: 20px;
}

.section-kicker {
  display: block;
  margin-bottom: 6px;
}

.idle-heading h2 {
  font-size: 15px;
}

.recent-sessions {
  display: grid;
  border-top: 1px solid #18222d;
}

.recent-session {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 2px;
  border-bottom: 1px solid #18222d;
}

.recent-session-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.recent-session-copy strong,
.recent-session-copy span,
.recent-session-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-session-copy strong {
  color: #e2eaed;
  font-size: 12px;
}

.recent-session-copy span {
  color: #aab8be;
  font: 11px var(--font-mono);
}

.recent-session-copy small {
  color: #84939d;
  font-size: 10px;
}

.recent-session button {
  min-width: 58px;
  color: #a9e8c3;
}

.workspace-empty {
  align-self: center;
  padding: 28px 0;
  border-top: 1px solid #18222d;
}

.workspace-empty h3 {
  margin: 0;
  color: #dce5e9;
  font-size: 14px;
  font-weight: 550;
}

.workspace-empty p {
  max-width: 500px;
  margin: 8px 0 14px;
  color: #91a0a8;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.connection-error,
.context-error {
  color: #fca5a5;
  font-size: 12px;
}

.inspector-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #aab8be;
  font-size: 11px;
}

.inspector-state::before {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #64717a;
  content: '';
}

.inspector-state.online {
  color: #86d6a7;
}

.inspector-content {
  margin-top: 16px;
}

.session-details {
  margin: 0;
}

.session-details div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  padding: 9px 0;
  border-top: 1px solid #18222d;
}

.session-details dt {
  color: #84939d;
  font-size: 11px;
}

.session-details dd {
  min-width: 0;
  margin: 0;
  color: #c9d5da;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.agent-context,
.capability-list {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #263541;
}

.subsection-heading h3 {
  font-size: 12px;
}

.subsection-heading span {
  color: #86d6a7;
  font-size: 10px;
}

.agent-context > p {
  margin: 10px 0 0;
  color: #91a0a8;
  font-size: 11px;
  line-height: 1.55;
}

.allowed-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 10px 0;
  padding: 0;
  list-style: none;
}

.allowed-actions li {
  padding: 4px 6px;
  border: 1px solid #263541;
  color: #b9c7cd;
  font-size: 10px;
}

.agent-context .approval-boundary {
  color: #f4c879;
}

.capability-list {
  margin-top: 18px;
}

.capability-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #18222d;
  color: #c9d5da;
  font: 10px var(--font-mono);
}

.capability-row small {
  color: #b6a06b;
  font: 10px var(--font-cn);
  text-align: right;
}

.capability-row small.supported {
  color: #86d6a7;
}

.create-overlay {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(3, 7, 13, .78);
}

.create-session {
  width: min(100%, 500px);
  padding: 24px;
  border: 1px solid #263541;
  background: #0b1118;
  box-shadow: 0 22px 70px rgba(0, 0, 0, .4);
}

.create-session h2 {
  margin: 6px 0 24px;
  color: #eef4f6;
  font-size: 22px;
  font-weight: 550;
}

.create-session label {
  display: grid;
  gap: 7px;
  margin: 15px 0;
  color: #a8b5bc;
  font-size: 11px;
}

.create-session input,
.create-session select,
.create-session textarea {
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid #263541;
  border-radius: 3px;
  outline: none;
  background: #080e14;
  color: #e2eaed;
  font: 12px var(--font-cn);
  resize: vertical;
}

.capability-warning {
  padding: 10px;
  border-left: 2px solid #f59e0b;
  color: #f4c879;
  font-size: 11px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 22px;
}

.host-key-copy {
  color: #a8b5bc;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.host-key-dialog code {
  display: block;
  margin: 18px 0;
  padding: 12px;
  border: 1px solid #263541;
  color: #c9d5da;
  font: 11px var(--font-mono);
  overflow-wrap: anywhere;
}

.risk-preview {
  display: grid;
  gap: 7px;
  margin: 18px 0;
  padding: 12px;
  border: 1px solid #263541;
  border-left: 3px solid #38bdf8;
  background: #0d151d;
}

.risk-preview span,
.risk-preview small {
  color: #a8b5bc;
  font-size: 11px;
}

.risk-preview strong {
  color: #38bdf8;
  font-size: 14px;
}

.risk-preview strong.high,
.risk-preview strong.critical {
  color: #ef4444;
}

@media (max-width: 1180px) {
  .operations-workspace {
    grid-template-columns: 210px minmax(0, 1fr);
  }

  .server-inspector {
    grid-column: 1 / -1;
    border-top: 1px solid #18222d;
    border-left: 0;
  }

  .inspector-content {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 18px;
  }

  .agent-context {
    margin-top: 0;
  }

  .capability-list {
    grid-column: 1 / -1;
  }
}

@media (max-width: 700px) {
  .connections-header {
    align-items: flex-start;
  }

  .connection-status {
    min-width: 0;
    padding: 8px;
  }

  .connection-status small {
    display: none;
  }

  .operations-workspace {
    display: flex;
    min-height: 0;
    flex-direction: column;
  }

  .session-tree,
  .server-inspector {
    border-right: 0;
    border-bottom: 1px solid #18222d;
  }

  .session-list {
    max-height: 210px;
  }

  .terminal-workspace {
    min-height: 380px;
  }

  .workspace-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .inspector-content {
    display: block;
  }

  .agent-context {
    margin-top: 16px;
  }
}
.remote-menu{display:flex;align-items:center;gap:0;min-height:30px;padding:0 5px;border:1px solid var(--smart-border);border-bottom:0;background:var(--smart-surface);overflow-x:auto}.remote-menu button{min-height:29px;padding:3px 10px;border:0;background:transparent;color:var(--smart-muted);font:12px var(--font-cn);cursor:pointer;white-space:nowrap}.remote-menu button:hover,.remote-menu button:focus-visible{background:color-mix(in srgb,var(--smart-primary-strong) 10%,transparent);color:var(--smart-text);outline:none}.remote-toolbar{display:flex;align-items:stretch;gap:2px;padding:8px 10px;border:1px solid var(--smart-border);background:color-mix(in srgb,var(--smart-surface) 92%,transparent);overflow-x:auto}.remote-toolbar button{display:grid;justify-items:center;gap:4px;min-width:70px;padding:6px 11px;border:0;border-right:1px solid var(--smart-border);background:transparent;color:var(--smart-muted);font:10px var(--font-cn);cursor:pointer;white-space:nowrap}.remote-toolbar button:hover,.remote-toolbar button:focus-visible{color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 8%,transparent);outline:none}.remote-toolbar button:disabled{opacity:.35;cursor:not-allowed}.remote-toolbar svg{width:22px;height:22px;color:var(--smart-primary-strong)}.remote-welcome{display:grid;justify-items:center;gap:12px;padding:28px 18px 24px;text-align:center}.remote-logo{display:grid;place-items:center;width:72px;height:62px;border:4px solid #76828a;background:#202a33;box-shadow:6px 6px 0 #eb463f,12px 12px 0 #36a4dd,18px 18px 0 #9ecb3b;transform:skew(-8deg)}.remote-logo span{color:#fff;font:700 22px var(--font-mono);transform:skew(8deg)}.remote-welcome h2{margin:5px 0 8px;color:var(--smart-text);font:400 38px var(--font-cn);letter-spacing:.01em}.welcome-actions{display:flex;gap:18px}.welcome-actions button{min-width:220px;padding:12px 20px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);font:16px var(--font-cn);cursor:pointer}.welcome-actions button:hover{border-color:var(--smart-primary-strong);color:var(--smart-primary-strong)}.welcome-actions .primary-action{border-color:#65a7ff;background:color-mix(in srgb,#65a7ff 8%,var(--smart-surface));color:var(--smart-text)}.action-plus{display:inline-grid;place-items:center;width:20px;height:20px;margin-right:5px;border-radius:50%;background:#53b86a;color:#fff}.welcome-search{width:min(620px,90%);margin-top:6px}.welcome-search input{width:100%;padding:10px 14px;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);font:15px var(--font-cn);outline:none}.welcome-search input:focus{border-color:var(--smart-primary-strong)}.remote-status-banner{display:flex;align-items:flex-start;gap:12px;padding:16px;border:1px solid var(--smart-border);background:var(--smart-bg)}.remote-status-banner strong{color:var(--smart-text);font-size:14px}.remote-status-banner p{margin:6px 0 0;color:var(--smart-muted);font-size:12px;line-height:1.6}.remote-status-dot{width:9px;height:9px;margin-top:5px;border-radius:50%;background:#f4c879;box-shadow:0 0 10px color-mix(in srgb,#f4c879 45%,transparent)}.remote-status-dot.offline{background:#f4c879}@media(max-width:760px){.remote-menu button{padding-inline:8px}.remote-toolbar button{min-width:58px;padding-inline:7px}.remote-welcome h2{font-size:30px}.welcome-actions{flex-direction:column;gap:8px}.welcome-actions button{min-width:240px}}
.remote-tool-overlay{position:fixed;inset:0;z-index:40;display:grid;place-items:center;padding:clamp(12px,3vw,36px);background:rgba(2,7,12,.72);backdrop-filter:blur(3px)}
.remote-tool-dialog{display:flex;width:min(880px,100%);max-height:min(760px,calc(100vh - 32px));flex-direction:column;border:1px solid var(--smart-border-strong);background:var(--smart-surface);box-shadow:0 24px 80px rgba(0,0,0,.5);overflow:hidden}
.remote-tool-dialog-header{display:flex;justify-content:space-between;gap:18px;padding:20px 24px;border-bottom:1px solid var(--smart-border);background:linear-gradient(90deg,color-mix(in srgb,var(--smart-primary-strong) 9%,var(--smart-surface)),var(--smart-surface))}
.remote-tool-dialog-header h2{margin:4px 0 5px;color:var(--smart-text);font-size:22px;font-weight:550}.remote-dialog-subtitle{margin:0;color:var(--smart-muted);font-size:12px}.remote-dialog-close{position:sticky;top:0;align-self:flex-start;display:grid;place-items:center;width:34px;height:34px;padding:0;border:1px solid var(--smart-border-strong);background:var(--smart-surface);color:var(--smart-text);font-size:23px;line-height:1;cursor:pointer}.remote-dialog-close:hover,.remote-dialog-close:focus-visible{border-color:var(--smart-primary-strong);color:var(--smart-primary-strong);outline:2px solid color-mix(in srgb,var(--smart-primary-strong) 30%,transparent);outline-offset:2px}
.remote-tool-dialog-body{min-height:0;padding:22px 24px;overflow:auto;color:var(--smart-text)}.remote-inline-form{display:flex;align-items:end;gap:12px;flex-wrap:wrap}.remote-inline-form label,.remote-search-field,.remote-setting-list label{display:grid;gap:7px;color:var(--smart-muted);font-size:12px}.remote-inline-form label{flex:1;min-width:240px}.remote-tool-dialog input,.remote-tool-dialog select{min-height:36px;padding:8px 10px;border:1px solid var(--smart-border-strong);background:var(--smart-bg);color:var(--smart-text);font:12px var(--font-cn);outline:none}.remote-tool-dialog input:focus,.remote-tool-dialog select:focus{border-color:var(--smart-primary-strong)}.remote-tool-note{margin:16px 0 0;padding:12px 14px;border-left:3px solid var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 7%,transparent);color:var(--smart-muted);font-size:12px;line-height:1.6}.remote-stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:20px}.remote-stat-grid div{display:grid;gap:5px;padding:14px;border:1px solid var(--smart-border);background:var(--smart-bg)}.remote-stat-grid strong{color:var(--smart-primary-strong);font:24px var(--font-mono)}.remote-stat-grid span{color:var(--smart-muted);font-size:11px}.remote-tool-list,.remote-favorite-list{display:grid;gap:8px;margin-bottom:18px}.remote-tool-row{display:flex;justify-content:space-between;padding:11px 12px;border-bottom:1px solid var(--smart-border);font-size:12px}.remote-state{font-size:11px}.remote-state.online{color:#86d6a7}.remote-state.offline{color:#f4c879}.remote-tool-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.remote-tool-grid button,.split-choice-grid button{display:grid;gap:6px;min-height:76px;padding:13px;text-align:left;border:1px solid var(--smart-border);background:var(--smart-bg);color:var(--smart-text);font:13px var(--font-cn);cursor:pointer}.remote-tool-grid button:hover:not(:disabled),.split-choice-grid button:hover:not(:disabled),.split-choice-grid button.selected{border-color:var(--smart-primary-strong);background:color-mix(in srgb,var(--smart-primary-strong) 9%,var(--smart-bg))}.remote-tool-grid small,.split-choice-grid small{color:var(--smart-muted);font-size:10px}.remote-tool-grid button:disabled,.split-choice-grid button:disabled{cursor:not-allowed;opacity:.42}.remote-search-field{margin-bottom:14px}.remote-favorite-row{display:flex;align-items:center;gap:12px;width:100%;padding:12px;border:1px solid var(--smart-border);background:var(--smart-bg);color:var(--smart-text);text-align:left;cursor:pointer}.remote-favorite-row:hover{border-color:var(--smart-primary-strong)}.remote-favorite-row span:nth-child(2){display:grid;gap:4px;flex:1}.remote-favorite-row small{color:var(--smart-muted);font-size:11px}.remote-chevron{font-size:24px;color:var(--smart-muted)}.remote-empty{padding:34px 12px;border:1px dashed var(--smart-border-strong);color:var(--smart-muted);text-align:center;font-size:12px}.remote-setting-list{display:grid;gap:14px}.remote-setting-list label{grid-template-columns:1fr auto;align-items:center}.remote-setting-list label input[type=checkbox]{justify-self:start;grid-column:1}.remote-setting-list label small{grid-column:1 / -1;color:var(--smart-muted);font-size:10px}.remote-setting-list select{min-width:180px}.remote-setting-list button{min-height:36px;padding:0 12px;border:1px solid var(--smart-border-strong);background:var(--smart-bg);color:var(--smart-text);cursor:pointer}.split-choice-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.remote-help-content{max-width:680px;color:var(--smart-muted);font-size:13px;line-height:1.8}.remote-help-content h3{margin-top:0;color:var(--smart-text)}
@media(max-width:700px){.remote-tool-dialog-header{padding:16px}.remote-tool-dialog-body{padding:16px}.remote-stat-grid,.remote-tool-grid,.split-choice-grid{grid-template-columns:1fr 1fr}.remote-tool-grid button{min-height:66px}.remote-setting-list label{grid-template-columns:1fr}.remote-setting-list select{width:100%}}@media(max-width:460px){.remote-stat-grid,.remote-tool-grid,.split-choice-grid{grid-template-columns:1fr}}
</style>
