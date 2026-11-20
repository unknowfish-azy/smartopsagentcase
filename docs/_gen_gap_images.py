"""为 hardware-dependency-gaps.md 生成架构示意图。

使用 Trae text_to_image API，输出到 docs/hardware-gaps-assets/。

用法：python _gen_gap_images.py
"""
from __future__ import annotations
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"
SIZE = "landscape_16_9"
OUT_DIR = Path(__file__).parent / "hardware-gaps-assets"

FIGURES = [
    {
        "file": "fig1-scene-twin.png",
        "prompt": (
            "3D digital twin of an industrial factory warehouse interior, "
            "isometric dark tech blueprint style, robot patrol trajectory "
            "lines glowing cyan, conveyor belts and racks, top-down "
            "perspective, blue and cyan accent colors, schematic diagram "
            "aesthetic, not a real screenshot"
        ),
    },
    {
        "file": "fig2-gap-comparison.png",
        "prompt": (
            "Comparison diagram between scene-level digital twin and "
            "device-level digital twin, two side-by-side panels: left shows "
            "whole factory 3D scene, right shows individual robot device "
            "twin with detailed joints and sensors, arrows indicating the "
            "missing capability gap, dark tech infographic style, blue cyan "
            "palette, schematic diagram aesthetic, not a real screenshot"
        ),
    },
    {
        "file": "fig3-bandwidth-conflict.png",
        "prompt": (
            "Network bandwidth conflict diagram, BLE connection max 300kbps "
            "vs video stream requiring minimum 2Mbps, red warning zone in "
            "middle showing the hard conflict gap, spectrum visualization, "
            "bar chart comparison, dark tech cybersecurity style, red and "
            "cyan accent colors, schematic diagram aesthetic, not a real "
            "screenshot"
        ),
    },
]


def fetch_image(prompt: str) -> bytes:
    url = f"{API}?prompt={urllib.parse.quote(prompt)}&image_size={SIZE}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fig in FIGURES:
        dst = OUT_DIR / fig["file"]
        if dst.exists():
            print(f"skip (exists): {dst.name}")
            continue
        print(f"generating: {dst.name} ...")
        try:
            data = fetch_image(fig["prompt"])
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL: {exc}")
            return 1
        dst.write_bytes(data)
        print(f"  ✓ {dst.name}  ({len(data) // 1024} KB)")
        time.sleep(1)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
