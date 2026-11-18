"""Ollama 视觉推理调用。

弱标注（要框）与筛图（要二分类）走的是同一个 `/api/generate` 接口，
差别只在 prompt 与 num_predict，所以调用层抽出来共用一份，
避免两份 urllib 代码在超时/错误处理上慢慢跑偏。

`format=json` 只是请模型尽量只吐 JSON，3B 级模型仍会夹带解释文字，
解析与拒绝由各业务模块负责，这里不假装"结构化输出一定安全"。
"""

from __future__ import annotations

import json
import urllib.request


def call_vision(
    base_url: str,
    model: str,
    prompt: str,
    image_b64: str,
    timeout: float,
    num_predict: int = 512,
    temperature: float = 0.0,
) -> str:
    """返回模型的原始文本响应；网络/协议错误以异常抛出，由调用方按张记账。"""
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8", "replace"))
    if not isinstance(body, dict):
        raise RuntimeError("Ollama 返回非 JSON 对象")
    if body.get("error"):
        raise RuntimeError(f"Ollama 报错：{body['error']}")
    return str(body.get("response") or "")
