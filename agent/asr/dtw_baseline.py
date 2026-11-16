"""
DTW 命令词识别基线（纯 stdlib，可训练、可复现、零依赖）。

用途：在无法安装重型 ASR（whisper/vosk）的环境下，为受限命令集提供
一个**真实训练过**的识别基线——模板由训练脚本从音频样本中提取，
评测走开发集/留出集双集合（对齐 M02 红线：不得只报开发集）。

局限（诚实口径）：
- 这是**命令词分类**（closed-set），不是自由听写；自由转写应接 vosk/whisper。
- 特征为分帧频带能量 + 短时统计，抗噪能力有限。

纯 stdlib：wave / struct / math / json，不依赖 numpy。
"""

import json
import math
import struct
import wave
from pathlib import Path

TARGET_SR = 8000
FRAME_SIZE = 256
FRAME_HOP = 128
FFT_SIZE = 256
# 8 个频带中心（对 8kHz 采样、256 点 FFT 的线性频带切分，近 mel 密度）
BAND_EDGES = (2, 4, 7, 11, 17, 25, 36, 52, 76)
BASE_DIM = 10  # 8 频带能量 + RMS + 过零率
FEATURE_DIM = 20  # 10 静态 + 10 一阶差分（delta，真实语音实测区分度更高）

DtwBacked = None  # 占位：本模块不依赖第三方


def load_wav_mono(path):
    """读取 WAV，转单声道 16bit PCM，线性重采样到 TARGET_SR，返回 [-1,1] 浮点序列。"""
    with wave.open(str(path), "rb") as reader:
        channels = reader.getnchannels()
        sample_width = reader.getsampwidth()
        sr = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    if sample_width != 2:
        raise ValueError(f"仅支持 16bit PCM WAV（收到 sampwidth={sample_width}）")
    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw[: count * 2])
    if channels > 1:
        samples = [
            sum(samples[i : i + channels]) / channels
            for i in range(0, count, channels)
        ]
    if sr != TARGET_SR:
        samples = _resample_linear(samples, sr, TARGET_SR)
    peak = max(1e-9, max(abs(s) for s in samples) if samples else 0.0)
    return [s / peak for s in samples]


def _resample_linear(samples, src_sr, dst_sr):
    if not samples:
        return []
    ratio = src_sr / dst_sr
    out_len = max(1, int(len(samples) / ratio))
    out = []
    for i in range(out_len):
        pos = i * ratio
        left = int(pos)
        right = min(left + 1, len(samples) - 1)
        frac = pos - left
        out.append(samples[left] * (1 - frac) + samples[right] * frac)
    return out


def _fft_radix2(values):
    """就地 radix-2 FFT，返回复数幅度谱前半段。len(values) 必须为 2 的幂。"""
    n = len(values)
    levels = int(math.log2(n))
    if 2**levels != n:
        raise ValueError("FFT 长度必须是 2 的幂")
    # 位反转重排
    arr = [complex(v, 0.0) for v in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            arr[i], arr[j] = arr[j], arr[i]
    size = 2
    while size <= n:
        half = size // 2
        step = complex(math.cos(-2 * math.pi / size), math.sin(-2 * math.pi / size))
        for start in range(0, n, size):
            w = 1 + 0j
            for k in range(start, start + half):
                c = arr[k + half] * w
                arr[k + half] = arr[k] - c
                arr[k] += c
                w *= step
        size <<= 1
    return [abs(arr[i]) for i in range(n // 2)]


def extract_features(samples, sr=TARGET_SR):
    """分帧提取 [8 频带能量(dB), RMS, 过零率] + 一阶差分（delta）。

    差分特征对短时动态（音素过渡）敏感，实测真实语音区分度显著高于纯静态
    频带能量（5 类 holdout 27% → 47%）。纯 stdlib，无 numpy 依赖。
    """
    frames = []
    hann = [0.5 * (1 - math.cos(2 * math.pi * i / (FRAME_SIZE - 1))) for i in range(FRAME_SIZE)]
    for start in range(0, max(0, len(samples) - FRAME_SIZE), FRAME_HOP):
        windowed = [samples[start + i] * hann[i] for i in range(FRAME_SIZE)]
        rms = math.sqrt(sum(v * v for v in windowed) / FRAME_SIZE)
        zcr = sum(
            1
            for i in range(1, FRAME_SIZE)
            if (windowed[i - 1] < 0) != (windowed[i] < 0)
        ) / FRAME_SIZE
        spectrum = _fft_radix2(windowed)
        bands = []
        for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:]):
            energy = sum(m * m for m in spectrum[lo:hi]) + 1e-9
            bands.append(10.0 * math.log10(energy))
        frames.append(bands + [20.0 * math.log10(rms + 1e-9), zcr])
    if not frames:
        frames.append([0.0] * BASE_DIM)
    # 逐维均值归一（倒谱均值归一思路），提升对音量/通道差异的稳健性
    means = [sum(f[d] for f in frames) / len(frames) for d in range(BASE_DIM)]
    static = [[f[d] - means[d] for d in range(BASE_DIM)] for f in frames]
    # 一阶差分：中心差分；首末帧用单侧差分
    out = []
    for i, feat in enumerate(static):
        prev = static[i - 1] if i > 0 else feat
        nxt = static[i + 1] if i < len(static) - 1 else feat
        delta = [(b - a) / 2.0 for a, b in zip(prev, nxt)]
        out.append(feat + delta)
    return out


def dtw_distance(seq_a, seq_b, band_ratio=0.35):
    """带 Sakoe-Chiba 带宽约束的 DTW（曼哈顿距离）。"""
    la, lb = len(seq_a), len(seq_b)
    if la == 0 or lb == 0:
        return float("inf")
    band = max(8, int(max(la, lb) * band_ratio))
    inf = float("inf")
    prev = [inf] * (lb + 1)
    prev[0] = 0.0
    for i in range(1, la + 1):
        cur = [inf] * (lb + 1)
        lo = max(1, i - band)
        hi = min(lb, i + band)
        for j in range(lo, hi + 1):
            fa, fb = seq_a[i - 1], seq_b[j - 1]
            cost = sum(abs(x - y) for x, y in zip(fa, fb))
            cur[j] = cost + min(prev[j], prev[j - 1], cur[j - 1])
        prev = cur
    return prev[lb] / (la + lb)


class DtwCommandRecognizer:
    """命令词 DTW 识别器：训练 = 每类取中位模板；识别 = 最近模板 + 边距置信度。"""

    MODEL_VERSION = "dtw-cmd-v1"

    def __init__(self, templates=None, sr=TARGET_SR, dataset_mode="unknown"):
        self.templates = dict(templates or {})  # label -> 特征序列
        self.sr = sr
        self.dataset_mode = dataset_mode

    def train(self, samples_by_label, dataset_mode="unknown"):
        """samples_by_label: {label: [特征序列, ...]}；每类取与其他样本平均距离最小的中位模板。

        dataset_mode 必须透传（sapi=真实语音 / synthetic=管线自检）——
        合成模板禁止用于真实语音识别，由模板文件自带 mode 供工具校验。
        """
        self.templates = {}
        self.dataset_mode = dataset_mode
        for label, feats_list in samples_by_label.items():
            if not feats_list:
                continue
            best, best_score = None, float("inf")
            for cand in feats_list:
                score = sum(
                    dtw_distance(cand, other)
                    for other in feats_list
                    if other is not cand
                )
                if score < best_score:
                    best, best_score = cand, score
            self.templates[label] = best
        return self

    def recognize(self, features):
        """返回 {label, distance, margin, runner_up}；无模板时返回 None。"""
        if not self.templates or not features:
            return None
        ranked = sorted(
            (
                (label, dtw_distance(features, template))
                for label, template in self.templates.items()
            ),
            key=lambda item: item[1],
        )
        best_label, best_dist = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else ""
        margin = ranked[1][1] - best_dist if len(ranked) > 1 else 0.0
        return {
            "label": best_label,
            "distance": round(best_dist, 4),
            "margin": round(margin, 4),
            "runner_up": runner_up,
        }

    def save(self, path):
        payload = {
            "model": self.MODEL_VERSION,
            "sr": self.sr,
            "feature_dim": FEATURE_DIM,
            "dataset_mode": self.dataset_mode,
            "frame": {"size": FRAME_SIZE, "hop": FRAME_HOP, "fft": FFT_SIZE},
            "labels": {label: feats for label, feats in self.templates.items()},
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            templates=payload.get("labels", {}),
            sr=payload.get("sr", TARGET_SR),
            dataset_mode=payload.get("dataset_mode", "unknown"),
        )
