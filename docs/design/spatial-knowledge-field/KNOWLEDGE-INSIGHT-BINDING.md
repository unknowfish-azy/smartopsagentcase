# 知识库 ↔ 自然语言洞察 绑定契约 v1

日期：2026-11-14
上位设计：[`DESIGN.md`](./DESIGN.md) §4
适用代码：`frontend/src/views/knowledge/`、`frontend/src/views/insights/`、`knowledge/evidence/`

---

## 0. 一句话

**洞察不是知识的旁注，是知识的生成器。**
所以绑定不能是"给卡片贴个关联标签"，必须是**双向、带锚点、带可信档位、能闭环回流**的关系。空间场里它表现为一条垂直线；数据层它必须能被纯函数重建、被单测断言、被审计追溯。

本文回答四件事：数据长什么样（§2）、索引怎么建（§3）、怎么匹配且不编造（§4）、绑上之后能做什么（§5）、状态怎么流转（§6）、后端何时介入（§7）。

---

## 1. 现状与缺口（读码确认）

| 对象 | 现有字段 | 缺口 |
|---|---|---|
| 知识条目（`knowledgeCatalog.js` → `knowledgeEntries`） | `id, domain, platform, service, type, title, summary, content, source, section, version, risk, tags` | 无 `evidenceRefs`、无 `insightRefs`、无 `freshness` |
| 知识投影（`knowledgeModel.js` → `catalogProjection`） | 加上 `reviewStatus: 'UNVERIFIED'`（写死）、`lastVerifiedAt: null`（写死）、`visibility: 'BUILTIN'` | 复核状态是常量，未接真实复核数据 |
| 洞察（`NaturalLanguageInsightsView.vue`） | `kind, badge, title, source, question, description, charts|items, note, updatedAt` | 无 `id`、无 `binding`、无 `confidence`，与知识零关联 |
| 证据（`knowledge/evidence/models.py` → `Evidence`） | `evidence_id, chunk_id, source, content, score, version, metadata` | 与前端知识条目无连接键 |

**结论：两侧都缺共同的身份与锚点。** 绑定的第一步不是加 UI，是给两类对象补上可对齐的键与锚。

---

## 2. 数据契约

### 2.1 知识原子（`KnowledgeAtom`）

```ts
interface KnowledgeAtom {
  // ── 现有字段，不改语义 ──
  id: string
  domain: string            // 'nginx' | 'mysql' | 'linux' | ...
  platform: string          // 'Nginx' | 'Linux' | ...
  service: string
  type: string              // 'DIAGNOSIS RUNBOOK' | 'ENGINEERING KNOWLEDGE' | ...
  title: string
  summary: string
  content: string
  source: string
  section?: string
  version: string           // '1.24+'
  risk?: 'READ_ONLY' | 'LOW' | 'MEDIUM' | 'HIGH'
  tags: string[]

  // ── 新增：全部可选，缺省即"未提供"，不得补默认值冒充有 ──
  evidenceRefs?: EvidenceRef[]     // 向下：这个知识凭哪些证据
  insightRefs?: InsightRef[]       // 向上：哪些洞察引用了它（由索引重建，非手写）
  freshness?: Freshness
}

interface EvidenceRef {
  evidenceId: string               // 对应 knowledge/evidence/models.py::Evidence.evidence_id
  chunkId: string                  // 对应 Evidence.chunk_id
  source: string                   // 来源 URI / runbook 路径 / 巡检任务号
  version: string
  capturedAt: string               // ISO-8601
  note?: string                    // 人读的一句话，说明这条证据支持哪个论断
}

interface Freshness {
  verifiedAt: string | null        // 真实复核时间；null = 从未复核
  verifiedBy: string | null
  staleAfterDays: number           // 超过即判定 stale（渲染为沿 -Z 后退 + 雾化）
  status: 'FRESH' | 'STALE' | 'UNVERIFIED' | 'CONTRADICTED'
}

interface InsightRef {
  insightId: string
  relation: BindingRelation
  weight: number                   // 0..1，用于线程粗细与排序
}
```

### 2.2 洞察（`Insight`）

```ts
interface Insight {
  // ── 现有字段，不改语义（NaturalLanguageInsightsView 现有 4 个 intent 全部兼容）──
  id: string                       // 新增：稳定 ID，规则生成，如 'insight.alerts.active-severity'
  kind: 'chart' | 'list' | 'text' | 'unavailable'
  badge: string                    // 'ALERTS' | 'SERVERS' | 'KNOWLEDGE' | 'INSPECTOR'
  title: string
  source: string                   // 真实接口路径，如 '/api/sentinel/alerts'
  question: string                 // 触发它的原话
  description: string
  charts?: ChartSpec[]
  items?: { name: string, desc: string }[]
  note?: string                    // 口径声明（现有一致：'口径：待处理 / 待审批 / 处置中。'）
  updatedAt: string

  // ── 新增 ──
  confidence: 'observed' | 'derived' | 'inferred'   // 与项目证据纪律同构
  binding: InsightBinding
}

interface InsightBinding {
  mode: 'derived' | 'corroborates' | 'contradicts' | 'operational'
  atoms: AtomAnchor[]
  explanation: string              // 人读的匹配理由，禁止空字符串
}

interface AtomAnchor {
  atomId: string
  weight: number                   // 0..1
  anchor: {
    field: 'title' | 'summary' | 'content' | 'tags' | 'section'
    span?: [number, number]        // 在该字段内的字符区间；缺省 = 整字段
    chunkId?: string               // 若知识原子本身来自切片
  }
  stale?: boolean                  // 引用时该原子是否已过期（决定线程是否虚化）
}
```

### 2.3 关系语义（`BindingRelation` / `mode`）

| 值 | 含义 | 空间表现 | 触发条件（可判定，不靠语义猜测） |
|---|---|---|---|
| `derived` | 洞察由这些知识推导得出 | 实线，`accent-soft → accent` | 洞察的 `service`/`domain` 命中原子，且洞察文本引用了原子的 `tags` 或 `section` |
| `corroborates` | 洞察数据佐证了这些知识 | 实线更细 + 双向箭头 | 洞察数据源与被引用知识的 `service` 一致，且结论方向不冲突 |
| `contradicts` | 洞察与知识结论冲突 | **虚线 + 端点菱形**，颜色用 status 警示色 | 同 `service` + 同 `version` 下，洞察结论词项与原子结论词项互斥（结构判定，见 §4.3） |
| `operational` | 纯运行态洞察，不依赖任何知识 | 短横线 + 空心端点 | 无原子命中（如"活跃告警级别分布"当前就是这一类） |

**`operational` 是合法状态，不是缺陷。** 强行给纯数据洞察补一条知识连线，就是编造证据。

---

## 3. 索引构建（纯函数，可单测）

新文件 `frontend/src/views/knowledge/space/bindingIndex.js`：

```js
/**
 * buildBindingIndex(atoms, insights) -> {
 *   byAtom:   Map<atomId,  InsightRef[]>,
 *   byInsight: Map<insightId, AtomAnchor[]>,
 *   threads:  Array<{ insightId, atomId, relation, weight, stale }>,
 *   stats:    { bound, unbound, operational, contradicts, staleAtoms }
 * }
 *
 * 保证：
 *  - 纯函数，无 Date.now / Math.random / DOM
 *  - 同输入 → 同输出，threads 按 (insightId, atomId) 字典序稳定排序
 *  - 只重建 byAtom 的 insightRefs，绝不改写 atoms 的其余字段
 */
export function buildBindingIndex(atoms, insights) { /* … */ }
```

**规模与复杂度**：当前 `knowledgeEntries` 量级几百、洞察量级 ≤ 20，双向索引 O(n·m) 足够（< 5ms）。超过 5000 原子再引倒排表，现在**不做过度设计**。

**`stats` 的意义**：它是「绑定覆盖率」的唯一真实来源。空间场的 HUD 直接读它，展示为 `已绑定 12 / 未绑定 3 / 纯运行态 5 / 冲突 1 / 过期知识 4`。**没有这个数字，绑定就无法验收。**

---

## 4. 匹配规则（可解释、不编造）

### 4.1 打分（沿用 `knowledgeModel.js::rankKnowledgeEntries` 的可解释风格）

```
score(atom, insight) =
    3.0 · [atom.service === insight.service]          // 同服务最强
  + 2.0 · [atom.domain  === insight.domain]
  + 1.0 · [atom.platform 命中洞察 badge 的映射表]      // ALERTS→sre, SERVERS→linux, INSPECTOR→linux
  + 1.2 · |atom.tags ∩ tokens(insight.title + insight.question)| / max(1, |atom.tags|)
  + 0.8 · [insight.source 与 atom.source 同域]
  − 2.0 · [atom freshness.status === 'CONTRADICTED']
```

取 `score ≥ 1.5` 的前 3 条作为 `atoms`；若一条都不满足 → `mode = 'operational'`、`atoms = []`。

### 4.2 必须产出解释

`binding.explanation` 由命中项拼出，禁止留空，例如：

> `命题命中：服务 nginx ↔ nginx；标签命中 502、upstream；来源同域（Nginx Operations Pack）`

这条字符串会出现在洞察卡的 `note` 区与线程 hover 提示里——**用户要能看见"为什么这两件事被连起来"**。看不见理由的连线比没有连线更糟。

### 4.3 `contradicts` 的结构判定（Phase A 的诚实边界）

只做**同键互斥词**判定：

```
同一 service + 同一 version 下：
  知识原子结论含 { 无需重启, 不影响, 安全, 可回滚 } 之一
  且洞察结论含 { 必须重启, 有影响, 风险, 不可回滚 } 之一
  → contradicts（记录双方原句作为证据，不做更多推理）
```

**不做语义相似度、不做 LLM 判词。** 误判冲突会直接伤害"可信"这个卖点，宁可漏报（记为 `derived`）不可误报。语义判定列 Phase C，且必须带人工复核闸门。

### 4.4 什么情况下允许"猜测"
**从不。** 匹配不中就是 `operational`，渲染为「未绑定知识」。这条是硬约束，写进验收（A5）。

---

## 5. 绑上之后能做什么（这才是价值）

### 5.1 空间：垂直线程 + 三跳下钻
1. 点洞察（L2）→ 相机 `Trace` 机位，向下拉出它引用的 1–3 条知识（L1）；
2. 再点知识 → 沿线程下到它的 `evidenceRefs`（L0 证据条带高亮）；
3. `Esc` 逐层上浮。**任何一跳都能读出"这条结论的背书还差哪一环"**。

### 5.2 冲突即工单（不新建流程）
`contradicts` 的洞察在 HUD 产生一条「知识复核候选」。点击 → **进入现有 `KnowledgeCandidateReviewView`**（`/knowledge/candidates`），带上 `{ insightId, atomId, 双方原句 }` 作为上下文。
**不新建审批表、不新建状态机**——沿用项目已有的候选复核链路，这是成本最低且不破坏既有权限/审计的设计。

### 5.3 沉淀：洞察固化为知识
人工确认后，走两条路：
- **修正知识**：原子 `version + 1`，旧版本沿 `−Z` 后退并标 `STALE`，线程断开变虚（旧洞察仍指向旧版本，可见历史）；
- **固化洞察**：洞察从 L2 **下沉**到 L1 成为新知识候选（`type: 'FIELD INSIGHT'`，`source` 记录原接口与时间窗），线程由虚变实。

**这一步就是"经验沉淀"的可视化。** 空间里你能看见自己的洞察变成知识——这是任何列表视图给不了的反馈。

### 5.4 检索：双向可达
- 从知识条目侧栏「被引用的洞察」跳洞察；
- 从洞察「凭据」区跳知识条目（`Ctrl+↑/↓` 键盘等价）；
- 检索命中知识时，引用它的洞察一并高亮（复用现有 `hitIds` 机制，扩一个 `hitInsightIds`）。

---

## 6. 状态流转

```
                 ┌──────────── 洞察生成（带 binding + confidence）────────────┐
                 ▼                                                          │
        ┌────────────────┐   点洞察下钻    ┌──────────────┐                  │
        │ L2 INSIGHT     │ ──────────────► │ L1 KNOWLEDGE │                  │
        │ derived /      │                 │ 命中 1–3 原子 │                  │
        │ corroborates / │ ◄────────────── │              │                  │
        │ operational    │   线程 hover     └──────┬───────┘                  │
        └───────┬────────┘                         │                          │
                │ contradicts                      │ evidenceRefs             │
                ▼                                  ▼                          │
        ┌────────────────┐                 ┌──────────────┐                  │
        │ 知识复核候选    │                 │ L0 EVIDENCE  │                  │
        │ (既有 review)   │                 └──────────────┘                  │
        └───────┬────────┘                                                   │
                │ 人工确认                                                   │
        ┌───────┴────────────────┐                                           │
        ▼                        ▼                                           │
  修正知识（v+1，旧版后退）   固化洞察（L2→L1，type=FIELD INSIGHT）──────────┘
```

`Insight` 侧新增一个派生状态（不落库也能算）：`sunkToAtomId?: string`——一旦固化，洞察卡标 `SUNK`，不再重复参与匹配。

---

## 7. Phase 边界

| 阶段 | 范围 | 是否需要后端 |
|---|---|---|
| **Phase A（本次实施）** | 前端数据契约 + `bindingIndex.js` + 规则匹配 + 空间线程 + 「未绑定」真实渲染 + 冲突进既有复核入口 | 否。静态 `knowledgeCatalog` + 现有 4 个 intent 即可跑通 |
| **Phase B** | 知识原子 `evidenceRefs` 真实化：从 `knowledge/evidence/` 与 `knowledge/retrieval/` 反查 `chunk_id → 知识条目`；`insight_binding` 落表（如需要） | 是。新增只读接口 `GET /api/knowledge/{id}/evidence-refs`，不改既有写入协议 |
| **Phase C** | 语义级 `contradicts`、洞察自动生成（非规则 intent）、绑定权重学习 | 是。且必须带人工闸门 |

Phase A 的验收**不依赖任何后端改动**，这是刻意设计：让这个能力先能演示、再谈闭环。

---

## 8. 禁止项（实施者逐条自检）

1. ❌ 给 `operational` 洞察补知识连线以求画面完整。
2. ❌ 给没有 `evidenceRefs` 的知识原子渲染任何"证据已就绪"的形态。
3. ❌ `binding.explanation` 留空或写"智能匹配"这类无信息量文案。
4. ❌ 用 `Math.random` / 时间戳让布局或匹配看起来"更活"。
5. ❌ Phase A 引入语义相似度或 LLM 判 `contradicts`。
6. ❌ 为绑定新建第二套审批/权限/审计。

---

## 9. 验收

| 编号 | 判据 |
|---|---|
| B1 | `buildBindingIndex` 同输入同输出，`threads` 顺序稳定（`test/binding-index.test.mjs`） |
| B2 | 每条洞察的 `binding.mode` 与 `atoms.length` 自洽：`operational ⇔ atoms.length === 0` |
| B3 | 每条非 `operational` 洞察都有非空 `explanation` |
| B4 | 现有 4 个 intent 全部可运行，且至少各有 1 条正确落到 `operational` 或 `derived`（**当前真实预期：alerts / servers / health 为 `operational`，knowledge 类可命中**） |
| B5 | 空间中线与数据一致：`threads` 数量 === 渲染的线数量（browser test 断言） |
| B6 | `stats` 在 HUD 可见，且与索引计算值相等 |
| B7 | 无证据锚点的知识条目渲染「未绑定」而非「已关联」 |
