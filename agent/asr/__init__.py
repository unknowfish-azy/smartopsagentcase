"""
ASR（语音识别）可插拔栈。

设计口径（对齐 fact-sheet「确定性基线 + 可插拔接口」）：
- 优先使用已安装的真实 ASR 后端（vosk / faster-whisper / whisper）；
- 其次使用本仓内置的 DTW 命令词基线（纯 stdlib 训练型模型，见 dtw_baseline）；
- 全部不可用时**确定性降级**：不伪造转写文本，返回结构化说明。

红线：任何路径都不得编造识别结果。
"""

from .dtw_baseline import (
    DtwCommandRecognizer,
    dtw_distance,
    extract_features,
    load_wav_mono,
)

__all__ = [
    "DtwCommandRecognizer",
    "dtw_distance",
    "extract_features",
    "load_wav_mono",
]
