# -*- coding: utf-8 -*-
"""按 storyboard 生成深色科技风章节卡。"""

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
]

BG_TOP = (7, 11, 22)
BG_BOTTOM = (16, 26, 46)
ACCENT = (238, 62, 70)
CYAN = (56, 189, 248)
TEXT = (226, 232, 240)
MUTED = (148, 163, 184)


def find_font():
    for path in FONT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("未找到中文字体，请安装 Noto Sans CJK 或微软雅黑")


def font(size):
    return ImageFont.truetype(str(find_font()), size)


def gradient(width, height):
    image = Image.new("RGB", (width, height), BG_TOP)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(BG_TOP, BG_BOTTOM))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def wrap(text, draw, text_font, max_width):
    lines, current = [], ""
    for char in str(text):
        trial = current + char
        if draw.textlength(trial, font=text_font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def chapter_parts(chapter, index):
    match = re.match(r"\s*(\d+)\s*(.*)", chapter or "")
    if match:
        return match.group(1), match.group(2).strip()
    return f"{index:02d}", (chapter or "").strip()


def card_points(shot):
    points = shot.get("card_points")
    if isinstance(points, list) and points:
        return [str(item) for item in points][:4]
    visual = shot.get("visual", "")
    parts = [item.strip() for item in re.split(r"[、，,；;]", visual) if item.strip()]
    return [item for item in parts if len(item) <= 18][:4]


def draw_card(shot, meta, index, width, height, out):
    image = gradient(width, height).convert("RGBA")
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    for x in range(0, width, 96):
        draw.line([(x, 0), (x, height)], fill=(56, 189, 248, 16), width=1)
    for y in range(0, height, 96):
        draw.line([(0, y), (width, y)], fill=(56, 189, 248, 16), width=1)

    number, title = chapter_parts(shot.get("chapter", ""), index + 1)
    title = shot.get("card_title") or title or meta.get("title", "")
    subtitle = shot.get("card_subtitle") or shot.get("overlay") or meta.get("title", "")
    points = card_points(shot)

    draw.line([(120, 150), (120, height - 180)], fill=ACCENT, width=4)
    draw.text((96, 118), number, font=font(180), fill=(238, 62, 70, 46))

    title_font = font(66)
    y = 300
    for line in wrap(title, draw, title_font, width - 320)[:2]:
        draw.text((160, y), line, font=title_font, fill=TEXT)
        y += 86

    subtitle_font = font(32)
    y += 20
    for line in wrap(subtitle, draw, subtitle_font, width - 360)[:2]:
        draw.text((164, y), line, font=subtitle_font, fill=MUTED)
        y += 46

    y += 40
    point_font = font(36)
    for item in points:
        draw.rectangle([(166, y + 15), (180, y + 29)], fill=ACCENT)
        draw.text((202, y), item, font=point_font, fill=(203, 213, 225))
        y += 62

    footer = f"{meta.get('project', '')}　{meta.get('title', '')}".strip()
    draw.text((120, height - 92), footer, font=font(26), fill=(120, 138, 160))

    corner = 46
    for points_line in [
        [(52, 52 + corner), (52, 52), (52 + corner, 52)],
        [(width - 52 - corner, 52), (width - 52, 52), (width - 52, 52 + corner)],
        [(width - 52, height - 52 - corner), (width - 52, height - 52),
         (width - 52 - corner, height - 52)],
        [(52 + corner, height - 52), (52, height - 52), (52, height - 52 - corner)],
    ]:
        draw.line(points_line, fill=(238, 62, 70, 190), width=3)

    Image.alpha_composite(image, layer).convert("RGB").save(out, quality=95)


def main():
    parser = argparse.ArgumentParser(description="生成章节卡 PNG")
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--out", help="输出目录，默认 <work>/cards")
    parser.add_argument("--only", help="逗号分隔的镜头编号")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--all", action="store_true", help="连有 route 的镜头也生成卡片")
    args = parser.parse_args()

    storyboard_path = Path(args.storyboard).resolve()
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8-sig"))
    meta = storyboard.get("meta", {})
    shots = storyboard["shots"]
    out_dir = Path(args.out).resolve() if args.out else storyboard_path.parent / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    only = {item.strip() for item in args.only.split(",")} if args.only else None

    width, height = args.width or 1920, args.height or 1080
    if args.width is None and args.height is None:
        resolution = str(meta.get("resolution", "1920x1080")).lower()
        try:
            width, height = [int(part) for part in resolution.split("x")]
        except ValueError:
            pass

    count = 0
    for index, shot in enumerate(shots):
        if only and shot["id"] not in only:
            continue
        if shot.get("route") and not args.all and not shot.get("card_title"):
            continue
        out = out_dir / f"{shot['id']}.png"
        draw_card(shot, meta, index, width, height, out)
        print(f"卡片：{out}", flush=True)
        count += 1
    print(f"完成 {count} 张章节卡", flush=True)


if __name__ == "__main__":
    main()
