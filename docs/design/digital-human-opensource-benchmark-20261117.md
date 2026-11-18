# 数字人交互：大厂开源模型借鉴调研（2026-11-17）

> 范围：SmartOpsAgent 桌宠数字人（VRM + 浏览器实时交互）。
> 问题：现有交互能否借鉴大厂/社区开源模型？能借鉴哪些、怎么借、哪些不能碰。
> 结论先行：**能，但只能走实时 VRM 路线；端到端视频数字人不是同一个问题，接进来会毁掉实时性。**

---

## 1. 当前基线（代码事实，非推测）

| 能力 | 实现 | 位置 | 现状评价 |
| --- | --- | --- | --- |
| 形象 | VRM 1.0 模型，three.js + `@pixiv/three-vrm` | `useVrmModel.js` | 已对齐 VTuber 生态 |
| 口型 | 五元音 viseme（aa/ih/ou/ee/oh） | `useLipSync.js` | **audio 模式只有频段能量近似；text 模式按码位散列，不代表真实发音** |
| 语音合成 | edge-tts（ai-service） | `ai-service/app/services/tts.py` | 免费、无需 GPU，但默认只回音频、不回时间戳 |
| 表情/姿态 | 状态 → 表情权重 + 骨骼插值 | `personaStates.js` / `useVrmModel.js` | 有表情管线，但输入是系统状态而非"情绪识别" |
| 手势 | 程序化关节动画 | `personaGestures.js` | 手写，动作库有限 |
| 事件驱动 | `FAULT_DETECTED` → 气泡/手势/播报 | `personaFaultNotify.js` | 已完成（P1-3） |

**短板定位**：不是"画面不够真"，而是"口型没有音素依据、情绪没有识别输入、对话没有打断能力"。这三项都恰好有成熟开源方案，且都不需要 GPU 服务。

---

## 2. 两条路线必须分开判断

| 维度 | 路线一：VRM / 实时交互 | 路线二：端到端视频数字人 |
| --- | --- | --- |
| 代表 | ChatVRM、Open-LLM-VTuber、Audio2Face-3D | MuseTalk、EchoMimic、LivePortrait、HunyuanVideo-Avatar |
| 输出 | 浏览器实时渲染的 3D 骨骼/表情 | 预渲染视频流 / 帧序列 |
| 延迟 | 帧级（16–33ms） | 秒级到分钟级 |
| 硬件 | 客户端 GPU（已有） | 服务端 GPU（新增） |
| 可交互 | 是（可被打断、可指向、可挂件） | 否（只能播） |
| 与桌宠契合 | 同构 | 异构 |

**结论**：桌宠是运维场景的实时告警入口，"说错话可以立刻停"比"脸更真"重要。主线走路线一；路线二只用于离线宣传片/播报物料。

---

## 3. 路线一候选清单（可直接落地）

许可标注为「已核实」指本次检索到公开许可信息；标「需核实」指仓库 LICENSE 可能已变更，落地前必须再看一眼。

### 3.1 口型同步（最优先）

| 项目 | 能力 | 许可 | 接入成本 | 契合度 |
| --- | --- | --- | --- | --- |
| **NVIDIA Audio2Face-3D** | 音频 → ARKit 52 blendshape，可离线烘焙 | SDK（C++/Python）MIT；模型权重 NVIDIA Open Model License（已核实） | 中（需离线跑一次，产出曲线资源） | **高**：产物是时间序列，运行时零推理 |
| edge-tts WordBoundary | 词级时间戳 | edge-tts 为开源库（已在使用） | 低（改 ai-service 返回值） | **高**：现有 TTS 就能拿 |
| MuseTalk | 实时唇形（视频域） | MIT（已核实，但依赖 Whisper/VAE/DWPose 各自许可） | 高（需 GPU + 视频管线） | 低：改的是视频不是骨骼 |
| Wav2Lip | 唇形替换 | **仅个人/研究/非商用**（已核实） | 高 | **排除**：商用不可用 |
| SadTalker | 音频驱动说话头视频 | 代码 Apache-2.0，但预训练权重含非商用模型（已核实） | 高 | **排除**：权重许可不清 |

**关键判断**：真口型的前提是"音素/词级时间戳"，不是换更聪明的模型。当前 edge-tts 本来就能给出 WordBoundary 事件，只是 ai-service 没把它回传给前端——这是成本最低、收益最直接的一步。

### 3.2 表情与情绪

| 项目 | 可借鉴内容 | 许可 | 说明 |
| --- | --- | --- | --- |
| **Open-LLM-VTuber** | ASR→LLM→TTS→情绪→表情→VRM 的编排；桌面宠物模式；免耳机打断（回声消除） | 后端 v1.2.0 为 MIT；**前端与后续版本转为 Open-LLM-VTuber License 1.0（改版 Apache 2.0，含商用限制）**（已核实） | 只借鉴**架构思路**，不复制其前端代码；商用前必须读新版许可 |
| ChatVRM | VRM 加载顺序、相机取景、viseme 映射 | MIT | 已在借鉴 |
| silero-vad | 语音活动检测，支持 barge-in | MIT | 独立小模型，浏览器/服务端均可跑 |

### 3.3 动作

| 项目 | 可借鉴内容 | 说明 |
| --- | --- | --- |
| **VRMA（VRM Animation 1.0）** | 标准骨骼动作文件格式，跨模型复用 | 规范在 `vrm-c/vrm-specification`，UniVRM 参考实现开源；可把手写 `personaGestures.js` 逐步换成可替换动作资源 |

---

## 4. 路线二候选清单（仅离线物料）

| 项目 | 厂商 | 许可 | 适用场景 |
| --- | --- | --- | --- |
| MuseTalk | 社区 | MIT（已核实） | 实时唇形合成，可做播报视频 |
| EchoMimic / EchoMimicV2 | 蚂蚁集团 | Apache-2.0（已核实） | 半身数字人视频，宣传物料 |
| LivePortrait | 快手 KwaiVGI | MIT 类（已核实） | 静态照片驱动，宣传片 |
| LatentSync | 字节跳动 | Apache-2.0（已核实） | 唇形同步，替代 Wav2Lip |
| HunyuanVideo-Avatar | 腾讯 | 腾讯混元社区许可（**地域条款排除 EU/UK/KR**，已核实） | 高保真说话视频，需大显存 |
| EMO / VASA-1 | 阿里 / 微软 | **未开放权重**（论文级） | 仅作技术参考，不可落地 |
| Duix / HeyGem | 硅基智能 / 社区 | 需核实仓库 LICENSE | 端侧实时数字人，可评估 |

---

## 5. 推荐路线（分期，按投入产出排序）

### P0：让口型有依据（低成本，无新依赖）

1. ai-service 的 TTS 返回值增加 `timing[]`（edge-tts WordBoundary 的 `offset/duration`，单位 100ns 转 ms）。
2. 前端新增 `visemeTimeline(text, timing)` 纯逻辑模块：中文用 `pypinyin`-等价映射（前端可内置轻量声母/韵母→viseme 表，或由 ai-service 直接算好返回），英文按字母→音素粗映射。
3. `useLipSync` 增加 `timeline` 模式，优先于现有 text 散列模式；**保留旧模式作为降级**，并在 UI 如实标注当前是"音素对齐"还是"能量近似"。

验收：同一句话在 timeline 模式下，aa/oh 出现在元音位置；断网/无时间戳时自动回落到现状，不报错。

### P1：固定话术离线烘焙 blendshape（中成本）

针对高频固定播报（告警分级话术、巡检结论模板），用 Audio2Face-3D 离线烘出 ARKit blendshape 曲线，作为静态资源缓存。运行时只做曲线播放，零推理开销。
适用边界：**只对固定文本有效**，动态文本仍走 P0。

### P2：情绪与打断（体验提升）

- 借鉴 Open-LLM-VTuber 的 emotion → expression 映射，接到现有 `personaStates.js` 表情管线（只加映射层，不改渲染层）。
- silero-vad 做 barge-in：用户开口即压低/停止播报，与现有"播报中让路"守卫（`isBusy`）合并。

### P3：动作标准化（长期）

把手写手势逐步替换为 VRMA 动作资源，支持按场景（告警/恢复/巡检）切换动作集。

---

## 6. 明确不做

- 不用 Wav2Lip 做任何商用产出（许可不允许）。
- 不用 SadTalker 预训练权重做交付（权重含非商用模型）。
- 不把端到端视频模型接进桌宠主链路（延迟与可打断性不达标）。
- 不直接复制 Open-LLM-VTuber 前端代码（1.3 起许可变更，商用需单独授权）。
- 不引入 EMO / VASA-1（未开放权重）。

---

## 7. 风险与前置检查

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| edge-tts 属非官方接口封装，WordBoundary 行为可能随微软策略变动 | P0 依赖它的时间戳 | 时间戳缺失时静默降级到能量模式，不阻断播报 |
| Audio2Face-3D 权重为 NVIDIA Open Model License（非 MIT） | 商用需读条款 | 只用于离线烘焙，产物为曲线数据；上线前法务确认 |
| VRM 模型本身的 VRM Public License 1.0 对"人格形象"有约束 | 商用分发 | 与模型作者许可一并核对 |
| 开源项目许可随版本变化 | 长期维护 | 落地时锁定 commit + LICENSE 快照归档 |

---

## 8. 结论

1. **可以借鉴，且已经在借鉴**（ChatVRM）。
2. 最高价值的一步不是引入更大模型，而是**把 edge-tts 已有的词级时间戳接进 viseme 管线**——这一步零 GPU、零新服务、可降级。
3. Audio2Face-3D 是唯一同时满足"大厂出品 + 开源 + 与 VRM blendshape 体系可直接对接"的选项，定位是**离线烘焙固定话术**。
4. 端到端视频数字人（MuseTalk / EchoMimic / LivePortrait）留给宣传物料，不进产品主链路。

---

## 9. 带对齐能力的 TTS / 口型方案专项调研（2026-11-17）

### 9.1 判定口径

"带对齐能力"只算**合成时能直接给出时间戳**（词 / 字 / 音素）。把音频再送 ASR 或强制对齐器反推时间戳，属于"后对齐"，单列一类——它同样可用，但多一层延迟和识别错误，不能与原生对齐混为一谈。

### 9.2 对比表

| 方案 | 对齐粒度 | 运行位置 | 许可 / 成本 | 与当前栈契合度 | 关键风险 |
| --- | --- | --- | --- | --- | --- |
| **edge-tts WordBoundary** | 词级（中文粒度以服务端为准） | 云（免费接口） | 开源封装库（已在使用） | **已接完（P0）** | 非官方接口，行为可能变动 |
| **Azure Speech viseme** | **音素级 viseme ID + 100ns 音频偏移** | 云 | 按字符计费，需订阅 key | 高：返回结构与现有 `timing[]` 同构 | 国内区域可用性、key 与合规 |
| **Amazon Polly speech marks** | viseme / word / sentence | 云 | 按字符计费 | 中：需接 AWS SDK | viseme 支持范围按音色而定，中文需实测 |
| **阿里云百炼 CosyVoice** | 字级时间戳（`word_timestamp_enabled`，仅流式） | 云 | 按字符计费 | 中：WebSocket 流式，改造成本高于 HTTP | 仅部分音色支持；非开源版能力 |
| **piper-plus**（Piper 的 MIT 分支） | **音素级**（VITS duration predictor） | 本地 CPU/ONNX | MIT | 高：Python 包 + HTTP 服务，中文走 pypinyin | 需模型导出 `durations` 输出；zh 模型需实测 |
| **IndexTTS2** | 仅"总时长/token 数"控制，**不逐字** | 本地 GPU | Bilibili-IndexTTS 许可（需读条款） | 中：中文与情感更强，但对不齐口型 | 时长控制 ≠ 逐字时间戳；Python ≥3.10 |
| **CosyVoice2 开源版** | 未见公开时间戳输出接口 | 本地 GPU | Apache-2.0（代码） | 中：中文音色好 | 时间戳要做只能自己加对齐头或后对齐 |
| **F5-TTS** | **架构上无对齐/时长预测器** | 本地 GPU | MIT（代码） | 已在用（音色克隆） | 官方论文明确移除 phoneme alignment / duration predictor，不可能直接回传 |
| **FunASR Paraformer（后对齐）** | **中文字级时间戳**（原生） | 本地 GPU | MIT | 高：中文场景最省事 | TTS 音频再识别，错字/漏字会导致个别字对不上 |
| **WhisperX（后对齐）** | 词级（zh 走 wav2vec2 中文模型） | 本地 GPU | BSD-2（代码） | 中：需装 whisper + 对齐模型 | 模型下载体积大；中文分词粒度偏词 |
| **MFA 普通话（后对齐）** | **音素（声母/韵母）级** | 本地 CPU，独立环境 | MIT | 中：离线批量最准 | 安装重（conda），单句推理秒级，不适合实时逐句 |
| **Rhubarb Lip Sync** | 嘴型 A–H（音频驱动） | 本地 CPU | 开源（需核实当前 LICENSE） | 低：默认识别器只认英语 | 非英语只能用 phonetic recognizer，中文准确度未验证 |

### 9.3 三条可落地路线

**路线 A（推荐，增量最小）：原生对齐**
- 保留 Edge 作为主音色，`timing[]` 已上线（词级）。
- 增加 **piper-plus 作为"音素级"可选 Provider**：中文用 pypinyin 取声韵母，VITS 的 duration predictor 直接给每个音素的 `start_ms/end_ms`，映射到 aa/ih/ou/ee/oh 五元音。CPU 可实时，MIT 许可干净。
- 前端 `visemeTimeline` 无需改动：把 `phoneme → 时间` 折算成"词/字 → 时间"即可复用。

**路线 B（保音色）：后对齐**
- 继续用 F5-TTS / VoxCPM2 做音色克隆，合成后把音频交给 **FunASR Paraformer** 取字级时间戳，再按拼音映射 viseme。
- 代价：每句多一次 ASR 推理；识别错字时该字口型按前后插值，UI 标注"字级（ASR 对齐）"。
- 只用于短句（桌宠回复通常在 60 字内），长文本仍走路线 A。

**路线 C（云，效果上限最高）**
- Azure viseme 直接给音素级 viseme ID 与 100ns 偏移，映射到 VRM 五元音后就是"真口型"。
- 但引入订阅、key 管理、跨境网络与合规评估，且与"本地优先、可离线"的现有架构冲突。建议只作为对外演示的旁路，不进主链路。

### 9.4 与当前环境的兼容性检查（必须先验）

| 依赖 | 约束 | 结论 |
| --- | --- | --- |
| piper-plus | Python ≥3.11；ONNX Runtime 需有 cp314 wheel | **已实测通过**：Python 3.14.3 + onnxruntime 1.32.0（cp314）安装与推理正常 |
| piper-plus 中文 timing | 仅当模型导出 `durations` 输出（`has_duration_output`） | **已实测**：tsukuyomi 6 语种模型 `has_duration_output=True`；上游 `zh_CN-huayan-medium` 无法加载 |
| IndexTTS2 | Python ≥3.10，GPU 推理 | 与现有 torch 2.14 / Python 3.14 组合需实测；许可为厂商自定义 |
| FunASR | 依赖 torch / torchaudio | 与 Python 3.14 的 wheel 兼容性需实测 |
| MFA | 独立 conda 环境，不依赖项目 Python | Windows 可用，最稳，但只能离线批处理 |
| Azure / Polly / 百炼 | 需要网络与密钥 | 与"离线可降级"原则冲突，需产品决策 |

### 9.5 诚实降级原则（沿用 P0 口径）

1. 没有时间戳 → 静默回落到现有近似模式，不阻断播报。
2. 后对齐失败或置信度低 → 回落到"按音频时长反推 cps"，不假装对齐。
3. UI 标注必须区分三档：**音素级（原生）> 字/词级（原生或 ASR）> 近似同步**，不能把后两档说成音素级。

### 9.6 建议顺序

1. **先做 piper-plus 可行性验证**（已完成，见 9.7）：结论是"可用，但只能用 piper-plus 自家的 multilingual 模型"。
2. 可行则加为可选 Provider（不做默认），Edge 继续兜底。
3. 音色克隆需求强时，再评估 FunASR 后对齐（路线 B）。
4. Azure viseme 只在明确接受云依赖时评估（路线 C）。

### 9.7 实测结果（2026-11-17，本机 Windows / Python 3.14.3 / CPU）

环境：临时 venv（`%TEMP%\piper-check`），`pip install "piper-plus[cpu]==2.0.2"`，装上 onnxruntime 1.32.0（cp314 wheel 存在）。

| 检查项 | 结果 |
| --- | --- |
| 上游中文模型 `zh_CN-huayan-medium` | **加载失败**：其 config 为 `phoneme_type: espeak`，piper-plus 2.0.2 的 `PhonemeType` 只有 `openjtalk / bilingual / multilingual`，直接 `ValueError` |
| piper-plus 多语种模型 `tsukuyomi-chan-6lang-fp16` | 加载成功（38MB fp16），`has_duration_output=True` |
| 时间戳粒度 | 音素级 IPA（含 `tone1–4` 音调 token），`total_duration_ms` 与音频时长误差 <5ms |
| 音节切分 | 以 `toneN` token 结尾即可切出一个音节；三句测试中音节数 = 汉字数（混入拉丁字符 `A` 时 +1） |
| CPU 性能 | 模型加载 0.32s；首句 RTF 0.106–0.352；热态 RTF **0.027**（2.09s 音频用 0.06s 合成） |
| 五元音映射覆盖率 | 按"韵母最长匹配"（`aʊ/ueɪ/iɛn/uaɪ/uo/ou/iŋ/...`）三句共 36 音节，**未映射 0、无口型音节 0**；`你好我是智维助手` → `ih/aa/oh/ih/ih/ee/ou/oh`，与听感一致 |
| 音色 | 单说话人日语少女音色；中文清晰度需人工试听（样例 wav 在临时目录，未入仓） |

**关键结论**：piper-plus 的中文能力来自自家 multilingual 模型，**不是**上游 Piper 的 `zh_CN-huayan` 系列；落地时必须把"模型来源"锁到 piper-plus 的 release，不能混用 rhasspy/piper-voices。

**尚未验证**：中文听感主观质量、长句（>100 字）稳定性、zero-shot 音色克隆（`zs-v1` bundle 有中文，但需要参考音频 embedding）。

### 9.8 接入结果（2026-11-17）

已按路线 A 把 piper-plus 接成**可选** Provider（不抢占默认音色，`TTS_PROVIDER=piperplus` 显式启用）：

- 后端 `PiperPlusProvider`（`name="piperplus"`）：探测 `piper_plus` 模块 + 模型/config 文件；`synthesize_with_timing` 把以 `toneN` 收尾的音素组切成音节，折算成前端契约 `{text, offset_ms, duration_ms, viseme}`，`length_scale = 1/speed`。
- 对齐策略（2026-11-17 补充）：**中文逐字 + 字母数字串整体**。汉字/假名各占一个音节，拿到逐字起止与真实韵母；`A-07` / `Kubernetes` 这类串音节数不固定，整串共用一个时间段、串内由前端均分，UI 额外注明「字母数字为整串近似」；没有汉字锚点、音节数少于汉字数、或无法判定哪串被发音时回空降级。
- 实测混合文本：`服务器 A-07 的处理器温度…` → 27 条（含 `A-07` 360ms）；`请注意，Kubernetes 集群的 Pod 重启次数异常。` → 14 条（`Kubernetes` 801ms、`Pod` 255ms），此前这两种句子会整句降级。
- **数字规范化（重要，已修）**：模型 phonemizer 会丢弃 ASCII 数字（日志 `Missing phoneme from id map: 0/7`），实测 `温度07度` 原本只读「温度度」。现在 Provider 在合成前改写：独立数字按数量读（`92`→九十二、`0.35`→零点三五、`1001`→一千零一），千分位整段读（`1,024`→一千零二十四），日期按年月日读（`2026-11-17`→二零二六年十一月十七日，月/日越界不硬套），时刻按时分读（`10:30`→十点三十分、`10:00`→十点整、`10:30:45`→十点三十分四十五秒，时分秒越界与端口/比例 `1:100` 不按时刻处理），货币按符号读单位词（`¥5`→五元；人民币按元/角/分 `¥5.50`→五元五角、`¥5.05`→五元零五分、`¥0.50`→五角；其余币种按主币+辅币 `$12.50`→十二美元五十美分、`£5.50`→五英镑五十便士、`€0.50`→五十欧分；韩元无辅币仍按点读），单位按中文读（`5kg`→五公斤、`120MB`→一百二十兆字节、`5GB/s`→五吉字节每秒、`220V`→二百二十伏、`-5℃`→负五摄氏度、`5min`→五分钟、`5px`→五像素、`60fps`→六十帧每秒、`2000rps`→两千请求每秒、`5000mAh`→五千毫安时、`2.5kWh`→二点五千瓦时、`4.7kΩ`→四点七千欧、`45°`→四十五度；单位识别要求数字左侧不在型号串里、单位右侧不再是字母数字，避免 `A-07s`、`5kgf` 误判），倒装单位改中文前置语序（`300dpi`→每英寸三百点、`500QPS`→每秒五百次查询、`5000万QPS`→每秒五千万次查询（`5000 万 QPS` 这类带空格的写法同样识别；单位在前的 `QPS 5000万`、`QPS：5000万`、`QPS高达5000万`、`QPS（5000万）`、`QPS 已达 5000 万` 会先调换语序再统一读（冒号与括号注释一并丢弃；`每秒查询数（QPS）5000万` 删掉括号里的缩写）。注意规范化只作用于 piper-plus：`TTS_PROVIDER=f5tts` 合成失败时，后端会按 `_AUTO_ORDER` 自动换到下一个可用 Provider（响应头 `X-TTS-Fallback-From` 如实标注来源；2026-11-18 起 f5tts 首选失败即由 piper-plus 兜底，不再 502）；只有全部 Provider 都失败才回落浏览器 `speechSynthesis`，此时前端 `normalizeSpeechText` 先把 QPS/IOPS/dpi/fps/mAh/Wh/GB每秒 等会被逐字母念出的缩写换成中文读法、并去掉 markdown 标记与裸链接再朗读（2026-11-17 实测的 UI 念英文 QPS，即 `TTS_PROVIDER=f5tts` 合成 502 后浏览器兜底念原文所致）；全角 `５０００万ＱＰＳ` 先转半角）、`1200IOPS`→每秒一千二百次读写，`img300dpis` 这类仍按原样逐位读；前置的「每秒/每英寸」没有原文对应位置，口型落在数字串上属近似），口语数量词（千位及以上的 2 读「两」：`2000`→两千、`20000`→两万，`200`→二百、`20`→二十不变），前导零与多段编号按位读（`07`→零七、`192.168.1.1`→一九二点一六八点一点一），字母数字串内逐位读（`A-07`→A-零七），`98%`→百分之九十八，前导负号读「负」。时间戳仍按原文对齐，多出的音节由数字串吸收。
  仍未覆盖：单位是白名单，未收录的单位仍按字母读（字母本身会被念出，不是漏念）。
- 配置：`TTS_PIPER_MODEL` / `TTS_PIPER_CONFIG`（.env.example 已补），安装 `pip install "piper-plus[cpu]==2.0.2"`；`_AUTO_ORDER` 末尾追加。
- 前端：`visemeTimeline` 优先采用条目里的 `viseme`；桌宠把口型来源分三档标注——`phoneme`（音素级）/ `timeline`（词级）/ `text`（近似），含字母数字串时降档说明。
- F5-TTS 依赖修复（2026-11-18）：torchaudio 2.9+ 的 `load()` 走 torchcodec，需要 FFmpeg **共享库**（`avcodec-*.dll` 等）；官方 ffmpeg full_build 只有静态 exe，读参考音频会报 `Could not load libtorchcodec_coreN.dll`。新增 `TTS_FFMPEG_SHARED_DIR` 指向 full_shared 构建的 `bin`，Provider 在导入 `f5_tts` 之前用 `os.add_dll_directory` + PATH 前置注册（目录无效时按配置错误如实报错）。实测 `TTS_PROVIDER=f5tts`：`QPS 峰值 5000 万，请关注` 合成 200，24kHz 单声道 1.99s，响应头 `x-tts-provider: f5tts`。
- 实机抽测（本机 CPU，22050Hz，tsukuyomi-6lang）：热态 RTF 0.04–0.05（含 HTTP 往返）；`设备温度过高，请立即检查冷却系统。` 15 字 → 15 条音节时间戳。
- 仍未验证：中文主观听感、长句稳定性、zero-shot 音色克隆。

---

## 参考来源

- [Open LLM Vtuber 文档 · 1.2.0 Release（许可变更说明）](https://docs.llmvtuber.com/en/blog/v1.2.0-release/)
- [Open LLM Vtuber Quick Start（Ollama + sherpa-onnx + edge_tts）](https://open-llm-vtuber.github.io/en/docs/quick-start/)
- [NVIDIA ACE for Games · Audio2Face-3D SDK（SDK MIT）](https://developer.nvidia.com/ace-for-games)
- [NVIDIA NGC · Audio2Face-3D（模型许可）](https://catalog.ngc.nvidia.com/orgs/nim/nvidia/containers/audio2face-3d/-)
- [Audio2Face-3D 论文（网络/SDK/训练框架开源）](https://arxiv.org/pdf/2508.16401)
- [Wav2Lip（仅非商用）](https://github.com/Rudrabha/Wav2Lip)
- [SadTalker 许可说明（权重含非商用模型）](https://sadtalker.ai/sadtalker-github)
- [MuseTalk（MIT）](https://musetalkai.com/)
- [LivePortrait（MIT 类）](https://gaga.art/blog/liveportrait/)
- [EchoMimicV2（Apache-2.0，蚂蚁集团）](https://aihub.caict.ac.cn/codes/AntGroup/echomimic_v2)
- [HunyuanVideo 许可（腾讯混元社区许可，地域条款）](https://hivebook.wiki/wiki/hunyuan-video-tencent-s-13b-open-weight-video-diffusion-model)
- [VRM Animation 规范](https://vrm.dev/en/vrma/)
- [Azure · Get facial position with viseme（音素级 viseme + 100ns 偏移）](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis-viseme)
- [Azure · 语音音素集（zh-CN 的 IPA/SAPI 与 viseme 映射）](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-ssml-phonetic-sets)
- [Amazon Polly · Speech marks（sentence/word/viseme/SSML）](https://docs.aws.amazon.com/polly/latest/dg/speechmarks.html)
- [Amazon Polly · SynthesizeSpeech（SpeechMarkTypes）](https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html)
- [阿里云 · CosyVoice 字级时间戳（word_timestamp_enabled）](https://help.aliyun.com/zh/model-studio/cosyvoice-client-events)
- [piper-plus（VITS duration predictor 音素级 timing，MIT）](https://pypi.org/project/piper-plus/)
- [F5-TTS 论文（明确不使用 phoneme alignment / duration predictor）](https://arxiv.org/html/2410.06885v1)
- [IndexTTS2 论文（token 数时长控制）](https://arxiv.org/html/2506.21619)
- [FunASR · 中文字级时间戳](https://www.funasr.com/en/blog/speech-to-text-timestamps-python.html)
- [WhisperX（zh 走 wav2vec2 中文对齐模型）](https://pypi.org/project/whisperx/)
- [Montreal Forced Aligner · Mandarin 示例](https://montreal-forced-aligner.readthedocs.io/en/latest/first_steps/alignment_example.html)
- [Rhubarb Lip Sync（默认识别器仅英语，另有 phonetic 识别器）](https://www.npmjs.com/package/rhubarb-lip-sync)
