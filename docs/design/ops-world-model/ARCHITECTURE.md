# 运维世界模型（Ops World Model）设计方案 v1

日期：2026-11-15
状态：设计定稿 / 待实施（计划见 `.trae/documents/运维世界模型-WM-01至WM-08实施计划.md`）
目标：把「深度视觉 + 预测下一状况 + 自主自学习」做进智维 Agent，迁移范式来自 NBA 深度视觉黑客松那套 CV Agent。

---

## 0. 来源与证据

| 档位 | 内容 |
|---|---|
| **observed** | 你给的三个仓库：`CharlesLiuZC/NBA-AWS-CV-Agent`、`unknowfish-azy/NBAcv-py-tools`、`unknowfish-azy/NBA-ASSIST`。 |
| **observed** | **这三个仓库的源码我没读到。** 本机 TLS 通道彻底不可用：PowerShell 报 `The SSL connection could not be established / Authentication failed`；curl 报 `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)`——拿不到凭据句柄，与客户端无关。浏览器 provider 连续报 `execution_failure`。 |
| **observed** | 检索通道能拿到同域项目，可作为范式参照：[aiden-guan/courtvision](https://github.com/aiden-guan/courtvision)（实时篮球 CV + 决策层 + 有据可依的 AI 解说 + 操作台）、[RidwanHaque/AI-ML-CV-NBA-Basketball-Analytics-System-Interface](https://github.com/RidwanHaque/AI-ML-CV-NBA-Basketball-Analytics-System-Interface)（YOLO 检测 + 多目标跟踪 + 零样本队别分类 + 场地关键点 + 战术俯视图 + 真实米制指标）、[aws-samples/sample-media-video-agent-amazon-bedrock-agentcore](https://github.com/aws-samples/sample-media-video-agent-amazon-bedrock-agentcore)（AWS 官方视频 Agent 样例）、`PanoEvJ/NBA_Assist`（HuggingFace Space，疑似与 NBA-ASSIST 同源）。 |
| **inferred** | `NBA-AWS-CV-Agent` 的 "AWS" 大概指 Bedrock / AgentCore 那条链；`NBA-ASSIST` 是"助手/解说"层；`NBAcv-py-tools` 是 CV 工具库。**这是我的推断，未证实。** |
| **unknown** | 三个仓库的具体实现、模型选择、prompt 结构。 |

**因此本文是"范式迁移设计"，不是"代码复刻方案"。** 要逐文件改写，得你把仓库的 README + 关键文件贴进来（或修好 TLS），我按 §2 的映射表给逐条 diff。

> 关于「开源的元宝」：我按 **"开源的原版/上游项目"** 理解——即那三个仓库各自的上游依赖与同域开源实现。如果你指的是腾讯元宝那个产品，说一声我换方向。

---

## 1. 诊断：你缺的不是"更深的视觉"，是"时间轴"

这是本方案最重要的一句话，先给证据。

**实测你现有视觉栈（读码确认）：**

| 文件 | 实际做什么 |
|---|---|
| `ai-service/app/vision/classes.py` | 三套类别预设：`patrol_anomaly`（person_intrusion / obstacle / fire_or_smoke / missing_extinguisher / fallen_equipment / liquid_leak）、`datacenter_equipment`（server / rack / status_led_abnormal / cable / gauge / door_state）、`coco_subset` |
| `app/vision/grounding.py` | GroundingDINO 式弱标注出框（离线） |
| `app/vision/screening.py`、`weak_label.py` | 离线筛帧与打标 |
| `scripts/{accumulate,export,weak_label,train}_vision*.py` | 攒帧 → 导出数据集 → 打标 → 训 YOLO |
| `ai-service/weights/yolo26n.pt`（实测路径） | 单帧检测权重；另有一份 `ai-service/yolov8n.pt` 在 ai-service 根目录 |

**全仓检索 `bytetrack|deepsort|kalman|reid`：零命中。**

也就是说：你现在有**单帧检测**，没有**帧间身份延续**，没有**事件层**，没有**下一状态**。

再看那个被当成"世界模型"的东西：
`app/training/simulator.py` 里是 `class FaultShape` + `def synthesize_series()` + `def generate_scenario_set()`——**这是一个合成指标曲线的数据生成器，不是动力学模型**。它不会"预测下一个状态"，它负责"造出像样的假数据来训异常检测器"。

**结论**：NBA 那套 CV Agent 的价值 100% 在时间轴上（跟踪 → 事件 → 预测下一回合 → 解说）。你现在的东西是"一帧一帧地看"，缺的正是那一整条时间轴。**把时间轴补上，才是那种深度。**

---

## 2. 范式迁移映射（NBA → 运维）

这是复刻的核心。逐行对照：

| NBA 黑客松组件 | 你要的运维等价物 | 你现有的落点 | 缺什么 |
|---|---|---|---|
| 视频帧 | 监控墙 / 仪表盘 / 终端 的截屏序列 | `vision/*`（截图能力有，桌面手上一轮已设计） | **帧带时间戳的会话**（运行时，不是离线攒帧） |
| YOLO 检测球员/球/篮筐 | 检测曲线、告警块、状态灯、错误弹窗 | `yolo26n.pt` + `screening.py` | 类别要扩到 UI 元素（`status_led_abnormal` 已有雏形） |
| **多目标跟踪（ByteTrack）→ 轨迹** | **指标/服务的状态轨迹（同一对象跨帧认得出）** | **无** | **★ 全新增，这是第一块** |
| 场地关键点 → 战术俯视图 | 拓扑图 → 态势俯视图 | `fault_propagation.py`、前端 3D 拓扑 | 视觉到拓扑的映射 |
| **事件识别（传球/投篮/失误）** | **运维事件（重启/扩容/切流/回滚/自愈）** | **无** | **★ 全新增，这是第二块** |
| **下一事件预测（球权转移）** | **下一状态预测（故障扩散 / 自愈 / 恶化）** | `simulator.py` 只造数据 | **★ 全新增，这是第三块** |
| grounded 解说 | 运维解说（"这次异常表现为阶梯突升，符合缓存雪崩特征"） | `temporal_narrator.py` ✅ 已有 | 接上预测结果 |
| 新比赛弱标注 → 越用越准 | 持续学习（预测误差驱动采样） | `continual_learner.py` ✅ 已有 | 接上视觉/世界模型的训练回路 |

**六格里你已经有四格的半成品，缺的是中间那三块带 ★ 的。**

### 2.5 三种视觉输入的可行性矩阵（决定 WM-02/03 走哪个分支）

这条原本是个待你回答的问题，现在**做成可配置分支**，选哪个都不用返工：

| | ① 监控墙截图 | ② 终端录屏 | ③ 巡检视频 |
|---|---|---|---|
| 元素身份稳定性 | **高**（面板/卡片位置固定） | **低**（文本行滚动，没有稳定身份） | 中（视角晃动、遮挡） |
| 跟踪是否适用 | ✅ ByteTrack 直接可用 | ❌ **不该用**——文本行做 IoU 关联必然抖成碎片 | ✅ 需配视角补偿/对齐 |
| 事件来源 | 状态灯变色、数值块抖动、红色块出现 | **新错误行出现 / 错误码首次出现 / 堆栈重复计数** | 人/物进出、设备状态变化、遗留物 |
| 替代关联方式 | — | **行级 OCR + 关键行锚点（首次出现即事件）** | — |
| 主要风险 | 分辨率低 → 误检 | 刷屏 → 事件风暴（需去重窗口） | 光照/遮挡 → ID 跳变 |
| 相对工作量 | 1.0×（基准） | **0.7×**（不做跟踪反而更简单） | **1.8×**（最难） |
| 分支名 | `W2A-tracker` | `W2B-ocr-event` | `W2C-tracker+align` |

**两个直接结论：**

1. **WM-02 必须做成可插拔关联器**，不是单一 Tracker。接口统一成：

```python
class Associator(ABC):
    """把逐帧检测组织成"有身份的时间序列"。追踪和 OCR 事件关联都实现它。"""
    def update(self, t: datetime, detections: list[Detection]) -> list[Track]: ...

class TrackerAssociator(Associator):     # ①③：ByteTrack 式 IoU 关联
class OcrEventAssociator(Associator):    # ②：文本行哈希做身份，首次出现即新 track
```

2. **如果你是终端录屏，别硬上跟踪**。文本行没有几何连续性，IoU 关联会产出大量碎片 ID，反而让事件层淹没在噪声里。老老实实做"错误码首次出现 + 刷屏去重"就是对的。

选择方式：配置项 `VISION_SOURCE ∈ {dashboard, terminal, patrol}`，默认 `dashboard`；`terminal` 自动切到 `W2B` 分支并关闭 tracker。

---

## 3. 目标架构

```
┌─────────────────────── 时间轴 ───────────────────────┐
│                                                       │
│  帧序列 ──► 检测 ──► 跟踪 ──► 事件 ──► 状态向量 s_t  │
│  (已有)    (已有)   (★新增)  (★新增)   (★新增)      │
│                                                       │
│                        s_t, a_t                       │
│                          │                            │
│                          ▼                            │
│               ┌─────────────────────┐                 │
│               │ 世界模型 (★新增)     │                 │
│               │ s_{t+1} = f(s_t,a_t) │                │
│               │ + 不确定性估计       │                │
│               └─────────┬───────────┘                 │
│                         │                             │
│         ┌───────────────┼───────────────┐             │
│         ▼               ▼               ▼             │
│   风险分级         处置方案预演      解说(narrator)   │
│   (已有 policy)   (RL policy 已有)   (已有)          │
│                         │                             │
│                         ▼                             │
│              预测误差 → 采样 → 增量训练（自学习闭环）  │
└───────────────────────────────────────────────────────┘
```

### 3.1 状态向量（唯一新增的核心抽象）

不要用像素做世界模型的输入——1.7B 尺度 + 单机显卡撑不住，而且没必要。**世界模型吃结构化状态，视觉只是状态的一个来源。**

```python
# ai-service/app/world_model/state.py（新增）
class OpsState(BaseModel):
    t: datetime
    # 来自指标（anomaly_detector / forecast_detector 已有）
    metrics: dict[str, float]          # {"cpu":0.92,"qps":1200,"latency_p99":840}
    # 来自拓扑（rootcause / fault_propagation 已有）
    topology: dict[str, dict]          # node -> {status, neighbors, load}
    # 来自日志/链路（log_classifier / trace_detector 已有）
    signals: list[Signal]              # {kind, count, severity}
    # 来自视觉（★新增，本方案贡献）
    visual: VisualObs | None           # {elements, changed_rate, red_blocks}
    # 来自动作（executor / rl_policy 已有）
    last_action: str | None
```

**关键设计**：`visual` 只是 `OpsState` 的一个**可选字段**。没有视觉时世界模型照样跑（退化成一维时序预测）。这样视觉是增强，不是单点依赖。

#### 3.1.1 与 `EvidenceEnvelope` 的字段映射（Z0-01 已定，实现 WM-01 时按此对齐）

封套已存在于 `ai-service/app/schemas/evidence_envelope.py`，`OpsState` 不是它的替代品，而是**它的结构化投影**：

| `OpsState` 字段 | 对应封套语义 | 硬规则 |
|---|---|---|
| `t` | `EvidenceEnvelope.round` 的时间锚 | 状态序列只追加，不回写旧 round |
| `metrics` / `topology` / `signals` | `EvidenceRef(kind=metric/topology/log)` | 每个来源一条 ref；`derivation` 按 observed/derived/inferred 标注 |
| `visual.raw_shot_digest` | 截图证据 | **必须调用 `canonical_digest`**（`app/core/canonical.py`），不得自算 sha256 |
| `visual.elements` | `EvidenceRef(kind=vision)` | 检测结果带 `module_version`；无检测器版本时整条 ref 标 `quality=partial` |
| 整个 `OpsState` | 可整段塞进一个 `EvidenceEnvelope(round=n)` | 序列化后 `digest` 必须等于 `object_digest(OpsState)` |

**结论**：`OpsState` 新增字段时，先问"它对应哪条 `EvidenceRef`"，答不上来就不该进状态向量。

### 3.2 世界模型（预测下一状况）

三档实现，按代价递增，**先做最便宜的**：

| 档 | 结构 | 训练成本 | 何时用 |
|---|---|---|---|
| **W0** 基线 | 每个指标独立 AR / 他们已有的 `patchtst_model` 预测未来 h 步 | 已有 | **先跑 W0 拿基线数** |
| **W1** 状态转移 | `GRU/Transformer(s_t, a_t) → (s_{t+1}, σ)`，多任务 | 单卡小时级 | **本方案默认档** |
| **W2** 潜空间世界模型 | Dreamer 式 RSSM：编码 s_t 到潜变量 z，在 z 上演化 | 单卡天级 | 竞赛拔高才上 |

**W1 的输出契约**（这才是"预测下一个状况"能落地的地方）：

```json
{ "horizon": [60, 300, 900],
  "predicted_state": { "metrics": {...}, "topology_delta": {...} },
  "uncertainty": { "cpu": 0.12, "latency_p99": 0.31 },
  "risk": {"level":"HIGH","reason":"p99 在 900s 内越阈概率 0.78"},
  "degraded": false }
```

`uncertainty` 必须给——**没有不确定性估计的预测，在运维里等于赌博**。用 MC dropout 或分位数回归都能出。

### 3.3 三块 ★ 新增的落地形态

**A. 跟踪（跨帧身份）**
- 输入：`[{t, detections:[{cls,bbox,score}]}]`
- 算法：ByteTrack（MIT，两阶段关联，不用 ReID，CPU 也能跑）
- 输出：`[{track_id, cls, path:[{t,bbox}], dwell_time, transition}]`
- **运维特化**：跟踪的不是"人"，是"UI 元素 / 指标块"。`transition` 要能表达"这个状态灯从绿变红""这个数字从稳定变为抖动"。

**B. 事件识别（发生了什么）**
- 规则 + 学习双轨，**先规则后学习**：
  - 规则：`status_led: green→red`、`error_dialog.appear`、`latency.p99 > 3σ 持续 3 帧`
  - 学习：小 Transformer/TCN 吃 track 特征序列做事件分类（他们 `log_model.py` 可复用结构）
- 输出：`[{event_type, t, involved_tracks, confidence}]`
- **这一层是给人看的**：没有事件层，运维看到的还是"一堆数字在动"。

**C. 预测（下一状况）**
- 见 §3.2。**预测的对象是 `OpsState`，不是像素帧。** 直接预测下一帧图像在运维场景是浪费——你不需要知道像素，你需要知道"5 分钟后 p99 会不会越阈"。

### 3.4 自学习闭环（"自主自我学习"的正确形态）

"自主"不等于"无人监督乱学"。运维场景必须留人闸：

```
预测 → 实际发生 → 算误差 → 误差超阈的样本进"待复核池"
                                    │
                     人工/规则确认（少量）
                                    │
                     样本入训练集 → 增量训练（EWC 防遗忘）
                                    │
                     评测集回归 → 通过才上线，否则回滚
```

**三条铁律**：
1. **预测误差是唯一的学习信号**，不是"用户点赞"。
2. **超阈样本必须经人确认**才能进训练集（`continual_learner.py` 已有增量能力，缺的是这个闸）。
3. **每次增量训练都要跑固定评测集**（回滚判据），这是 WM-07 的核心。

---

## 4. 深度 Agent 算法清单（多多益善，按性价比排序）

### P0 必做（本方案基线，成本可控）

| 能力 | 算法 | 参考实现（许可证**待核验**） |
|---|---|---|
| 多目标跟踪 | ByteTrack | [ifzhang/ByteTrack](https://github.com/ifzhang/ByteTrack)（MIT） |
| 单帧检测 | YOLO 系 | ⚠️ **见 §5 合规红旗** |
| 时序异常 | AnomalyTransformer / PatchTST | **你已有**（`anomaly_transformer.py`、`patchtst_model.py`） |
| 状态转移预测 | GRU/Transformer 多任务回归 | 自己写，~300 行 |
| 持续学习 | EWC / 经验回放 | **你已有**（`continual_learner.py`）；可参照 [avalanche-lib/avalanche](https://github.com/avalanche-lib/avalanche)（MIT） |
| 解说 | LLM 读状态序列生成自然语言 | **你已有**（`temporal_narrator.py`） |

### P1 竞赛加分（有论文、有代码、能讲清楚）

| 能力 | 算法 | 参考实现（待核验） |
|---|---|---|
| 世界模型（潜空间） | **DreamerV3**（RSSM，跨域通用） | [danijar/dreamerv3](https://github.com/danijar/dreamerv3)；[eclectic-sheep/sheeprl](https://github.com/eclectic-sheep/sheeprl) 有 DreamerV2/V3 实现 |
| 模型预测控制式决策 | **TD-MPC2** | [nicklashansen/tdmpc2](https://github.com/nicklashansen/tdmpc2) |
| 自监督视频表征 | **V-JEPA 2**（不靠像素重建，预测表征） | [facebookresearch/vjepa2](https://github.com/facebookresearch/vjepa2) ⚠️ 权重多为 **CC-BY-NC**，商用/竞赛提交前必核 |
| 视觉分割 | **SAM 2**（视频分割，带记忆） | [facebookresearch/sam2](https://github.com/facebookresearch/sam2) |
| 开放词表检测 | **GroundingDINO** | [IDEA-Research/GroundingDINO](https://github.com/IDEA-Research/GroundingDINO)；**你已用**（`grounding.py`） |
| 动作/事件识别 | **MMAction2** | [open-mmlab/mmaction2](https://github.com/open-mmlab/mmaction2) |
| 屏幕元素解析 | **OmniParser** | [microsoft/OmniParser](https://github.com/microsoft/OmniParser)（上一轮桌面手已列） |

### P2 赛道拔高（讲得动就上，讲不动别碰）

| 能力 | 算法 | 参考 |
|---|---|---|
| 因果发现 | NOTEARS / PC 算法 | 无强推荐，需自己选型 |
| 反事实推演 | 结构性因果模型 + LLM | 参考你清单里的"反事实故障推演引擎" |
| 预测性编码 | 分层预测网络，误差即异常 | 类脑方向，落地案例少 |
| 世界模型生成样本 | Dreamer 在潜空间 rollout 造训练样本 | 解决故障样本稀缺 |

---

## 5. 合规红旗（必须先处理，否则可能白做）

### 🔴 红旗一：`yolo26n.pt` 大概率是 AGPL-3.0

`app/vision/classes.py` 第 6 行明确写着"避免 ultralytics 写 `data.yaml` 时的编码问题"——**你这是 Ultralytics 生态**。Ultralytics 的许可是 **AGPL-3.0**（或其企业许可）。

而你自己的 `design-system/MASTER.md` 的 Open Source Intake 写着：

> **Tier C, prohibited**: grafana/grafana (**AGPL-3.0** network copyleft) …

**按你自己的规则，AGPL 属于禁止项。** 这不是小事：竞赛提交材料若宣称"开源可商用"，权重来源会被追问。

三条出路（按推荐度）：
1. **换成 Apache/MIT 的检测器**：`torchvision` 的 FasterRCNN/RetinaNet（BSD-3）、`ultralytics` 的替代 `YOLOX`（Apache-2.0）、`RT-DETR`（部分实现 Apache-2.0，需核）。
2. 保留 Ultralytics 但**明确标注"仅用于研究/竞赛演示，不分发"**，并把它从"可商用开源"叙述里摘出去。
3. 联系 Ultralytics 拿企业许可（不现实）。

**建议走 1**，并把替换写进 WM-04。

#### 决策记录（2026-11-20）：已选路线 1，替换代码已落地

实测证据（`reports/detector-license-audit-2026-11-20.md`）：

- 两个权重的 checkpoint 内嵌 `license=AGPL-3.0 (https://ultralytics.com/license)`；GitHub API 返回 `spdx_id=AGPL-3.0`；
- 但 `ai-service/app/**` 目前**没有任何运行时路径** import ultralytics，两个权重是"死权重"（无调用方）——替换成本最低的时刻就是现在。

已交付：

| 项 | 文件 | 状态 |
|---|---|---|
| 运行时检测器（BSD-3，懒加载 + 显式降级） | `ai-service/app/vision/detector.py` | 已实现，输出归一化 bbox，可直接喂 `/api/nn/vision-forecast` |
| 训练脚本（同一份 YOLO 格式数据集） | `ai-service/scripts/train_vision_frcnn.py` | 已实现，`--dry-run` 自检 + 1 epoch CPU 冒烟跑通 |
| 数据集读回/自检（无 PyYAML、无 ultralytics） | `ai-service/app/vision/dataset.py`（新增 `read_data_yaml` / `parse_yolo_labels` / `dataset_health`） | 已实现 |
| 运行时 AGPL 不变式 | `ai-service/app/tests/test_runtime_no_ultralytics.py` | 已通过，后续若有人偷偷接回 AGPL 会红 |

**未完成的边界（不要当成已做）**：
1. 没有训练新权重——冒烟用的是随机初始化的 64px 小模型，`mAP=NOT_RUN`（需 pycocotools）；
2. 检测器尚未接进 `services/vision_forecast` 的取帧链路，`YOLO/AGPL` 的"能力替换"只完成了组件层，端到端接线属 WM-04；
3. `yolo26n.pt` / `yolov8n.pt` 仍在磁盘（gitignore 状态），未删——删之前需确认没有历史脚本引用。

### 🟡 红旗二：NBA 那三个仓库的许可证未知

移植任何代码前必须先看 LICENSE。竞技/学术项目里常见 **无 LICENSE**（= 保留所有权利，法律上不可复制）。**只迁移"思路与结构"，不复制代码**——这是最安全的做法，也是我在 §2 只给映射表不给 diff 的原因之一。

### 🟡 红旗三：V-JEPA 2 权重多为 CC-BY-NC

非商用。竞赛若提交到需要商用声明的赛道，**只用它的思想（预测表征而非像素），不用它的权重**。

---

## 6. 与既有体系的接线

| 既有模块 | 怎么接 |
|---|---|
| `anomaly_detector` / `forecast_detector` | 提供 `metrics` 序列 → 进 `OpsState` |
| `rootcause_detector` / `fault_propagation` | 提供 `topology`；`fault_propagation` 的输出与 W1 预测**互为交叉验证**（两者不一致时降低置信度，不要取平均） |
| `log_classifier` / `trace_detector` | 提供 `signals` |
| `vision/*` | 提供 `visual`；**新增运行时路径，离线脚本不动** |
| `temporal_narrator` | 消费 `predicted_state` 生成人读解说 |
| `rl_policy` | 消费世界模型做**方案预演**（在潜空间 rollout，不碰真机） |
| `continual_learner` | 接自学习闭环的训练段；**新增入池闸** |
| `agent/policies/risk.py` | 消费 `risk.level` 做风险分级 |

---

## 7. 验收

| 编号 | 判据 |
|---|---|
| W1 | `OpsState` 三不变量：`visual` 缺失时模型仍能跑（无视觉降级用例）；时间戳单调；`topology` 节点集合与契约一致 |
| W2 | 跟踪：合成序列（3 个元素，其中 1 个中途消失又出现）→ `track_id` 复识别正确率 100%（规则可判） |
| W3 | 事件层：构造 `status_led green→red` 序列 → 事件 `LED_TURN_RED` 被识别且 `confidence>0.8` |
| W4 | 预测：W0 基线（PatchTST 直推）分数落盘；W1 相对 W0 在预测 MAE 上**不差于**基线（差就说明白差在哪，不许含糊） |
| W5 | 不确定性：`uncertainty` 字段非空；高噪样本的 `uncertainty` 显著高于平稳样本（区分度可测） |
| W6 | 自学习：误差超阈样本进"待复核池"而非直接进训练集；未经确认不得训练 |
| W7 | 增量训练后固定评测集分数不下降超过 2 个百分点，否则自动回滚 |
| W8 | 合规：仓库内不存在 AGPL 权重的对外分发；`reports/` 有检测器与所有新增依赖的 SPDX 核验记录 |

---

## 8. 明确不做

1. ❌ **不做"预测下一帧图像"**。运维不需要像素级未来，需要状态级未来。
2. ❌ **不让视觉成为单点依赖**。视觉挂了系统要能退化运行。
3. ❌ **不做无人监督的自动训练**。入池必须有人闸。
4. ❌ **不复制 NBA 仓库的代码**（许可证未知）。只迁范式。
5. ❌ **不在本阶段上 DreamerV3 全量**。W1 够了；W2 是竞赛拔高项，先把 W1 的数字跑出来。
6. ❌ **不用云端 VLM 处理含敏感信息的画面**（延续桌面手那条约束）。

---

## 9. 未决问题

1. **三个仓库的实际内容未知**。§2 的映射是范式推断。你把 README + 关键文件贴进来，我出逐文件改写清单（含"哪几行必须改掉，因为它假设了篮球语义"）。
2. **"元宝"指代未确认**。我按"开源原版/上游"理解。若指腾讯元宝产品，方向要换。
3. **预测 horizon 的业务口径未定**。60/300/900 秒是暂定，得看你的告警分级与 MTTR 目标。
4. **视觉来源未定**。监控墙截图？终端录屏？机器人巡检视频？这三种的跟踪难度差很多，直接影响 W2/W3 的工作量。
5. **GPU 预算未知**。W1 单卡小时级是我的估计，实际取决于状态维度与样本量。

---

## 10. 一句话总结

NBA 那套东西的可迁移价值，不在"用了 YOLO"，而在**它把一段视频变成了一条可预测的时间轴**。

你现在有眼睛（单帧检测），但没有**记忆**（跟踪）、没有**叙述**（事件）、也没有**预感**（下一状态）。补上这三样，"深度视觉"才成立——而且这三样恰好都能落在你已有的 `temporal_narrator` / `fault_propagation` / `continual_learner` 上，不用推倒重来。
