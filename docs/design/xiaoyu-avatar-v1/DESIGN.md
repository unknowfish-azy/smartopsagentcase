# 小鱼 · 3D 数字人整合方案

> 原名：Agent Persona（sendagaya-shino VRM 少女 + 程序化深海发光体）
> 更名：**小鱼** — 蓝发少女的海洋主题人格化身

---

## 一、现状盘点

### 已有资产

| 组件 | 文件 | 作用 |
|---|---|---|
| AgentPersona.vue | `frontend/src/components/persona/AgentPersona.vue` | 核心 3D 舞台，mode="vrm"/"programmatic" 双模式，setState/attachAudio/speakText 等命令式接口 |
| PersonaPet.vue | `frontend/src/components/persona/PersonaPet.vue` | **悬浮桌宠**：拖拽浮窗，默认收起小球，speak/rest/mini 按钮 |
| personaPet.js store | `frontend/src/stores/personaPet.js` | enable/collapsed/position 持久化 |
| personaStates.js | `frontend/src/components/persona/personaStates.js` | 七状态 profile（idle/thinking/executing/observing/warning/error/recovering） |
| useVrmModel.js | `frontend/src/components/persona/useVrmModel.js` | VRM 模型加载 + 主题化（applyOceanTone） |
| useProgrammaticAvatar.js | `frontend/src/components/persona/useProgrammaticAvatar.js` | 程序化深海发光体（零资产备选） |
| public/avatar/sendagaya-shino/model.vrm | `frontend/public/...` | CC0 VRM 少女模型 |

### 待接入入口

| 页面 | 路由 | 当前形态 | 目标 |
|---|---|---|---|
| Dashboard | `/` | briefing 头部只有 SVG 图标 | 替换为小鱼形象 + 快捷对话输入 |
| Chat | `/chat` | 纯文本对话，无形象 | header 旁加小鱼头像（半身缩图） |
| PersonaPet | 全局 | ✅ 悬浮桌宠 | 保留，名称文案改小鱼 |
| AgentPersona | `/agent/persona` | ✅ 全页展示 | 保留，名称文案改小鱼 |

---

## 二、命名统一

| 位置 | 原文本 | 新文本 |
|---|---|---|
| PersonaPet.vue 标题 | 数字人 | 小鱼 |
| PersonaPet.vue 按钮 aria | 数字人桌宠 | 小鱼桌宠 |
| AgentPersona.vue 状态文案 | 当前状态：xxx | 小鱼 · 当前状态：xxx |
| store defineStore id | persona-pet | xiaoyu-pet |
| 路由名 AgentPersona | AgentPersona | XiaoyuAvatar |
| 路由 section | AGENT PERSONA / 人格化身 | 小鱼 / 3D 化身 |
| PersonaPet store toggle 按钮 | 桌宠·开/关 | 小鱼·开/关 |

> **不修改文件名**（避免大规模重构 + 测试重写），只改对外展示文本和 store id。文件路径保持 `components/persona/*`，降低回归风险。

---

## 三、首页 Dashboard 小鱼面板

### 布局改动

DashboardBento.vue 当前 12 列 bento：

```
[ briefing (1/12) ]
[ KPI×4 (各 3 列) ]
[ alerts (8 列) | actions (4 列) ]
[ distribution (7 列) | trend (5 列) ]
```

**新布局** — 用小鱼面板替换 "快捷入口 actions" 卡片：

```
[ briefing (1/12) ]           ← 加小鱼头像替换 SVG
[ KPI×4 (各 3 列) ]
[ alerts (6 列) | 小鱼面板 (6 列) ]   ← 把 actions 换成小鱼
[ distribution (7 列) | trend (5 列) ]
```

### 小鱼面板组件 XiaoyuDashboardCard.vue

```
┌─ 小鱼 · 智维 Agent ──────────────────────┐
│  ┌──────────┐                              │
│  │ 3D 半身  │   当前状态：待机              │
│  │  WebGL   │   今日已巡检 12 项 · 2 告警   │
│  │ (180×220)│                              │
│  └──────────┘                              │
│  "你好，今天想让我做什么？"                  │
│  [ 一键体检 ] [ 读取知识库 ] [ 解释告警 ]    │
│  ── RAG 状态 ──                             │
│  知识条目 284 · 向量索引就绪 · 命中 3         │
│  ── Agent 训练 ──                           │
│  对话 156 · 技能 8 · 最后微调 3 天前         │
└────────────────────────────────────────────┘
```

### 组件规格

| 属性 | 说明 |
|---|---|
| 尺寸 | 固定 6 列 × ~360px 高，和 alerts 卡片等高 |
| 3D 区域 | AgentPersona `mode="vrm"`，quality="high"，比例 16:9 竖屏裁剪，只露上半身 |
| 对话气泡 | Textarea（3 行）+ 发送按钮，走现有 /chat 接口 |
| 快捷操作 | 3 个按钮 → 触发已有的 health/sentinel/knowledge 路由跳转 |
| RAG 状态 | 读 `api/personalKnowledge` + `api/modelGovernance/rag`（占位 mock） |
| 训练状态 | 读 `api/modelGovernance/stats`（占位 mock） |

### 懒加载策略

- XiaoyuDashboardCard 本身 `defineAsyncComponent`
- AgentPersona 在 Dashboard 首次进入时才挂载，离开页面时 dispose
- lightweight 档位：3D 换成静态插画（和桌宠降级逻辑一致）

---

## 四、ChatView 小鱼形象

### 方案：侧边头像 + 状态气泡

在 ChatView.vue 的 **header 右侧**加一个小鱼头像（120px 半身 canvas 缩图），不阻塞对话主区：

```
┌─ AI 对话 ──┬─ 小鱼 ────────────────┐
│  会话列表   │  (半身 120px)          │
│            │  "我在，说吧"             │
│            │ ─────────────────────── │
│            │  对话消息区              │
│            │                         │
│            │  输入框                  │
└────────────┴─────────────────────────┘
```

或者更轻量：**把小鱼放进 header 右侧 badge 旁边**（64px 圆形 canvas），点击展开一个侧拉面板显示完整半身 + 快捷对话。

**选用后者**，不破坏现有 ChatView 的 grid 布局。

### 组件 XiaoyuChatAvatar.vue

- 64px 圆形头像，AgentPersona 用 CSS `transform: scale(0.35)` + clip 裁圆
- 点击展开 Drawer（280px 宽）：半身 200px + 快捷操作 + 最近 RAG 命中
- Drawer 关闭时 canvas dispose，节省资源

---

## 五、小鱼功能面（面板里能做什么）

### P0 · 必做（Dashboard 面板里直接可用）

| 功能 | 数据源 | 交互 |
|---|---|---|
| 状态展示 | `personaStates` + sentinel/inspector 摘要 | 小鱼随巡检状态切换 7 姿态 |
| 快捷对话 | `/api/ai/chat`（已有） | Textarea + 发送 → 结果回写到对话气泡 |
| RAG 状态 | `listKnowledgeLibraries()` + mock 向量索引 | 知识条目数 · 索引就绪 · 最近命中 |
| Agent 统计 | mock（训练对话数 / 技能数 / 最后微调） | 只读展示，无点击入口 |

### P1 · 可点击跳转

| 入口 | 目标路由 | 文案 |
|---|---|---|
| 一键体检 | `/health` | 让小鱼"说"出当前巡检摘要 |
| 读取知识库 | `/knowledge` | 跳转知识检索页 |
| 解释告警 | `/sentinel/alerts` | 带告警 ID 预填 |

### P2 · 二期（不进本次）

- **真正的 RAG 检索**：输入自然语言 → 查知识向量库 → 返回相关条目
- **对话历史 → 训练数据集**：标记好对话 → 加入微调数据集
- **微调状态 Webhook**：训练完成通知小鱼切换到 "recovering" 状态
- **语音输入麦克风按钮**：用 Web Speech API

---

## 六、文件变更清单

### 新增

| 文件 | 作用 |
|---|---|
| `frontend/src/components/dashboard/XiaoyuDashboardCard.vue` | 首页小鱼面板（3D + 气泡 + RAG/训练状态） |
| `frontend/src/components/chat/XiaoyuChatAvatar.vue` | Chat header 小鱼头像 + Drawer |

### 修改

| 文件 | 改动 |
|---|---|
| `DashboardBento.vue` | 把 actions 卡片替换成 XiaoyuDashboardCard，briefing SVG 头像换成小鱼缩略 |
| `ChatView.vue` | header 加 XiaoyuChatAvatar |
| `MainLayout.vue` | personaPetStore id `persona-pet` → `xiaoyu-pet`（可选，影响 localStorage） |
| 所有 persona 组件内 | 文案 "数字人" → "小鱼"，"桌宠" → "小鱼" |
| 路由 routeMetadata | section 文案 |

### 不改（零风险）

- VRM 模型文件
- personaStates.js（七状态 profile 保持）
- useVrmModel.js / useProgrammaticAvatar.js
- AgentPersona.vue 核心逻辑

---

## 七、门禁要求

- eslint 零新增 error，warning 不超过 31
- typecheck 通过
- 现有 661 测试通过（**不新增测试**，P0 功能用已有的健康诊断/知识/RAG mock 数据源）
- Dashboard 和 Chat 页面正常渲染，小鱼面板不阻塞对话

---

## 八、分阶段执行

| 阶段 | 内容 | 验收 |
|---|---|---|
| **1. 文案 + store id 更名** | "数字人" → "小鱼"，store id 改，localStorage key 迁移 | 桌宠按钮显示 "小鱼·开"，刷新后记住上次状态 |
| **2. Dashboard 小鱼面板** | XiaoyuDashboardCard 组件嵌入 bento，替换 actions | 3D 少女在首页显示；快捷按钮能跳转 |
| **3. Chat 小鱼头像** | XiaoyuChatAvatar 加进 Chat header | 圆形小鱼在对话页右上；点击展开 Drawer |
| **4. 门禁 + 提交** | typecheck / lint / test / build | 全绿，commit + push |

---

## 九、风险与兜底

| 风险 | 兜底 |
|---|---|
| Dashboard 多挂载一个 AgentPersona 导致首屏卡 | defineAsyncComponent + lightweight 档位降级静态插画 |
| Chat 侧 Drawer 里的 3D 频繁创建销毁 | Drawer 关闭时 dispose canvas，不常驻 |
| 悬浮桌宠 + Dashboard + Chat 三处 WebGL 同屏 | personaPetActive 时 Dashboard 面板自动降级（MainLayout 已有 whale 让位逻辑，同理推小鱼） |
| localStorage 从 `persona-pet` 迁移到 `xiaoyu-pet` | 启动时读旧 key 迁移到新 key，保留用户开关/位置 |
