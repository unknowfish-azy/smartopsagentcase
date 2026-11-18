# -*- coding: utf-8 -*-
"""成片验收：规格、响度、分段、抽帧与联系表。"""

import argparse
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def run(command):
    return subprocess.run([str(part) for part in command],
                          stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def probe(path):
    result = run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
                  "-show_entries", "format=duration,size,bit_rate",
                  "-of", "json", path])
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    data = json.loads(result.stdout)
    video = next((item for item in data["streams"] if item["codec_type"] == "video"), {})
    audio = next((item for item in data["streams"] if item["codec_type"] == "audio"), {})
    rate = video.get("r_frame_rate", "0/1")
    numerator, denominator = rate.split("/")
    fps = float(numerator) / float(denominator or 1)
    return {
        "duration": float(data["format"]["duration"]),
        "size_mb": round(float(data["format"]["size"]) / 1024 / 1024, 2),
        "bit_rate": int(data["format"].get("bit_rate", 0)),
        "video": video,
        "audio": audio,
        "fps": round(fps, 2),
    }


def loudness(path):
    result = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                  "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                  "-f", "null", "-"])
    text = result.stderr
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def font(size):
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def contact_sheet(frames, out, columns=6, width=320):
    if not frames:
        return None
    rows = (len(frames) + columns - 1) // columns
    thumb_height = round(width * 9 / 16)
    sheet = Image.new("RGB", (columns * width, rows * (thumb_height + 26)), (8, 12, 22))
    draw = ImageDraw.Draw(sheet)
    label_font = font(18)
    for index, (shot_id, path) in enumerate(frames):
        try:
            image = Image.open(path).convert("RGB").resize((width, thumb_height))
        except Exception:
            continue
        x = (index % columns) * width
        y = (index // columns) * (thumb_height + 26)
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + thumb_height + 2), shot_id, font=label_font,
                  fill=(226, 232, 240))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out


def main():
    parser = argparse.ArgumentParser(description="展示片验收")
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--work", help="工作目录，默认 storyboard 所在目录")
    parser.add_argument("--final", help="成片路径；默认 <work>/final/<meta.output_name>")
    parser.add_argument("--report", help="输出 qc-report.json 的路径")
    parser.add_argument("--skip-loudness", action="store_true")
    parser.add_argument("--require-voice", action="store_true",
                        help="缺少旁白视为错误；默认只告警")
    args = parser.parse_args()

    storyboard_path = Path(args.storyboard).resolve()
    storyboard = load_json(storyboard_path)
    meta = storyboard.get("meta", {})
    work = Path(args.work).resolve() if args.work else storyboard_path.parent
    final = Path(args.final).resolve() if args.final else (
        work / "final" / (meta.get("output_name") or "demo-video.mp4"))
    report_path = (Path(args.report).resolve() if args.report
                   else work / "qc" / "qc-report.json")

    errors, warnings, info = [], [], {}
    if not final.is_file():
        errors.append(f"成片不存在：{final}")
        data = {}
    else:
        data = probe(final)
        info["final"] = str(final)
        info["probe"] = data
        resolution = str(meta.get("resolution", "1920x1080")).lower()
        try:
            expected_width, expected_height = [int(part) for part in resolution.split("x")]
        except ValueError:
            expected_width, expected_height = 1920, 1080
        if data["video"].get("width") != expected_width or data["video"].get("height") != expected_height:
            errors.append(f"分辨率 {data['video'].get('width')}x{data['video'].get('height')} "
                          f"不等于 {expected_width}x{expected_height}")
        expected_fps = float(meta.get("fps", 30))
        if abs(data["fps"] - expected_fps) > 0.2:
            errors.append(f"帧率 {data['fps']} 不等于 {expected_fps}")
        target = meta.get("target_seconds")
        if target:
            tolerance = max(20.0, float(target) * 0.15)
            if abs(data["duration"] - float(target)) > tolerance:
                warnings.append(f"成片时长 {data['duration']:.1f}s 与目标 "
                                f"{float(target):.1f}s 相差超过 {tolerance:.0f}s")
        if not data["audio"]:
            errors.append("成片没有音频轨")

        if not args.skip_loudness and data["audio"]:
            measured = loudness(final)
            if not measured:
                warnings.append("未能读取 loudnorm 结果")
            else:
                info["loudness"] = measured
                input_i = float(measured.get("input_i", 0))
                input_tp = float(measured.get("input_tp", 0))
                if input_i < -18 or input_i > -14:
                    warnings.append(f"整片响度 {input_i} LUFS，建议 -18 到 -14")
                if input_tp > -1.0:
                    warnings.append(f"真峰值 {input_tp} dBTP，建议不高于 -1.0")

    render_report_path = work / "final" / "render-report.json"
    render = None
    if render_report_path.exists():
        render = load_json(render_report_path)
        shots = render.get("shots", [])
        info["render_report"] = str(render_report_path)
        info["shot_count"] = len(shots)
        warning_shots = [shot["id"] for shot in shots if shot.get("warning_count")]
        if warning_shots:
            errors.append("标注定位警告未清零：" + ", ".join(warning_shots))
        missing_voice = [shot["id"] for shot in shots
                         if shot.get("audio_mode") == "silent-missing-voice"]
        if missing_voice:
            message = "缺少旁白：" + ", ".join(missing_voice)
            (errors if args.require_voice else warnings).append(message)
        expected_ids = [shot["id"] for shot in storyboard["shots"]]
        rendered_ids = {shot["id"] for shot in shots}
        absent = [shot_id for shot_id in expected_ids if shot_id not in rendered_ids]
        if absent:
            warnings.append("storyboard 中未渲染的镜头：" + ", ".join(absent))
        frames = []
        for shot in shots:
            mid = shot.get("midframe") or (shot.get("frames") or {}).get("mid")
            if mid and Path(mid).exists():
                frames.append((shot["id"], mid))
            else:
                warnings.append(f"{shot['id']} 缺少 mid 抽帧")
        sheet = contact_sheet(frames, work / "qc" / "contact-sheet.jpg")
        if sheet:
            info["contact_sheet"] = str(sheet)
    else:
        warnings.append(f"未找到 render-report.json：{render_report_path}")

    verdict = "FAIL" if errors else ("WARN" if warnings else "PASS")
    result = {
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"验收：{verdict}")
    for message in errors:
        print(f"  ERROR {message}")
    for message in warnings:
        print(f"  WARN  {message}")
    if data:
        print(f"  成片 {data['duration']:.2f}s，{data['video'].get('width')}x"
              f"{data['video'].get('height')} @ {data['fps']}fps，{data['size_mb']} MB")
    print(f"报告：{report_path}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
