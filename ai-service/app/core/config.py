from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 定位为仓库根目录（ai-service/app/core/config.py → 上溯 3 级），
# 与进程启动时的工作目录无关：无论 uvicorn 从仓库根、ai-service/ 还是其他目录启动，
# 都能读到同一份配置，避免因 cwd 不同而静默退回 mock。
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):

    app_name: str = "SmartOpsAgent AI Service"

    app_version: str = "0.1.0"

    host: str = "0.0.0.0"

    port: int = 8001

    debug: bool = False

    # mock / ollama / openai-compatible
    # openai-compatible 用于 DashScope 百炼（含 SFT 微调后的模型）、vLLM 等
    # OpenAI 协议端点：llm_base_url 填 .../compatible-mode/v1 即可，
    # 代码会自动补 /chat/completions；llm_model 填微调产出的模型名。
    llm_provider: str = Field(
        default="mock",
        description="mock / ollama / openai-compatible",
    )

    llm_model: str = "mock-model"

    llm_base_url: str = "http://localhost:11434"

    llm_api_key: str = ""

    # PERF-07：按复杂度路由模型。留空表示未配置路由——此时如实回落到
    # llm_model 并在响应元数据标注 routed=false，不假装"已路由"。
    llm_model_simple: str = ""

    llm_model_complex: str = ""

    # 多模态视觉模型：带真实图片的请求专用，Ollama 需已 pull 该模型。
    # 留空表示未配置视觉能力——此时带图请求会明确报错，不降级、不伪造识别结果。
    # 默认 qwen2.5vl:3b（与 qwen3 同系列、支持 vision、3B 低显存）。
    llm_vision_model: str = "qwen2.5vl:3b"

    # PERF-07：RAG 证据上下文的字符预算（按分数优先装填）。
    context_budget_chars: int = 12000

    # PERF-07：检索缓存。键包含租户/权限/版本，TTL 内的重复查询不再
    # 请求 knowledge 服务；降级与失败结果不缓存。
    rag_cache_ttl_sec: float = 60

    rag_cache_max_entries: int = 128

    # KV-CACHE：Ollama 调用的 keep_alive（秒，payload 传 "Ns" 时长串）。
    # 保模型与已算 KV 缓存驻留——Ollama 只对「最近一次评估」的 prompt 前缀
    # 复用 KV，模型被卸载缓存即丢；这是 prompt 前缀复用生效的前提。
    # 显存预算优先：默认 300（空闲 5 分钟即卸载）。实测完整前缀复用只在请求
    # 间隔 ≤5s 时可靠（见下方心跳结论），长 keep_alive 主要只省掉 250-500ms
    # 冷启动，却让模型（qwen3:1.7b ≈1.5GB、qwen2.5vl:3b ≈3GB）长期驻留
    # 8GB 显卡。显存充裕（≥16GB）可调回 1800。
    llm_keep_alive_sec: int = 300

    # KV-CACHE：Ollama 上下文窗口（payload options.num_ctx）。
    # 0 = 不传、沿用 Ollama 默认（qwen3 默认 4096）。实测（bench_kv_prefix.py）
    # 默认窗口下大 prompt + 生成会把 KV 缓存挤掉，前缀复用失效；
    # 大上下文 RAG 场景建议 8192+（qwen3:1.7b 在 8GB 显存下实测稳定）。
    llm_num_ctx: int = 0

    # KV-CACHE 心跳：空闲期定时发超短请求，重置 Ollama 的 KV 驱逐计时窗口。
    # 【2026-11-16 实测结论（bench_heartbeat.py + 阈值梯度实验，f16 与
    # FLASH_ATTENTION+q8_0 两种配置均已复测）】
    # Ollama 0.40.8 的槽位缓存在每次请求完成后只保留 system+模板头部
    # （~101 tokens，见 server.log 的 cached n_tokens=101 记录），完整
    # prompt 前缀复用仅在请求间隔 ≤5s 时可靠出现（预填充 15-73ms vs
    # 冷启动 250-500ms）；间隔 10s/45s 的心跳均无法维持完整复用，
    # FA+q8_0 也不改变该行为（仅让 5s 内命中更深：73ms vs 172ms）。
    # 因此心跳默认关闭；演示场景的收益来自「演示动线让问题时间邻近」
    # （间隔 ≤5s 自然命中）。可用 scripts/bench_heartbeat.py 重新验证。
    ollama_heartbeat_enabled: bool = False
    # 心跳间隔（秒）。默认 45 秒——远小于 llm_keep_alive_sec(1800)，
    # 足以在空闲期持续刷新驱逐窗口。
    ollama_heartbeat_interval_sec: int = 45
    # 单次心跳超时（秒）。心跳必须快，超时就放弃等下一轮。
    ollama_heartbeat_timeout_sec: float = 5.0
    # 心跳 prompt：**必须与业务 prompt 前缀逐字节一致**才能命中 KV 复用。
    # 默认值匹配 chat._build_prompt 的固定头部（三引号前导 \n + 到「知识库证据：」为止），
    # 尾部只加极短的 "ping" 让 Ollama 有东西生成 → 1 token 即停（num_predict=1）。
    # 如果业务 prompt 模板改了，这里必须同步更新，否则心跳 prefix 对不上。
    ollama_heartbeat_prompt: str = (
        "\n"
        "请回答下面的用户问题。\n\n"
        "要求：\n"
        "- 优先使用知识库证据。\n"
        "- 不要把没有证据支持的内容说成确定事实。\n"
        "- 如果知识库没有足够证据，请明确说明。\n"
        "- 如果涉及执行操作，只给出建议，不声称已经执行。\n\n"
        "知识库证据：\n"
        "用户问题：\n"
        "ping"
    )

    knowledge_service_url: str = (
        "http://localhost:8002"
    )

    # Knowledge 服务开启鉴权时（KNOWLEDGE_API_KEY），调用侧需发送同名 X-API-Key。
    # 留空表示 Knowledge 未开启鉴权。
    knowledge_api_key: str = ""

    # ============================================================
    # 对话记忆闭环（operator_memory，读写走 Java 内部接口）
    # ------------------------------------------------------------
    # ai-service 不直连数据库：召回/回写统一调 Java 的
    # /api/internal/memory/{recall,remember}，用内部 token 鉴权。
    # 未配置 token 时记忆链路整体降级为「不召回、不回写」并记日志，
    # 绝不影响对话本身。
    # ============================================================
    memory_enabled: bool = True
    memory_service_url: str = "http://localhost:8080"
    # 必须与 Java 的 SMARTOPS_INTERNAL_TOKEN 一致；留空 = 未配置。
    memory_internal_token: str = ""
    # 单轮最多注入几条历史记忆（与 Java 侧 20 的上限共同约束）。
    memory_recall_limit: int = 3
    # 内部接口超时（秒）：记忆是增强项，不能拖慢首 token。
    memory_timeout_sec: float = 2.0

    # SEC-01/SEC-02：Java 边缘签发的聊天 run 令牌校验密钥，必须与
    # SMARTOPS_CHAT_RUN_TOKEN_SECRET 一致。留空时不接受任何聊天请求（503），
    # 不会退回匿名可用的旧行为。
    chat_run_token_secret: str = ""

    # 仅本地/内网联调时显式打开；生产不得开启（等同放弃聊天鉴权）。
    chat_allow_anonymous: bool = False

    # GUARDRAIL v1（docs/design/llm-guardrail-v1）：对话内容护栏，全部
    # 为确定性规则（正则/解码/字符控制），不做 AI 语义判定（F10 红线）。
    # 总开关：False 时输入/输出检查全部放行，仅审计记录跳过事件。
    guard_enabled: bool = True
    # fail-closed：护栏自身异常时拒绝请求（默认 True），绝不静默放行。
    guard_fail_closed: bool = True
    # 流式滑动窗口截断（W4）。默认关闭：小模型流式截断有体验风险，
    # 离线验证后再显式打开。
    guard_stream_enabled: bool = False
    # 规则版本号：随规则表演进，写入审计 detail 以便追溯判定依据。
    guard_rule_version: str = "1.0.0"

    # ============================================================
    # TTS（本地神经语音合成：VoxCPM2 / F5-TTS）
    # ------------------------------------------------------------
    # 红线：依赖未安装 / 权重缺失 / 加载失败时，/api/tts/synthesize 返回 503
    # 并在 message 里写明原因；绝不返回占位音频，也不静默换成别的音色。
    # ============================================================
    # auto = 按 f5tts → edge → baidu → voxcpm2 → piperplus 顺序取第一个可用；
    # 也可强制 voxcpm2 / f5tts / edge / baidu / piperplus；none = 显式关闭（前端回落浏览器语音）。
    # piperplus 额外提供音素级时间戳（真口型），但音色固定，默认不抢占前排。
    # edge / baidu 是在线音源：无需本地权重，但需要联网；edge 在部分网络会被区域拦截。
    tts_provider: str = "auto"
    # auto / cuda / cpu。auto 在 torch 可用且 CUDA 可见时用 GPU，否则 CPU。
    tts_device: str = "auto"
    # 单次合成的文本上限（字符）。桌宠播报是短句，超长请求直接 400 而不是截断。
    tts_max_chars: int = 300
    # 单次合成超时（秒）。首次合成含模型加载，需留足时间。
    tts_timeout_sec: float = 120.0
    # VoxCPM2 权重目录：本地路径或 HuggingFace 仓库 id。留空 = 未配置（不可用）。
    tts_voxcpm_model_dir: str = ""
    # Piper-Plus（Piper 的 MIT 分支）模型 .onnx 路径：必须来自 piper-plus 自家 release
    # （上游 rhasspy/piper-voices 的中文模型是 espeak 音素类型，piper-plus 2.x 无法加载）。
    # 留空 = 未配置（不可用）；配置后可用 TTS_PROVIDER=piperplus 强制启用。
    tts_piper_model: str = ""
    # Piper-Plus 模型配置 json（含 phoneme_type / sample_rate / hop_size）。
    # 留空 = 自动找 <model>.json 或同目录 config.json。
    tts_piper_config: str = ""
    # F5-TTS 权重目录：留空 = 用 f5-tts 包内置默认权重（首次运行会联网下载）。
    tts_f5_model_dir: str = ""
    # F5-TTS 的 vocos 声码器本地目录（需含 config.yaml 与 pytorch_model.bin）。
    # 留空 = 首次合成时从 HF 的 charactr/vocos-mel-24khz 下载（国内直连常超时）。
    tts_f5_vocoder_dir: str = ""
    # 音色预设（JSON 对象）：name → {audio, text, description}，也允许简写 name → audio 路径。
    # audio 是参考音频（VoxCPM2 做音色克隆、F5-TTS 做参考声线），相对路径按仓库根解析。
    # 例：{"sweet_girl": {"audio": "assets/tts/sweet_girl.wav", "text": "参考音频的转写文本"}}
    tts_voice_presets: str = "{}"
    # Edge 神经语音音色：zh-CN-XiaoyiNeural（活泼少女）/ zh-CN-XiaoxiaoNeural（温柔）。
    # 仅 edge provider 生效；忽略 tts_voice_presets（在线音源不走参考音频克隆）。
    tts_edge_voice: str = "zh-CN-XiaoyiNeural"
    # Edge 朗读服务的客户端版本号（同时用于握手签名 Sec-MS-GEC-Version 与 User-Agent）。
    # 微软会周期性抬高门槛：版本过旧会被直接 403，升级方式就是改这一行（当前对应 edge-tts 7.3.1）。
    tts_edge_version: str = "143.0.3650.75"
    # 甜度档位（2026-11-16）：借鉴王者荣耀甜美少女英雄的**听感取向**，
    # 不是克隆其配音演员（演员声音属于真人表演，不可提取复用）。
    # 可调维度只有三个：音高上抬、语速偏移、可选情感风格。
    # pitch 上抬 18Hz ≈ 提高约两个半音，是最接近"少女音"的档位；
    # rate +10% 让语气更轻快（再快会显急促、咬字发飘）。
    tts_edge_pitch_hz: int = 18
    tts_edge_rate_percent: int = 10
    # mstts:express-as 情感风格（如 cheerful / affectionate）。留空 = 不启用：
    # 并非所有音色都支持风格，强加会导致整条 SSML 被服务端拒绝，故默认关闭。
    tts_edge_style: str = ""

    request_timeout: int = 30

    # PERF-02：上游连接的容量预算。连接本身由 lifespan 管理的共享 transport 复用，
    # 这里只声明上限与排队预算，避免"每个请求新建连接 + 无上限并发"。
    http_max_connections: int = 100

    http_max_keepalive_connections: int = 20

    http_max_concurrent_requests: int = 32

    http_queue_timeout: float = 2.0

    http_pool_timeout: float = 5.0

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()