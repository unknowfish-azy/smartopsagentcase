# Demo Video Director

把真实产品页面的操作录屏，剪成 1920x1080 / 30fps、带旁白、字幕、红框、箭头、鼠标轨迹和点击环的展示片。

适合做产品演示、项目答辩、技术评测、开源项目介绍这类“要拿真实页面当证据”的视频。核心不是手剪，而是先把分镜、旁白、标注写成数据，再让 ffmpeg 确定性渲染。

> `SKILL.md` 是给 AI Agent 读的执行指令；这份 README 是给人看的快速上手。

## 能做出什么效果

- 真实页面录屏，不是 PPT 或纯动画
- 红色双层描边、四角亮线的局部标注框
- 红色箭头 + 中文标签，直接指向控件或结果
- 合成鼠标轨迹、真实点击环
- 深色科技风章节卡，自动编号
- 每镜独立旁白，支持 F5-TTS 声线克隆或 edge-tts
- 底部大字幕，自动避开红框、箭头和鼠标
- 成片 1.5 倍语速、-16 LUFS 响度统一
- 自动抽出每镜 early / click / mid / late 四帧做验收

## 目录结构

```text
demo-video-director/
├── SKILL.md                     # Agent 执行指令
├── README.md                    # 本文件
├── assets/
│   └── storyboard.example.json  # 可直接改的示例分镜
├── references/
│   └── pipeline.md              # 46 镜 / 13 章完整案例与踩坑记录
└── scripts/
    ├── record_pages.py          # Playwright 逐镜录屏 + 事件采集
    ├── build_cards.py           # 章节卡生成
    ├── synthesize_voice.py      # F5-TTS / edge-tts 配音
    ├── composite.py             # 标注、字幕、混音、拼接
    └── qc.py                    # 成片验收
```

一个项目的工作目录长这样：

```text
<work>/
├── storyboard.json          # 分镜、旁白、标注、录制动作（唯一事实来源）
├── capture-events.json      # 录制得到的鼠标/点击/框选/箭头时间线
├── raw/<shot>.webm          # 每镜原始录屏
├── voice/lines/<shot>.wav   # 每镜旁白
├── cards/<shot>.png         # 章节卡
├── final/<name>.mp4         # 成片
└── .work/                   # 分段、字幕、抽帧、报告
```

## 环境要求

- Python 3.10+
- ffmpeg / ffprobe，且 ffmpeg 带 `libass`（烧字幕）
- Python 包：`pillow`、`numpy`
- 录制：`playwright` + Chromium
- 配音：`edge-tts`，或本地 F5-TTS（声线克隆，建议 GPU）
- 中文字体：Windows 微软雅黑 / macOS 苹方 / Linux Noto Sans CJK

```bash
pip install pillow numpy playwright edge-tts
playwright install chromium
```

检查 ffmpeg 是否带 libass：

```bash
ffmpeg -filters
```

输出里能看到 `ass` 滤镜即可。Windows 可以用 `ffmpeg -filters | findstr ass`，macOS / Linux 用 `ffmpeg -filters | grep ass`。

## 快速开始

以下命令在 Skill 根目录执行；`storyboard.json` 放你的项目工作目录，脚本会自动按它所在目录读取 `raw/voice/cards/final`。

### 1. 准备分镜

```bash
cp assets/storyboard.example.json /path/to/work/storyboard.json
```

Windows PowerShell：

```powershell
Copy-Item assets\storyboard.example.json D:\work\storyboard.json
```

最小分镜示例：

```json
{
  "meta": {
    "project": "Acme 运维平台",
    "title": "让 AI 可信地完成下一步",
    "resolution": "1920x1080",
    "fps": 30,
    "voice_tempo": 1.5,
    "output_name": "acme-demo.mp4"
  },
  "shots": [
    {
      "id": "S00A",
      "chapter": "00 开场",
      "target": 9,
      "visual": "深色片头",
      "text": "这是 Acme 运维平台的真实演示。",
      "overlay": "真实页面 · 证据驱动"
    },
    {
      "id": "S01A",
      "chapter": "01 问答",
      "target": 10,
      "route": "/chat",
      "text": "用户直接描述问题，系统给出答案和引用。",
      "overlay": "答案与引用一起返回",
      "actions": [
        {"action": "click", "selector": "text=新建问答", "label": "新建问答"},
        {"action": "type", "selector": "textarea", "text": "MySQL 连接数打满了怎么排查？", "label": "输入问题"},
        {"action": "click", "selector": "button[type=submit]", "label": "发送", "hold": 5},
        {"action": "box", "selector": ".answer-card", "label": "答案与引用", "seconds": 3}
      ]
    }
  ]
}
```

没有 `route` 的镜头会走章节卡；有 `route` 的镜头会走真实页面录屏。

### 2. 生成章节卡

```bash
python scripts/build_cards.py --storyboard /path/to/work/storyboard.json
```

默认输出到 `<work>/cards`。卡片文案改 storyboard 里的 `card_title` / `card_points`。

### 3. 录制真实页面

```bash
python scripts/record_pages.py \
  --storyboard /path/to/work/storyboard.json \
  --base-url http://localhost:5173 \
  --storage-state auth.json
```

- 每个镜头独立录制，输出到 `<work>/raw/`
- 自动把鼠标轨迹、点击、框选、箭头写进 `<work>/capture-events.json`
- 首次登录：加 `--headed --login-wait 60`，手动登录后登录态会写回 `--storage-state`
- 只重录某几镜：`--only S02A,S02B`

已有录屏时不必重录，在 `capture-events.json` 里写：

```json
[
  {
    "id": "S01A",
    "route": "/chat",
    "video": "D:/work/raw/S01A.mp4",
    "video_content_offset": 1.8,
    "events": []
  }
]
```

再用 storyboard 的 `events` 手写标注。

### 4. 配音

没有 GPU，用 edge-tts：

```bash
python scripts/synthesize_voice.py \
  --storyboard /path/to/work/storyboard.json \
  --engine edge \
  --voice zh-CN-YunxiNeural
```

有声线参考音频，用 F5-TTS 克隆：

```bash
python scripts/synthesize_voice.py \
  --storyboard /path/to/work/storyboard.json \
  --engine f5 \
  --ref-audio reference.wav \
  --ref-text "参考音频里逐字对应的文本" \
  --ckpt /path/to/model.safetensors \
  --vocoder /path/to/vocos \
  --speed 1.2 --trim-pauses
```

默认输出到 `<work>/voice/lines/<shot>.wav`。

### 5. 合成

```bash
python scripts/composite.py --storyboard /path/to/work/storyboard.json --final
```

只重渲染几镜：

```bash
python scripts/composite.py --storyboard /path/to/work/storyboard.json --only S02B,S02C
```

先看画面不配音：

```bash
python scripts/composite.py --storyboard /path/to/work/storyboard.json --final --muted
```

合成器会自动完成红框、箭头、合成鼠标、点击环、章节/卖点标签、字幕避让、卡片淡入淡出、旁白提速、分段 H.264 和整片 loudnorm。

### 6. 验收

```bash
python scripts/qc.py \
  --storyboard /path/to/work/storyboard.json \
  --final /path/to/work/final/acme-demo.mp4 \
  --require-voice
```

检查项：

- 分辨率、帧率、时长是否符合 `meta`
- 整片响度是否在 -18 到 -14 LUFS
- 真峰值是否不高于 -1.0 dBTP
- 是否有镜头缺旁白
- 标注定位警告是否清零
- 每镜 mid 抽帧是否齐全，并生成 `qc/contact-sheet.jpg`

`--require-voice` 把缺旁白当作错误；草稿阶段可以不加。

## storyboard.json 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 镜头号，也是 WAV/卡片/录屏文件名，如 `S02A` |
| `chapter` | 是 | 左上角章节名，如 `02 证据驱动问答` |
| `target` | 是 | 目标秒数；有旁白时实际时长取 `max(target, 旁白 + 0.35)` |
| `text` | 是 | 底部字幕原文 |
| `spoken` | 否 | 给 TTS 的读法；英文缩写写成 `B M 二十五`、`A I`、`D A G` |
| `overlay` | 否 | 左上角副标题/卖点，建议不超过 24 字 |
| `route` | 否 | 页面路由；有 `route` 走录屏，无 `route` 走章节卡 |
| `visual` | 否 | 章节卡的一句话画面说明 |
| `card_title` / `card_points` | 否 | 章节卡主标题与要点 |
| `actions` | 否 | 录制动作，`record_pages.py` 使用 |
| `events` | 否 | 手写标注，和录制事件合并 |
| `image` | 否 | 用一张静帧代替录屏 |

## 录制动作

| action | 参数 | 说明 |
| --- | --- | --- |
| `click` | `selector`、`label`、`hold` | 移动鼠标并点击 |
| `type` | `selector`、`text`、`label` | 点击输入框并逐字输入 |
| `press` | `key` | 按键，如 `Enter` |
| `hover` | `selector`、`label` | 悬停 |
| `move` | `selector` 或 `to` | 只移动鼠标 |
| `scroll` | `dy`、`selector` | 滚动页面 |
| `wait` | `seconds` | 静止等待 |
| `box` | `selector`、`label`、`seconds`、`padding` | 框住元素 |
| `arrow` | `from_selector`、`to_selector`、`label`、`seconds` | 从 A 指向 B |

## 手写标注事件

```json
"events": [
  {"type": "cursor", "start": 0.3, "end": 0.8, "from": [200, 900], "to": [760, 430], "label": "移动到答案"},
  {"type": "click", "start": 0.85, "end": 1.4, "to": [760, 430], "label": "点击查看"},
  {"type": "box", "start": 0.9, "end": 2.6, "box": [520, 300, 620, 300], "label": "答案与引用"},
  {"type": "arrow", "start": 1.8, "end": 2.9, "from": [380, 760], "to": [700, 470], "label": "回到原文"}
]
```

时间单位是秒，相对当前镜头画面起点。

## 视觉规范

| 元素 | 参数 |
| --- | --- |
| 画布 | 1920x1080，30fps，H.264 high@4.1，CRF 18，yuv420p |
| 主色 | 红 `#EE3E46`；深色底 `#0B1020`；正文白 `#E2E8F0` |
| 红框 | 圆角 8，双层描边（黑 11px + 红 5px），四角亮线，内填充红 6% |
| 箭头 | 8px 红线 + 16px 黑影，三角箭头，起点圆点 |
| 鼠标 | 64px 白色指针 + 深色描边，smoothstep 缓动 |
| 点击环 | 直径 28→160，0.72s 扩散 |
| 字幕 | 48px 粗体，最多 30 字/行，自动避让标注 |
| 标签 | 26px 粗体，最多 12 字，中文 |
| 卡片转场 | 淡入 0.18s / 淡出 0.22s；页面之间硬切 |
| 音频 | 48kHz 立体声，AAC 160k（分段）/ 192k（成片），-16 LUFS |

## 安装为 Trae Skill

项目级：

```text
<project>/.trae/skills/demo-video-director/
```

用户级（所有项目可用）：

```text
~/.trae-cn/skills/demo-video-director/
```

把整个 `demo-video-director` 文件夹复制过去即可，`SKILL.md` 是入口。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| `ass` 滤镜不存在 | 换带 libass 的 ffmpeg 构建 |
| 字幕盖住红框 | 缩短字幕或调整标注位置；合成器会自动选重叠最小的档位 |
| 某镜画面比旁白短 | 合成器会自动延长；仍紧就改 `target` 或删字 |
| 点击位置偏了 | 录屏 viewport 必须是 1920x1080，`device_scale_factor=1` |
| 录像开头多出等待 | 调 `--offset-bias`（默认 -0.3，越负越早切） |
| 配音有电音或吞字 | 降 `--speed` 到 1.1，或拆短句；atempo 不要超过 1.6 |
| 响度不达标 | 检查是否有镜头缺旁白；成片 loudnorm 只做一次 |

## 案例

`references/pipeline.md` 记录了这套流程的来源案例：46 镜、13 章、约 8 分钟的国赛展示片，包含分镜骨架、标注排布、1.5 倍语速、字幕避让和诚实边界的具体做法。

## 验证

本地真实页面录制 → 11.7 秒成片 → `qc.py` PASS；章节卡、原始 v5 配音和卡片镜头也单独跑通过。
