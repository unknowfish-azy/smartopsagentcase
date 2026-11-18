# -*- coding: utf-8 -*-
"""把 storyboard + 录屏 + 旁白渲染成带标注的展示片。

依赖：ffmpeg/ffprobe（带 libass）、Pillow。
"""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from PIL import Image, ImageDraw


WORK = Path(".")
RAW = WORK / "raw"
VOICE = WORK / "voice" / "lines"
CARDS = WORK / "cards"
TMP = WORK / ".work"
SEGMENTS = TMP / "segments"
ASSETS = TMP / "assets"
SUBTITLES = TMP / "subtitles"
FRAMES = TMP / "frames"
FINAL_DIR = WORK / "final"
REPORT = FINAL_DIR / "render-report.json"
FINAL_OUTPUT = FINAL_DIR / "demo-video.mp4"
CAPTURE_EVENTS = WORK / "capture-events.json"

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
WIDTH, HEIGHT, FPS = 1920, 1080, 30
TEMPO = 1.5
SUBTITLE_LIMIT = 30
RED = (238, 62, 70, 255)


def run(command, *, cwd=None, timeout=3600):
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd or TMP),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            "命令执行失败：\n{}\n{}".format(
                " ".join(str(part) for part in command), result.stderr[-6000:]
            )
        )
    return result


def probe_duration(path):
    result = run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        timeout=120,
    )
    return float(result.stdout.strip())


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def clamp(value, low, high):
    return max(low, min(high, value))


def resolve(path, base):
    path = Path(path)
    return path if path.is_absolute() else (base / path)


def ass_time(seconds):
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"


def ass_text(text):
    return str(text).replace("{", "（").replace("}", "）").replace("\n", r"\N")


SUB_TOKEN = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.%_-")


def cut_allowed(text, cut):
    """英文词、版本号与文件名不能在中间断行。"""
    if cut <= 0 or cut >= len(text):
        return True
    return not (text[cut - 1] in SUB_TOKEN and text[cut] in SUB_TOKEN)


def wrap_subtitle(text, limit=None):
    limit = limit or SUBTITLE_LIMIT
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    lines = []
    remaining = text
    punctuation = "，。；：、！？,.!?;:"
    while len(remaining) > limit:
        lower = max(10, int(limit * 0.58))
        cuts = [index + 1 for index, char in enumerate(remaining[:limit])
                if char in punctuation and cut_allowed(remaining, index + 1)]
        cuts = [cut for cut in cuts if cut >= lower]
        if cuts:
            cut = cuts[-1]
        else:
            cut = limit
            while cut > lower and not cut_allowed(remaining, cut):
                cut -= 1
        lines.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        lines.append(remaining)
    return r"\N".join(lines)


def chinese_font():
    candidates = [
        (Path(r"C:\Windows\Fonts\msyh.ttc"), "Microsoft YaHei"),
        (Path(r"C:\Windows\Fonts\simhei.ttf"), "SimHei"),
        (Path(r"C:\Windows\Fonts\simsun.ttc"), "SimSun"),
        (Path(r"C:\Windows\Fonts\NotoSansCJK-Regular.ttc"), "Noto Sans CJK SC"),
        (Path("/System/Library/Fonts/PingFang.ttc"), "PingFang SC"),
        (Path("/System/Library/Fonts/STHeiti Medium.ttc"), "Heiti SC"),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), "Noto Sans CJK SC"),
        (Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"), "WenQuanYi Zen Hei"),
    ]
    for path, name in candidates:
        if path.exists():
            return name
    raise FileNotFoundError("未找到中文字体，请安装 Noto Sans CJK 或微软雅黑")


def ensure_base_assets():
    ASSETS.mkdir(parents=True, exist_ok=True)
    cursor_path = ASSETS / "cursor.png"
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    points = [(9, 5), (9, 43), (19, 34), (27, 54), (36, 50), (28, 31), (43, 30)]
    draw.polygon([(x + 3, y + 4) for x, y in points], fill=(0, 0, 0, 115))
    draw.polygon(points, fill=(255, 255, 255, 255), outline=(20, 27, 38, 255), width=3)
    draw.line([(13, 12), (13, 34), (20, 28)], fill=(216, 226, 238, 255), width=2)
    image.save(cursor_path)

    ring_path = ASSETS / "click-ring.png"
    image = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((14, 14, 166, 166), outline=(0, 0, 0, 125), width=14)
    draw.ellipse((14, 14, 166, 166), outline=RED, width=7)
    draw.ellipse((75, 75, 105, 105), fill=(238, 62, 70, 120))
    image.save(ring_path)
    return cursor_path, ring_path


def box_asset(shot_id, event_index, box):
    path = ASSETS / f"{shot_id}-box-{event_index:02d}.png"
    x, y, w, h = [float(value) for value in box]
    x = clamp(x, 3, WIDTH - 12)
    y = clamp(y, 3, HEIGHT - 12)
    w = clamp(w, 8, WIDTH - x - 4)
    h = clamp(h, 8, HEIGHT - y - 4)
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rect = (round(x), round(y), round(x + w), round(y + h))
    draw.rounded_rectangle(rect, radius=8, fill=(238, 62, 70, 16),
                           outline=(0, 0, 0, 145), width=11)
    draw.rounded_rectangle(rect, radius=8, outline=RED, width=5)
    corner = min(28, max(12, int(min(w, h) * 0.25)))
    for points in [
        ((x, y + corner), (x, y), (x + corner, y)),
        ((x + w - corner, y), (x + w, y), (x + w, y + corner)),
        ((x + w, y + h - corner), (x + w, y + h), (x + w - corner, y + h)),
        ((x + corner, y + h), (x, y + h), (x, y + h - corner)),
    ]:
        draw.line(points, fill=(255, 110, 112, 255), width=7, joint="curve")
    image.save(path)
    return path


def arrow_asset(shot_id, event_index, start, end):
    path = ASSETS / f"{shot_id}-arrow-{event_index:02d}.png"
    x1, y1 = [float(value) for value in start]
    x2, y2 = [float(value) for value in end]
    x1, y1 = clamp(x1, 12, WIDTH - 12), clamp(y1, 12, HEIGHT - 12)
    x2, y2 = clamp(x2, 12, WIDTH - 12), clamp(y2, 12, HEIGHT - 12)
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    angle = math.atan2(y2 - y1, x2 - x1)
    head = 36
    neck = (x2 - head * 0.72 * math.cos(angle), y2 - head * 0.72 * math.sin(angle))
    draw.line([(x1, y1), neck], fill=(0, 0, 0, 160), width=16)
    draw.line([(x1, y1), neck], fill=RED, width=8)
    draw.ellipse((x1 - 7, y1 - 7, x1 + 7, y1 + 7), fill=RED)
    left = (x2 - head * math.cos(angle + math.radians(29)),
            y2 - head * math.sin(angle + math.radians(29)))
    right = (x2 - head * math.cos(angle - math.radians(29)),
             y2 - head * math.sin(angle - math.radians(29)))
    draw.polygon([left, (x2, y2), right], fill=(0, 0, 0, 170))
    inner_head = 29
    left = (x2 - inner_head * math.cos(angle + math.radians(29)),
            y2 - inner_head * math.sin(angle + math.radians(29)))
    right = (x2 - inner_head * math.cos(angle - math.radians(29)),
             y2 - inner_head * math.sin(angle - math.radians(29)))
    draw.polygon([left, (x2, y2), right], fill=RED)
    image.save(path)
    return path


def label_position(event):
    kind = event["type"]
    if kind == "box":
        x, y, w, h = [float(value) for value in event["box"]]
        lx, ly = x, y - 48 if y > 160 else y + h + 12
    elif kind == "arrow":
        x1, y1 = event["from"]
        x2, y2 = event["to"]
        lx = (x1 + x2) / 2 - 70
        ly = min(y1, y2) - 52
        if ly < 132:
            ly = max(y1, y2) + 18
    else:
        x, y = event.get("to", event.get("from", (80, 200)))
        lx, ly = x + 24, y + 26 if y < 790 else y - 58
    return round(clamp(lx, 22, 1530)), round(clamp(ly, 126, 850))


def subtitle_obstacles(events):
    obstacles = []
    for event in events:
        kind = event.get("type")
        if kind == "box":
            x, y, w, h = event["box"]
            obstacles.append((x - 16, y - 16, x + w + 16, y + h + 16))
        elif kind == "arrow":
            x1, y1 = event["from"]
            x2, y2 = event["to"]
            obstacles.append((min(x1, x2) - 24, min(y1, y2) - 24,
                              max(x1, x2) + 24, max(y1, y2) + 24))
        elif kind in {"cursor", "click"} and event.get("to"):
            x, y = event["to"]
            obstacles.append((x - 65, y - 55, x + 65, y + 65))
    return obstacles


def subtitle_y(events, text):
    line_count = len(text.split(r"\N"))
    height = line_count * 58 + 28
    obstacles = subtitle_obstacles(events)
    best_y, best_score = 1016, float("inf")
    for y in (1016, 916, 816, 716):
        top, bottom = y - height, y - 10
        score = 0.0
        for x1, y1, x2, y2 in obstacles:
            overlap_y = max(0.0, min(bottom, y2) - max(top, y1))
            if overlap_y:
                overlap_x = max(0.0, min(1780, x2) - max(140, x1))
                score += overlap_x * overlap_y
        score += (1016 - y) * 0.5
        if score < best_score:
            best_y, best_score = y, score
        if score == 0:
            break
    return best_y


def build_ass(shot, events, duration, path):
    font = chinese_font()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},48,&H00FFFFFF,&H00FFFFFF,&H48000000,&H48000000,-1,0,0,0,100,100,0,0,3,11,0,2,120,120,34,1
Style: Chapter,{font},29,&H006DC6F2,&H006DC6F2,&H580B1520,&H580B1520,-1,0,0,0,100,100,0,0,3,7,0,7,30,30,24,1
Style: Overlay,{font},23,&H00FFFFFF,&H00FFFFFF,&H700B1520,&H700B1520,0,0,0,0,100,100,0,0,3,6,0,7,30,30,76,1
Style: Label,{font},26,&H00FFFFFF,&H00FFFFFF,&H18463EEE,&H18463EEE,-1,0,0,0,100,100,0,0,3,7,0,7,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    start, end = ass_time(0), ass_time(duration)
    chapter = shot.get("chapter", "")
    overlay = shot.get("overlay", "")
    if chapter:
        lines.append(
            f"Dialogue: 2,{start},{end},Chapter,,0,0,0,,"
            f"{{\\an7\\pos(34,24)\\fad(180,180)}}{ass_text(chapter)}\n"
        )
    if overlay:
        lines.append(
            f"Dialogue: 2,{start},{end},Overlay,,0,0,0,,"
            f"{{\\an7\\pos(36,76)\\fad(180,180)}}{ass_text(overlay)}\n"
        )
    wrapped = wrap_subtitle(shot.get("text", ""))
    y = subtitle_y(events, wrapped)
    lines.append(
        f"Dialogue: 1,{start},{end},Sub,,0,0,0,,"
        f"{{\\an2\\pos(960,{y})\\fad(140,180)}}{ass_text(wrapped)}\n"
    )

    cursor_labels = set()
    for event in events:
        kind = event.get("type")
        if kind not in {"box", "arrow", "cursor", "click"} or not event.get("label"):
            continue
        if kind == "click":
            nearby_cursor = any(
                other.get("type") == "cursor" and other.get("label") == event.get("label")
                and abs(float(other.get("end", -10)) - float(event.get("start", 0))) < 0.3
                for other in events
            )
            if nearby_cursor:
                continue
        event_start = clamp(float(event.get("start", 0)), 0, duration)
        event_end = clamp(float(event.get("end", duration)), 0, duration)
        if kind in {"cursor", "click"}:
            event_end = min(duration, max(event_end + 0.8, event_start + 1.0))
        if event_end <= event_start:
            continue
        key = (event.get("label"), round(event_start, 2))
        if kind == "cursor":
            if key in cursor_labels:
                continue
            cursor_labels.add(key)
        x, label_y = label_position(event)
        lines.append(
            f"Dialogue: 4,{ass_time(event_start)},{ass_time(event_end)},Label,,0,0,0,,"
            f"{{\\an7\\pos({x},{label_y})\\fad(140,160)}}{ass_text(event['label'])}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


def render_shot(shot, capture, muted, crf, preset, extract_frames=True):
    shot_id = shot["id"]
    route = shot.get("route")
    events = list(shot.get("events", []))
    if capture:
        events.extend(capture.get("events", []))
    events.sort(key=lambda item: float(item.get("start", 0)))
    visual_events = [event for event in events if event.get("type") != "warning"]
    warnings = [event for event in events if event.get("type") == "warning"]
    if capture and capture.get("error"):
        raise RuntimeError(f"{shot_id} 录屏失败，禁止进入合成：{capture['error']}")
    if warnings:
        raise RuntimeError(f"{shot_id} 仍有 {len(warnings)} 条标注定位警告，请先重录或修复")

    audio_path = resolve(shot["voice"], WORK) if shot.get("voice") else VOICE / f"{shot_id}.wav"
    use_voice = not muted and audio_path.is_file() and audio_path.stat().st_size > 0
    source_audio_duration = probe_duration(audio_path) if use_voice else None
    audio_duration = source_audio_duration / TEMPO if use_voice else None
    duration = float(shot.get("target", 8))
    if audio_duration is not None:
        duration = max(duration, audio_duration + 0.35)
    if visual_events:
        # 标注不能因为目标时长偏短被切掉。
        duration = max(duration, max(float(event.get("end", 0)) for event in visual_events) + 0.4)
    duration = round(duration, 3)

    if route:
        if not capture:
            raise FileNotFoundError(f"{shot_id} 缺少 capture-events.json 录制记录")
        source = Path(capture.get("video") or (RAW / f"{shot_id}.webm"))
        if not source.is_file():
            raise FileNotFoundError(f"{shot_id} 缺少录制视频：{source}")
        offset = float(capture.get("video_content_offset") or 0)
        inputs = ["-ss", f"{offset:.3f}", "-i", str(source)]
        input_kind = "page"
    elif shot.get("image"):
        source = resolve(shot["image"], WORK)
        if not source.is_file():
            raise FileNotFoundError(f"{shot_id} 缺少静帧：{source}")
        offset = None
        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(source)]
        input_kind = "image"
    else:
        source = CARDS / f"{shot_id}.png"
        if not source.is_file():
            raise FileNotFoundError(
                f"{shot_id} 缺少章节卡：{source}，请先运行 build_cards.py"
            )
        offset = None
        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(source)]
        input_kind = "card"

    input_count = 1
    cursor_path, ring_path = ensure_base_assets()
    filters = [
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={FPS},"
        f"tpad=stop_mode=clone:stop_duration={duration:.3f},trim=duration={duration:.3f},"
        "setpts=PTS-STARTPTS[base]"
    ]
    current = "base"
    overlay_number = 0

    def overlay_png(path, x, y, event_start, event_end, fade=True):
        nonlocal input_count, current, overlay_number
        index = input_count
        input_count += 1
        inputs.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(path)])
        fx = f"fx{overlay_number}"
        out = f"ov{overlay_number}"
        overlay_number += 1
        chain = f"[{index}:v]format=rgba"
        if fade:
            fade_out = max(event_start, event_end - 0.18)
            chain += (f",fade=t=in:st={event_start:.3f}:d=0.16:alpha=1,"
                      f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1")
        chain += f"[{fx}]"
        filters.append(chain)
        filters.append(
            f"[{current}][{fx}]overlay=x='{x}':y='{y}':"
            f"enable='between(t,{event_start:.3f},{event_end:.3f})':eof_action=pass[{out}]"
        )
        current = out

    cursors = [(index, event) for index, event in enumerate(visual_events)
               if event.get("type") == "cursor"]
    for position, (event_index, event) in enumerate(cursors):
        start = clamp(float(event["start"]), 0, duration)
        move_end = clamp(float(event["end"]), start + 0.001, duration)
        if start >= duration:
            continue
        next_start = duration
        if position + 1 < len(cursors):
            next_start = clamp(float(cursors[position + 1][1]["start"]), start, duration)
        related_clicks = [
            float(other["end"]) for other in visual_events
            if other.get("type") == "click"
            and float(other["start"]) >= start - 0.02
            and float(other["start"]) <= move_end + 0.25
        ]
        click_end = max(related_clicks, default=move_end)
        hold_end = min(next_start - 0.001 if next_start < duration else duration,
                       max(move_end + 1.5, click_end + 0.9))
        hold_end = clamp(hold_end, move_end, duration)
        from_x, from_y = [float(value) for value in event["from"]]
        to_x, to_y = [float(value) for value in event["to"]]
        progress = f"min(max((t-{start:.3f})/{max(0.001, move_end-start):.3f},0),1)"
        eased = f"({progress})*({progress})*(3-2*({progress}))"
        x = f"{from_x - 9:.2f}+({to_x-from_x:.2f})*{eased}"
        y = f"{from_y - 5:.2f}+({to_y-from_y:.2f})*{eased}"
        overlay_png(cursor_path, x, y, start, hold_end, fade=False)

    for event_index, event in enumerate(visual_events):
        kind = event.get("type")
        if kind not in {"box", "arrow", "click"}:
            continue
        start = clamp(float(event.get("start", 0)), 0, duration)
        end = clamp(float(event.get("end", duration)), 0, duration)
        if end <= start:
            continue
        if kind == "box":
            path = box_asset(shot_id, event_index, event["box"])
            overlay_png(path, 0, 0, start, end)
        elif kind == "arrow":
            path = arrow_asset(shot_id, event_index, event["from"], event["to"])
            overlay_png(path, 0, 0, start, end)
        elif kind == "click":
            x, y = [float(value) for value in event["to"]]
            ring_duration = min(0.72, duration - start)
            if ring_duration <= 0:
                continue
            index = input_count
            input_count += 1
            inputs.extend(["-loop", "1", "-framerate", str(FPS), "-i", str(ring_path)])
            fx = f"fx{overlay_number}"
            out = f"ov{overlay_number}"
            overlay_number += 1
            growth = f"min(max((t-{start:.3f})/{ring_duration:.3f},0),1)"
            size = f"trunc((28+132*{growth})/2)*2"
            filters.append(
                f"[{index}:v]format=rgba,scale=w='{size}':h='{size}':eval=frame,"
                f"fade=t=in:st={start:.3f}:d=0.05:alpha=1,"
                f"fade=t=out:st={start + min(0.18, ring_duration * 0.3):.3f}:"
                f"d={max(0.08, ring_duration - min(0.18, ring_duration * 0.3)):.3f}:alpha=1[{fx}]"
            )
            filters.append(
                f"[{current}][{fx}]overlay=x='{x:.2f}-overlay_w/2':y='{y:.2f}-overlay_h/2':"
                f"enable='between(t,{start:.3f},{start + ring_duration:.3f})':eof_action=pass[{out}]"
            )
            current = out

    ass_path = SUBTITLES / f"{shot_id}.ass"
    build_ass(shot, visual_events, duration, ass_path)
    if input_kind in {"card", "image"}:
        filters.append(
            f"[{current}]ass=subtitles/{shot_id}.ass,"
            f"fade=t=in:st=0:d=0.18,fade=t=out:st={max(0, duration-0.22):.3f}:d=0.22,"
            "format=yuv420p[vout]"
        )
    else:
        # 真实页面之间用硬切，避免每镜一次压黑打断观看节奏。
        filters.append(f"[{current}]ass=subtitles/{shot_id}.ass,format=yuv420p[vout]")

    audio_index = input_count
    if use_voice:
        inputs.extend(["-i", str(audio_path)])
        audio_mode = "voice"
    else:
        inputs.extend(["-f", "lavfi", "-t", f"{duration:.3f}",
                       "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        audio_mode = "muted" if muted else "silent-missing-voice"
    tempo_filter = f"atempo={TEMPO}," if use_voice else ""
    filters.append(
        f"[{audio_index}:a]{tempo_filter}aresample=48000,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d=0.04,afade=t=out:st={max(0, duration-0.08):.3f}:d=0.08[aout]"
    )

    output = SEGMENTS / f"{shot_id}.mp4"
    command = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin"]
    command.extend(inputs)
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-frames:v", str(round(duration * FPS)), "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(output),
    ])
    print(f"[{shot_id}] 渲染 {duration:.3f}s，输入偏移 "
          f"{offset if offset is not None else '静帧/卡片'}", flush=True)
    run(command)

    frames = {}
    if extract_frames:
        click_times = [float(event["start"]) + 0.24 for event in visual_events
                       if event.get("type") == "click"]
        frame_times = {
            "early": min(1.2, duration * 0.12),
            "click": click_times[0] if click_times else duration * 0.35,
            "mid": duration / 2,
            "late": max(0.0, duration - 0.8),
        }
        for label, frame_time in frame_times.items():
            frame = FRAMES / f"{shot_id}_{label}.png"
            run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-ss", f"{clamp(frame_time, 0, max(0, duration - 0.05)):.3f}",
                 "-i", str(output), "-frames:v", "1", str(frame)], timeout=120)
            frames[label] = str(frame)

    return {
        "id": shot_id,
        "kind": input_kind,
        "input": str(source),
        "video_content_offset": offset,
        "content_seconds": capture.get("content_seconds") if capture else None,
        "target_seconds": float(shot.get("target", 8)),
        "duration": probe_duration(output),
        "audio_input": str(audio_path) if use_voice else None,
        "source_audio_duration": source_audio_duration,
        "audio_duration": audio_duration,
        "voice_tempo": TEMPO if use_voice else None,
        "audio_mode": audio_mode,
        "event_count": len(events),
        "visual_event_count": len(visual_events),
        "warning_count": len(warnings),
        "warnings": [event.get("message", "") for event in warnings],
        "output": str(output),
        "frames": frames,
        "midframe": frames.get("mid"),
    }


def write_report(records, selected, muted, project, final=None):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "project": project,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "tempo": TEMPO,
        "selected": selected,
        "muted": muted,
        "shots": records,
        "final": final,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def concat_final(shots, records):
    by_id = {record["id"]: record for record in records}
    missing = [shot["id"] for shot in shots if shot["id"] not in by_id]
    if missing:
        raise RuntimeError("最终拼接缺少分段：" + ", ".join(missing))
    concat_file = TMP / "concat.txt"
    concat_file.write_text("".join(
        "file '{}'\n".format((SEGMENTS / f"{shot['id']}.mp4").as_posix())
        for shot in shots
    ), encoding="utf-8")
    has_voice = any(record.get("audio_mode") == "voice" for record in records)
    command = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "concat", "-safe", "0", "-i", str(concat_file),
               "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy"]
    if has_voice:
        command.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"])
    else:
        command.extend(["-c:a", "copy"])
    command.extend(["-movflags", "+faststart", str(FINAL_OUTPUT)])
    run(command, timeout=7200)
    return {
        "output": str(FINAL_OUTPUT),
        "duration": probe_duration(FINAL_OUTPUT),
        "shot_count": len(shots),
        "loudnorm": "I=-16,TP=-1.5,LRA=11" if has_voice else "not-applied-silent",
    }


def configure(args):
    global WORK, RAW, VOICE, CARDS, TMP, SEGMENTS, ASSETS, SUBTITLES, FRAMES
    global FINAL_DIR, REPORT, FINAL_OUTPUT, CAPTURE_EVENTS
    global WIDTH, HEIGHT, FPS, TEMPO, SUBTITLE_LIMIT

    storyboard_path = Path(args.storyboard).resolve()
    WORK = Path(args.work).resolve() if args.work else storyboard_path.parent
    RAW = Path(args.raw).resolve() if args.raw else WORK / "raw"
    VOICE = Path(args.voice).resolve() if args.voice else WORK / "voice" / "lines"
    CARDS = Path(args.cards).resolve() if args.cards else WORK / "cards"
    TMP = Path(args.tmp).resolve() if args.tmp else WORK / ".work"
    SEGMENTS = TMP / "segments"
    ASSETS = TMP / "assets"
    SUBTITLES = TMP / "subtitles"
    FRAMES = TMP / "frames"
    FINAL_DIR = Path(args.final_dir).resolve() if args.final_dir else WORK / "final"
    REPORT = FINAL_DIR / "render-report.json"
    CAPTURE_EVENTS = (Path(args.capture_events).resolve()
                      if args.capture_events else WORK / "capture-events.json")

    meta = load_json(storyboard_path).get("meta", {})
    if args.width and args.height:
        WIDTH, HEIGHT = args.width, args.height
    else:
        resolution = str(meta.get("resolution", "1920x1080")).lower()
        try:
            width, height = resolution.split("x")
            WIDTH, HEIGHT = int(width), int(height)
        except ValueError:
            WIDTH, HEIGHT = 1920, 1080
    FPS = args.fps or int(meta.get("fps", 30))
    TEMPO = args.tempo or float(meta.get("voice_tempo", 1.5))
    SUBTITLE_LIMIT = args.subtitle_limit or int(meta.get("subtitle_limit", 30))

    name = args.out or meta.get("output_name") or "demo-video.mp4"
    FINAL_OUTPUT = Path(name) if Path(name).is_absolute() else FINAL_DIR / name
    return storyboard_path, meta


def main():
    parser = argparse.ArgumentParser(description="展示片后期合成器：红框/箭头/鼠标/点击环/字幕/响度")
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--work", help="工作目录，默认 storyboard 所在目录")
    parser.add_argument("--raw", help="原始录屏目录，默认 <work>/raw")
    parser.add_argument("--voice", help="旁白目录，默认 <work>/voice/lines")
    parser.add_argument("--cards", help="章节卡目录，默认 <work>/cards")
    parser.add_argument("--tmp", help="临时目录，默认 <work>/.work")
    parser.add_argument("--final-dir", help="成片目录，默认 <work>/final")
    parser.add_argument("--capture-events", help="录制事件文件，默认 <work>/capture-events.json")
    parser.add_argument("--out", help="成片文件名或绝对路径；默认 meta.output_name")
    parser.add_argument("--only", help="逗号分隔的镜头编号，例如 S02B,S02C")
    parser.add_argument("--final", action="store_true", help="按 storyboard 顺序渲染并拼接全片")
    parser.add_argument("--muted", action="store_true", help="忽略旁白，生成静音轨")
    parser.add_argument("--tempo", type=float, help="旁白提速倍数，默认 meta.voice_tempo 或 1.5")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="fast")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--fps", type=int)
    parser.add_argument("--subtitle-limit", type=int, help="字幕每行最大字数，默认 30")
    parser.add_argument("--no-frames", action="store_true", help="不抽取每镜验收帧")
    args = parser.parse_args()

    if args.final and args.only:
        parser.error("--final 已包含全部镜头，请勿同时指定 --only")

    storyboard_path, meta = configure(args)
    FINAL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for directory in (TMP, SEGMENTS, ASSETS, SUBTITLES, FRAMES, FINAL_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    if not shutil.which(FFMPEG) or not shutil.which(FFPROBE):
        raise RuntimeError("PATH 中未找到 ffmpeg/ffprobe")

    storyboard = load_json(storyboard_path)
    shots = storyboard["shots"]
    capture_list = load_json(CAPTURE_EVENTS) if CAPTURE_EVENTS.exists() else []
    captures = {entry["id"]: entry for entry in capture_list}
    if args.only:
        selected_ids = [item.strip() for item in args.only.split(",") if item.strip()]
        known = {shot["id"] for shot in shots}
        unknown = [shot_id for shot_id in selected_ids if shot_id not in known]
        if unknown:
            parser.error("未知镜头：" + ", ".join(unknown))
        selected_set = set(selected_ids)
        selected_shots = [shot for shot in shots if shot["id"] in selected_set]
    else:
        selected_shots = shots
    if not selected_shots:
        parser.error("没有选中镜头")

    project = meta.get("project", "")
    records = []
    for shot in selected_shots:
        records.append(render_shot(
            shot, captures.get(shot["id"]), args.muted,
            args.crf, args.preset, extract_frames=not args.no_frames,
        ))
        write_report(records, [item["id"] for item in selected_shots], args.muted, project)
        print(f"[{shot['id']}] 完成：{records[-1]['output']}", flush=True)

    if args.final:
        final = concat_final(shots, records)
        write_report(records, [shot["id"] for shot in shots], args.muted, project, final)
        print(f"成片：{FINAL_OUTPUT}", flush=True)
    print(f"报告：{REPORT}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"合成失败：{exc}", file=sys.stderr)
        raise
