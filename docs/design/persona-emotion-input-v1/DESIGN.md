# 数字人「情绪识别输入」方案 v1（P2-8 收口）

> **缺口出处**：`docs/design/llm-distill-stack/ARCHITECTURE.md` §1.2「数字人三短板：音素口型、情绪识别输入、打断能力」（缺口清单 **P2-8**）。
> **现状复核（2026-11-22，读代码确认，非推测）**：
> - 音型口型 ✅ 已落地：`useLipSync.js`（534 行）+ `chineseViseme.js`（97 行），`phoneme / timeline / text` 三档精度，UI 如实标注档位。
> - 打断 ✅ 已落地：`PersonaPet.vue` 豆包式 barge-in（播报/思考中点击或语音打断，`interruptPlayback()` + `voiceMode` 切换），提示文案已上线。
> - **仅剩「情绪识别输入」**：`personaStates.js` 的 `expressions` 由**系统状态**决定（`PERSONA_STATE_PROFILES[state].expressions`），**没有任何来自用户输入的情绪识别**（全仓检索 `emotion/sentiment` 仅命中手势动画名与知识库课件）。
>
> 本文件是该需求的**唯一口径**。状态取值沿用 `docs/competition/fact-sheet.md`：数字必须带 n 与状态；`NOT_RUN` 不得写成达标。

---

## 0. 结论先行

加**一层**情绪识别输入，不改渲染层：

```
用户文本（ASR 转写 / 文本输入）
   → POST /api/nn/emotion  →  {label, confidence, engine, status}
   → 前端 withEmotion(profile, emotion)   ← 纯函数，叠加到状态 profile 的 expressions
   → useVrmModel.setState(profile)        ← 渲染层零改动
```

- **推荐选型**：本地轻量中文情绪模型（主）+ 规则词典（兜底）+ 不可用时如实降级；**不伪造情绪**。
- **投入**：1 个后端模块 + 1 个端点 + 1 个前端纯函数 + 单测，本机可闭环，无需 GPU。
- **不做**：语音情绪识别（需专门模型，重）、端到端视频数字人（延迟与可打断性不达标，见调研文档 §6）。

---

## 1. 现状（代码事实）

| 能力 | 实现 | 位置 | 状态 |
|---|---|---|---|
| 表情管线 | 状态 → `expressions` 权重 | `personaStates.js` `PERSONA_STATE_PROFILES` | ✅ 有，**输入是系统状态** |
| 表情渲染消费 | `activeProfile?.expressions` | `useVrmModel.js:539`、`setState()`（:755） | ✅ 有，**不改** |
| 口型 | 三档 viseme | `useLipSync.js` / `chineseViseme.js` | ✅ 已落地 |
| 打断 | barge-in | `PersonaPet.vue`（`interruptPlayback` / `voiceMode`） | ✅ 已落地 |
| 情绪识别输入 | — | — | ❌ **缺**（本方案） |
| 语音链路 | ASR/TTS 栈已就绪（DTW 命令词 + faster-whisper 可选；edge-tts/piper-plus） | `agent/asr/`、`ai-service/app/services/tts.py` | ✅ 文本可复用 |

**表情枚举**（渲染层实际支持）：`relaxed / happy / sad / angry / surprised`（见 `personaStates.js` 与 `personaGestures.js` 的 `expressionTrack`）。

---

## 2. 目标 / 非目标

**目标**
1. 用户文本（含 ASR 转写）→ 情绪标签 + 置信度，端点可调用、可降级、不伪造。
2. 情绪 → `expressions` 权重的**纯函数映射**，叠加在状态 profile 之上（状态仍主导；情绪只做**加成**，不覆盖状态语义）。
3. 低置信度 / 引擎不可用 → **不叠加**，并如实标注来源档位。

**非目标**
- 不做语音情绪识别（需 wav2vec2 类模型，超出本项范围；列为后续 P3）。
- 不改 VRM 渲染层、不改状态机七枚举。
- 不把「情绪识别」写成「情感计算已完成」——只覆盖**文本输入**。

---

## 3. 选型对比（三条路径）

| 路径 | 依赖 | 单次延迟（CPU） | 能力 | 结论 |
|---|---|---|---|---|
| **A. 本地轻量中文情绪模型** | `torch`+`transformers`（本机 py-3.14 已装）；权重经 `hf-mirror.com` / ModelScope 下载 | 数十~数百 ms | 中文情感/情绪分类 | **主路径** |
| **B. 规则词典** | `jieba`（已装）+ 自建情感词表 | < 5ms | 粗粒度（正/负/怒/惊） | **兜底**（模型缺失时） |
| C. 本地 LLM 分类 | Ollama 服务 + 真实模型 | 秒级（实测 qwen3:1.7b 约 5.4s/次） | 细粒度、可解释 | 不作主路径（延迟不适合交互） |

**环境事实（2026-11-22 实测）**
- `py -3.14`：`torch 2.14.1+cu126` / `transformers 5.18.0` / `jieba 0.42.1` / `pypinyin 0.55.0` / `scipy` / `onnxruntime`；默认 `py -3.13` **无**这些包。
- `huggingface.co` 直连不通（000）；**`hf-mirror.com` 200 可达**、`www.modelscope.cn` 302 可达 → 权重可下。
- 本机 HF 缓存仅 `faster-whisper-{base,medium,small}`，**无情绪模型**。

**候选模型（许可证必须按 `design-system/MASTER.md` 逐条核验后才可进主干）**
- `IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment`（110M，中文情感，二分类为主）
- 多分类候选：`uer/roberta-base-finetuned-*` 系列（需核验中文情绪维度与许可）
- 选型判据：**中文、CPU 可跑、许可证干净（MIT/Apache-2.0）、有官方情绪维度**；核验前一律记「未核验」，不得默认可用。

---

## 4. 链路设计

### 4.1 后端（`ai-service/app/emotion/`）

- `engine.py`：`EmotionEngine` 抽象 + `TransformersEmotionEngine`（懒加载单例，缺依赖自动降级）+ `LexiconEmotionEngine`（jieba + 词表）。
- `service.py`：`recognize(text)` → `EmotionResult{label, confidence, scores, engine, status, warnings, elapsed_ms}`；`get_emotion_info()`。
- `status ∈ {SUCCEEDED, EMPTY, UNAVAILABLE}`；`confidence` 未知时返回 `None`（**不写 0**）。
- 纯函数：`normalize_label`、`LEXICON`、`label_from_scores`。

### 4.2 端点（`ai-service/app/api/emotion.py`，注册到 `/nn`）

- `GET /api/nn/emotion-info` → `{available, engine, labels, model, license_status}`。
- `POST /api/nn/emotion`，请求 `{text, max_text}`，响应 `{available, ok, reason, engine, status, label, confidence, scores, warnings, elapsed_ms}`。
- 空文本 → `EMPTY`；模型与词典均不可用 → `available=false` + 原因（**不 500**）。
- `status` 逐字回传引擎状态（`SUCCEEDED`/`EMPTY`/`UNAVAILABLE`），供前端判断是否叠加。

### 4.3 前端

- `frontend/src/components/persona/emotionInput.js`（纯函数，可被 `node:test` 直测）：
  - `EMOTION_TO_EXPRESSION`：情绪 → `expressions` 权重（**只使用渲染层已有枚举**）。
  - `withEmotion(profile, emotion, {min_confidence, state})`：返回**新 profile**，把情绪权重与状态权重按 `max` 合并（状态主导，情绪加成）；`label` 未知 / `confidence < min_confidence` / `status != SUCCEEDED` / `available === false` → **原样返回原对象**。
  - **状态护栏**：`state ∈ {warning, error}` 时一律不叠加（否则「用户说开心，告警中的小鱼就变高兴」会破坏状态语义）。
  - `emotionSourceLabel` / `emotionLabelText`：来源档位与标签的中文标注。
- `frontend/src/api/emotion.ts`：调端点，**按项目约定先拆统一包装 `{code,message,data}`**；失败静默降级返回 `null`。
- 接线点：`AgentPersona.vue` 新增可选 `emotion` prop，内部 `stageProfile = withEmotion(personaProfile(state), emotion, {state})`，三处 `setState` 与状态/情绪两个 `watch` 统一走它；状态行如实显示「情绪：<标签>（<来源档位>）」。`AgentPersonaView.vue`（文本提问）与 `PersonaPet.vue`（ASR 转写）分别接线；浮窗另暴露 `applyEmotion(text)` 命令式入口。

**落地实测（2026-11-22）**
- 后端 `app/tests/test_emotion.py` **24 passed**；前端纯函数 `test/persona-emotion-input.test.mjs` **20 passed**。
- 浏览器实测 `test/persona-emotion-input.browser.mjs`（夹具端点）：词典兜底 / 本地模型 / 低置信不叠加 / 引擎不可用降级 **4 项通过**。
- 受控集评测 **n=25 逐句命中 14/25 = 0.5600**，平均置信度 0.8519；分类 happy 5/5、sad 5/5、angry 2/5、surprised 2/5、neutral 0/5（**维度错配导致的已知失败**）。产物 `reports/emotion-eval-20261122.json`。

**映射表（草案，可调）**

| 情绪标签 | expressions 权重 |
|---|---|
| happy | `{ happy: 0.6, relaxed: 0.2 }` |
| sad | `{ sad: 0.55, relaxed: 0.15 }` |
| angry | `{ angry: 0.6 }` |
| surprised | `{ surprised: 0.6 }` |
| neutral | `{ relaxed: 0.2 }` |

---

## 5. 验收门禁

| 编号 | 判据 |
|---|---|
| E1 | `withEmotion` 纯函数单测：映射正确、未知标签不叠加、低置信度不叠加、`max` 合并不覆盖状态高权重 |
| E2 | 后端契约：桩引擎、`EMPTY`/`UNAVAILABLE` 降级、空文本、`available=false` 不 500 |
| E3 | 端到端：一句话 → 端点 → 前端 profile（浏览器实测表情变化） |
| E4 | **真实评测**：自建 n≥20 条中文句子（喜/怒/哀/惊/中性 各 ≥4），报**准确率 + 平均置信度 + 引擎**；产物落 `reports/emotion-eval-<tag>.json`（`reports/` 不入库） |
| E5 | 口径登记：`fact-sheet` 新增条目 + 口径约束，**必须写明**「受控文本集，非真实语音；准确率口径为逐句标签命中」 |

**禁止事项**
1. 禁止把受控文本集准确率写成「情绪识别准确率 X%」（那是已知标签集，只证明链路）。
2. 禁止用 VLM/LLM 描述冒充情绪模型结果（引擎不可用一律 `available=false` + 原因）。
3. 禁止让情绪权重**覆盖**状态语义（告警/故障时不得因用户「开心」而变高兴）。
4. 禁止在无许可证核验的情况下把候选模型写进主干。

---

## 6. 工作包（可交接实现）

| 包 | 内容 | 产出 |
|---|---|---|
| T1 | 后端 `app/emotion/`（引擎抽象 + transformers 引擎 + 词典兜底 + 纯函数） | 模块 + 单测 |
| T2 | 端点 `/api/nn/emotion`、`/api/nn/emotion-info` + router 注册 | API + 契约测试 |
| T3 | 前端 `emotionInput.js` + `api/emotion.ts` + 接线 | 纯函数单测 + 浏览器实测 |
| T4 | 受控集评测 + 口径登记 + fact-sheet | 报告 + 登记 |

---

## 7. 风险与待核验

1. ~~**模型许可证**~~ **已核验（2026-11-22）**：`cardData.license = apache-2.0`，本地 `README.md` front matter 一致 → 允许使用；报告 `reports/open-source-license-verification-2026-11-22-emotion-model.md`。训练数据合规性与 base 模型许可传递链未核验。
2. **权重下载**：已成功下载（409MB，`models/emotion/erlangshen-sentiment/`，`models/` 已 gitignore）；失败时退回词典路径（功能降级，不伪造）。
3. **延迟**：实测首次加载约 0.4s，单次识别 `elapsed_ms` p50/max 见评测报告；交互路径可接受，未做异步化改造。
4. **维度错配（实测确认）**：`id2label={0:Negative,1:Positive}` 是**情感极性二分类**，渲染层需要 5 类；受控集 n=25 中 neutral **0/5**、angry/surprised 各 2/5。当前用词典补 angry/surprised 维度；**neutral 不可由该模型输出**，不得写成「五类情绪识别」。
5. **语音情绪未做**：本方案只覆盖文本，不得对外说「支持情绪识别」而不限定输入形态。

---

## 8. 与既有文档的关系

- 上游缺口：`docs/design/llm-distill-stack/ARCHITECTURE.md` §1.2（P2-8）。
- 调研依据：`docs/design/digital-human-opensource-benchmark-20261117.md`（§1 短板定位、§3.2 情绪、§5 P2 分期、§6 明确不做）。
- 口径纪律：`docs/competition/fact-sheet.md`（数字带 n 与状态）。
- 同项目其他设计：`docs/design/agent-avatar-3d-v1/`、`docs/design/xiaoyu-avatar-v1/`（本方案只加输入层，不改其渲染/资产）。
