<template>
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
</template>

<script setup>
import { inject } from 'vue'
import { CONNECTIONS_WORKSPACE_KEY } from '../../composables/useConnectionsWorkspace.js'

const {
  query,
  sessions,
  filteredSessions,
  selectedSession,
  initialLoading,
  initialError,
  showCreate,
  selectSession
} = inject(CONNECTIONS_WORKSPACE_KEY)
</script>

<style scoped>
.session-tree {
  min-width: 0;
  padding: 16px;
  background: #0b1118;
  border-right: 1px solid #18222d;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-heading h2 {
  margin: 0;
  color: #e2eaed;
  font-size: 13px;
  font-weight: 550;
}

.panel-heading small {
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

.session-search input:focus {
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

.session-empty {
  padding: 14px 0;
  color: #a8b5bc;
  font-size: 12px;
}

.session-empty p {
  margin: 7px 0 0;
  color: #84939d;
  line-height: 1.5;
}

.new-session {
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid #263541;
  background: transparent;
  color: #c9d5da;
  font: 12px var(--font-cn);
  cursor: pointer;
  width: 100%;
  margin-top: 14px;
}

.new-session:hover,
.icon-action:hover {
  border-color: #3a5261;
  background: #111a22;
}

@media (max-width: 700px) {
  .session-tree {
    border-right: 0;
    border-bottom: 1px solid #18222d;
  }

  .session-list {
    max-height: 210px;
  }
}
</style>
