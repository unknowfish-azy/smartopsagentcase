---
name: demo-video-director
description: 把真实产品页面录屏剪成带红框箭头、鼠标轨迹、点击环、章节卡、克隆配音和烧录字幕的展示片。当用户要做产品演示视频、项目答辩视频或复刻同款科技解说片时使用。不用于纯素材剪辑。
---

# Demo Video Director

把真实页面操作录屏合成 1920x1080 / 30fps 的展示片。核心不是手剪，而是先把分镜、旁白、标注写成数据，再让 ffmpeg 确定性渲染。

## 产出结构

```text
<work>/
├── storyboard.json          # 分镜、旁白、标注、录制动作（唯一事实来源）
├── capture-events.json      # 录制得到的鼠标/点击/框选/箭头时间线
├── raw/<shot>.webm          # 每个镜头的原始录屏
├── voice/lines/<shot>.wav   # 每镜旁白
├── cards/<shot>.png         # 章节卡
├── final/<name>.mp4         # 成片
└── .work/                   # 分段、字幕、抽帧、报告
```

## 铁律

- 改旁白、时长、标注都改 `storyboard.json`，不要手剪成片。
- 每镜旁白一个 WAV，文件名等于镜头 id；合成时按音频长度自动延长镜头。
- 真实页面之间硬切；只有章节卡/静帧用 0.18–0.22s 淡入淡出。
- 演示、模拟、未接真机的内容必须在画面或字幕里保留标识，不能包装成真实能力。
- 交付前必须过 `qc.py`，并人工抽查每镜 early/click/mid/late 四帧。

## 依赖

- `ffmpeg` / `ffprobe` 在 PATH，且 ffmpeg 带 libass（烧字幕）
- Python 3.10+：`pillow`、`numpy`
- 录制：`playwright`，并执行 `playwright install chromium`
- 配音二选一：`edge-tts`（轻量）或本地 F5-TTS（声线克隆，需 GPU 与模型）
- 中文系统字体：Windows 微软雅黑 / macOS 苹方 / Linux Noto Sans CJK

## 流程

以下命令在 skill 目录执行；`storyboard.json` 放你的项目工作目录，脚本按它所在目录解析 `raw/voice/cards/final`。

### 1. 定章节与分镜

先定 8–13 个章节，每章 3–5 个镜头，总镜头 35–50 个，成片 6–9 分钟。每镜 7–14 秒，一个镜头只讲一件事。推荐节奏：

```text
开场 2 镜 → 问题/架构 2 镜 → 核心能力 4 组 × 4 镜 → 工程与诚实边界 2 镜 → 结尾 1 镜
```

先写 `storyboard.json`，字段见 `assets/storyboard.example.json`：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 镜头号，也是 WAV/卡片/录屏文件名，如 `S02A` |
| `chapter` | 是 | 左上角章节名，如 `02 证据驱动问答` |
| `target` | 是 | 目标秒数；有旁白时实际时长取 `max(target, 旁白 + 0.35)` |
| `text` | 是 | 底部字幕原文 |
| `spoken` | 否 | 给 TTS 的读法；英文缩写写成 `B M 二十五`、`A I`、`D A G` |
| `overlay` | 否 | 左上角副标题/卖点，建议不超过 24 字 |
| `route` | 否 | 页面路由；有 `route` 走录屏，无 `route` 走章节卡 |
| `visual` | 否 | 给章节卡用的一句话画面说明 |
| `card_title` / `card_points` | 否 | 章节卡主标题与要点，默认从 `chapter` / `visual` 推导 |
| `actions` | 否 | 录制动作，`record_pages.py` 使用 |
| `events` | 否 | 手写标注，和录制事件合并，可直接做无录屏的标注 |
| `image` | 否 | 用一张静帧代替录屏 |

旁白长度按成片 1.5 倍语速估算：**每镜 45–85 字**，约 8–12 秒。宁可短，不要赶。

### 2. 录制真实页面

```bash
python scripts/record_pages.py \
  --storyboard storyboard.json \
  --base-url http://localhost:5173 \
  --out capture-events.json \
  --storage-state auth.json \
  --only S02A,S02B
```

- 每个镜头独立新建 context 录制，输出 `raw/<id>.webm`。
- 脚本自动记录鼠标轨迹、点击、框选、箭头的时间线到 `capture-events.json`。
- 首次登录：加 `--headed --login-wait 60` 手动登录，登录态会写回 `--storage-state`。
- 录制前确认页面没有加载骨架、弹窗、滚动条抖动；每镜操作完留 1 秒静止。
- 已有录屏时不必重录：在 `capture-events.json` 写 `{id, video, video_content_offset, events: []}`，再用 storyboard 的 `events` 手写标注即可。

`actions` 支持：`click`、`type`、`press`、`hover`、`move`、`scroll`、`wait`、`box`、`arrow`。

```json
"actions": [
  {"action": "click", "selector": "text=新建问答", "label": "新建问答"},
  {"action": "type", "selector": "textarea", "text": "MySQL 连接数打满怎么排查？", "label": "输入真实问题"},
  {"action": "click", "selector": "button[type=submit]", "label": "发送", "hold": 4},
  {"action": "box", "selector": ".answer-card", "label": "答案与引用", "seconds": 3},
  {"action": "arrow", "from_selector": ".answer-card", "to_selector": ".citation", "label": "回到原文", "seconds": 3}
]
```

### 3. 生成章节卡

```bash
python scripts/build_cards.py --storyboard storyboard.json --out cards
```

深色科技风、左上角章节号、主标题、要点、底部项目名。想改文案只改 storyboard 的 `card_title` / `card_points`。

### 4. 配音

克隆声线（F5-TTS，本地，参考音频不出本机）：

```bash
python scripts/synthesize_voice.py \
  --storyboard storyboard.json \
  --engine f5 \
  --ref-audio reference.wav \
  --ref-text "参考音频里逐字对应的文本" \
  --ckpt /path/to/model.safetensors \
  --vocoder /path/to/vocos \
  --out voice/lines \
  --speed 1.2 --trim-pauses
```

没有 GPU 时用 edge-tts：

```bash
python scripts/synthesize_voice.py --storyboard storyboard.json --engine edge --voice zh-CN-YunxiNeural --out voice/lines
```

配音规则：

- `--speed 1.2` 合成，合成器再按 `--tempo 1.5` 提速；先合成再提速比直接 1.5 倍合成自然。
- `--trim-pauses` 只收敛超过 320ms 的长静音，保留句读和呼吸。
- 每段必须检查字数、吞字和同音字；发现有问题的镜头用 `--only S02B --overwrite` 重录，不要整片重来。

### 5. 合成

```bash
python scripts/composite.py --storyboard storyboard.json --final
```

常用参数：

```bash
python scripts/composite.py --storyboard storyboard.json --only S02B,S02C   # 只重渲染几镜
python scripts/composite.py --storyboard storyboard.json --final --muted    # 先看画面
python scripts/composite.py --storyboard storyboard.json --final --tempo 1.5 --crf 18
```

合成器自动完成：红框、红箭头、合成鼠标、点击环、章节/卖点标签、底部字幕避让、卡片淡入淡出、旁白提速、分段 H.264、整片 loudnorm。

### 6. 验收

```bash
python scripts/qc.py --storyboard storyboard.json --final final/demo-video.mp4 --require-voice
```

`--require-voice` 把缺旁白当作错误；草稿阶段可以不加，只当告警。

必须同时过机器检查和人工抽帧：

- 每镜有 `_early/_click/_mid/_late` 四帧，标注没有压住文字、没有指向空白。
- 字幕不挡红框、箭头、鼠标；一行不超过 30 字，英文词和版本号不断行。
- 旁白与画面同步，没有一镜到底念两件事。
- 整片响度约 -16 LUFS，真峰值不高于 -1.5 dBTP。
- 演示/模拟标识在全片保留。

## 视觉规范

| 元素 | 参数 |
| --- | --- |
| 画布 | 1920x1080，30fps，H.264 high@4.1，CRF 18，yuv420p |
| 主色 | 红 `#EE3E46`；深色底 `#0B1020`；正文白 `#E2E8F0` |
| 红框 | 圆角 8，双层描边（黑 11px + 红 5px），四角亮线，内填充红 6% |
| 箭头 | 8px 红线 + 16px 黑影，三角箭头，起点圆点 |
| 鼠标 | 64px 白色指针 + 深色描边；移动用 smoothstep 缓动 0.35–0.6s |
| 点击环 | 直径 28→160，0.72s 扩散，红环 + 半透明中心 |
| 字幕 | 48px 粗体，最多 30 字/行，底部安全区，自动避开标注区 |
| 标签 | 26px 粗体，贴近标注，最多 12 字，中文 |
| 章节/卖点 | 29px / 23px，左上角，距边 34px |
| 卡片转场 | 淡入 0.18s / 淡出 0.22s；页面之间硬切 |
| 音频 | 48kHz 立体声，AAC 160k（分段）/ 192k（成片），loudnorm I=-16 TP=-1.5 LRA=11 |

## 标注规则

- 只标“观众此刻该看的地方”，一镜最多 2 个标注；不要每镜都标。
- 红框框住一个控件或一块结果，不要框整页；框比目标四周大 8–16px。
- 箭头从标签指向目标，尽量短，不跨过正文；标签放箭头起点一侧。
- 标注在页面稳定后 0.2–0.8s 出现，持续 2.5–4s；点击环只给真实点击。
- 标签必须是中文业务词，如“答案与引用”“越界预测”“人工审批”，不要留英文占位词。

## 常见故障

| 现象 | 处理 |
| --- | --- |
| `ass` 滤镜不存在 | 换带 libass 的 ffmpeg 构建 |
| 字幕盖住红框 | 缩短字幕或调整标注位置；`subtitle_y()` 会避开框/箭头/鼠标 |
| 某镜画面比旁白短 | 合成器自动延长；若仍紧，改 `target` 或删字 |
| 点击位置偏了 | 录屏时 viewport 必须是 1920x1080，`device_scale_factor=1` |
| 录像开头多出等待 | 调 `--offset-bias`（默认 -0.3，越负越早切） |
| 响度不达标 | 检查是否有镜头缺旁白；成片 loudnorm 只做一次，不要重复压 |
| 配音有电音/吞字 | 降 `--speed` 到 1.1，或拆短句；不要用 atempo 超过 1.6 |

## 交付

成片放 `final/`，同目录保留 `render-report.json`；把 `storyboard.json`、`capture-events.json`、`voice/lines`、`cards` 一起交付，别人才能复现和改版。

完整案例（46 镜、13 章、8 分钟国赛展示片的参数与踩坑记录）见 `references/pipeline.md`。
