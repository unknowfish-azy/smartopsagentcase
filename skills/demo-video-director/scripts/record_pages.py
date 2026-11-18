# -*- coding: utf-8 -*-
"""用 Playwright 逐镜录制真实页面，并记录鼠标/点击/框选/箭头时间线。"""

import argparse
import json
import time
from pathlib import Path


def now():
    return time.monotonic()


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def center(box, padding=0):
    return [
        round(box["x"] + box["width"] / 2, 1),
        round(box["y"] + box["height"] / 2, 1),
    ]


def box_rect(box, padding=0):
    return [
        round(box["x"] - padding, 1),
        round(box["y"] - padding, 1),
        round(box["width"] + padding * 2, 1),
        round(box["height"] + padding * 2, 1),
    ]


class Recorder:
    def __init__(self, page, timeout, width, height):
        self.page = page
        self.timeout = timeout
        self.width = width
        self.height = height
        self.prev = [round(width * 0.8), round(height * 0.82)]
        self.events = []

    def locator(self, selector):
        return self.page.locator(selector).first

    def point(self, action):
        if action.get("to"):
            return [float(action["to"][0]), float(action["to"][1])]
        selector = action.get("selector") or action.get("to_selector")
        if not selector:
            raise ValueError(f"动作缺少 selector/to：{action}")
        locator = self.locator(selector)
        locator.scroll_into_view_if_needed(timeout=self.timeout)
        self.page.wait_for_timeout(150)
        locator.wait_for(state="visible", timeout=self.timeout)
        return center(locator.bounding_box() or {})

    def move_cursor(self, target, label, duration=0.45):
        start = now()
        self.page.mouse.move(self.prev[0], self.prev[1])
        self.page.mouse.move(target[0], target[1], steps=18)
        end = start + duration
        self.events.append({
            "type": "cursor",
            "start": round(start, 3),
            "end": round(end, 3),
            "from": list(self.prev),
            "to": list(target),
            "click": False,
            "label": label,
        })
        time.sleep(duration)
        self.prev = list(target)

    def click(self, action):
        target = self.point(action)
        label = action.get("label", "点击")
        self.move_cursor(target, label, float(action.get("move", 0.4)))
        start = now()
        self.page.mouse.click(target[0], target[1])
        self.events.append({
            "type": "click",
            "start": round(start, 3),
            "end": round(start + 0.55, 3),
            "to": list(target),
            "label": label,
        })
        time.sleep(float(action.get("hold", 0.45)))

    def type_text(self, action):
        target = self.point(action)
        label = action.get("label", "输入")
        self.move_cursor(target, label, float(action.get("move", 0.35)))
        selector = action.get("selector") or action.get("to_selector")
        if not selector:
            raise ValueError("type 动作需要 selector")
        locator = self.locator(selector)
        locator.click()
        locator.fill("")
        start = now()
        self.page.keyboard.type(str(action.get("text", "")),
                                delay=int(action.get("delay", 40)))
        self.events.append({
            "type": "cursor",
            "start": round(start, 3),
            "end": round(now(), 3),
            "from": list(target),
            "to": list(target),
            "click": False,
            "label": label,
        })
        time.sleep(float(action.get("hold", 0.3)))

    def run(self, action):
        kind = action.get("action")
        if kind == "click":
            self.click(action)
        elif kind == "type":
            self.type_text(action)
        elif kind == "hover":
            target = self.point(action)
            self.move_cursor(target, action.get("label", "悬停"),
                             float(action.get("move", 0.4)))
            self.locator(action.get("selector")).hover()
        elif kind == "move":
            target = self.point(action)
            self.move_cursor(target, action.get("label", "移动"),
                             float(action.get("move", 0.4)))
        elif kind == "scroll":
            if action.get("selector"):
                self.locator(action["selector"]).scroll_into_view_if_needed()
            self.page.mouse.wheel(0, float(action.get("dy", 600)))
            time.sleep(float(action.get("seconds", 0.4)))
        elif kind == "wait":
            time.sleep(float(action.get("seconds", 1)))
        elif kind == "press":
            self.page.keyboard.press(action.get("key", "Enter"))
            time.sleep(float(action.get("seconds", 0.3)))
        elif kind in {"box", "arrow"}:
            self.annotate(kind, action)
        elif kind == "wait_for":
            self.locator(action.get("selector")).wait_for(
                state=action.get("state", "visible"), timeout=self.timeout)
        else:
            raise ValueError(f"不支持的动作：{kind}")

    def annotate(self, kind, action):
        start = now()
        seconds = float(action.get("seconds", 3))
        if kind == "box":
            selector = action.get("selector")
            if not selector:
                raise ValueError("box 动作缺少 selector")
            locator = self.locator(selector)
            locator.scroll_into_view_if_needed(timeout=self.timeout)
            self.page.wait_for_timeout(150)
            locator.wait_for(state="visible", timeout=self.timeout)
            rect = box_rect(locator.bounding_box() or {},
                            float(action.get("padding", 10)))
            self.events.append({
                "type": "box",
                "start": round(start, 3),
                "end": round(start + seconds, 3),
                "box": rect,
                "label": action.get("label", "重点"),
            })
        else:
            start_point = self.point({"to": action.get("from"),
                                      "selector": action.get("from_selector")})
            end_point = self.point({"to": action.get("to"),
                                    "selector": action.get("to_selector")})
            self.events.append({
                "type": "arrow",
                "start": round(start, 3),
                "end": round(start + seconds, 3),
                "from": start_point,
                "to": end_point,
                "label": action.get("label", "指向"),
            })
        time.sleep(seconds)


def merge_events(path, entry):
    rows = load_json(path) if path.exists() else []
    rows = [row for row in rows if row.get("id") != entry["id"]]
    rows.append(entry)
    rows.sort(key=lambda row: row["id"])
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="逐镜录制页面并生成 capture-events.json")
    parser.add_argument("--storyboard", default="storyboard.json")
    parser.add_argument("--base-url", required=True, help="例如 http://localhost:5173")
    parser.add_argument("--out", default="capture-events.json")
    parser.add_argument("--only", help="逗号分隔的镜头编号")
    parser.add_argument("--storage-state", help="登录态 JSON；存在则复用，登录后也会写回")
    parser.add_argument("--headed", action="store_true", help="显示浏览器")
    parser.add_argument("--login-wait", type=int, default=0,
                        help="打开页面后等待多少秒供手动登录")
    parser.add_argument("--lead-in", type=float, default=1.2, help="页面稳定后到第一个动作的静止秒数")
    parser.add_argument("--tail", type=float, default=1.0, help="最后一个动作后保留的秒数")
    parser.add_argument("--offset-bias", type=float, default=-0.3,
                        help="视频内容偏移修正；越负越早切，默认 -0.3")
    parser.add_argument("--timeout", type=int, default=15000, help="元素等待超时毫秒")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("缺少 playwright：pip install playwright && playwright install chromium")

    storyboard_path = Path(args.storyboard).resolve()
    storyboard = load_json(storyboard_path)
    work = storyboard_path.parent
    out_path = Path(args.out)
    out_path = out_path if out_path.is_absolute() else work / out_path
    raw_dir = work / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    only = {item.strip() for item in args.only.split(",")} if args.only else None

    shots = [shot for shot in storyboard["shots"]
             if shot.get("route") and (not only or shot["id"] in only)]
    if not shots:
        raise SystemExit("没有需要录制的镜头（检查 route / --only）")

    storage = Path(args.storage_state).resolve() if args.storage_state else None
    if storage and not storage.exists():
        print(f"登录态不存在，将匿名录制：{storage}", flush=True)
    failures = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        for shot in shots:
            shot_id = shot["id"]
            context = None
            try:
                options = {
                    "viewport": {"width": args.width, "height": args.height},
                    "device_scale_factor": 1,
                    "record_video_dir": str(raw_dir),
                    "record_video_size": {"width": args.width, "height": args.height},
                }
                if storage and storage.exists():
                    options["storage_state"] = str(storage)
                context = browser.new_context(**options)
                page = context.new_page()
                started = now()
                url = args.base_url.rstrip("/") + "/" + shot["route"].lstrip("/")
                page.goto(url, wait_until="networkidle", timeout=args.timeout)
                if args.login_wait:
                    print(f"[{shot_id}] 等待 {args.login_wait}s 供手动登录…", flush=True)
                    page.wait_for_timeout(args.login_wait * 1000)
                    if storage:
                        context.storage_state(path=str(storage))
                page.wait_for_timeout(args.lead_in * 1000)

                recorder = Recorder(page, args.timeout, args.width, args.height)
                if shot.get("cursor_start"):
                    recorder.prev = list(shot["cursor_start"])
                timeline = now()
                for action in shot.get("actions", []):
                    recorder.run(action)
                page.wait_for_timeout(args.tail * 1000)
                content_seconds = now() - timeline
                for event in recorder.events:
                    event["start"] = round(max(0.0, float(event["start"]) - timeline), 3)
                    event["end"] = round(max(0.0, float(event["end"]) - timeline), 3)
                video = page.video
                context.close()
                context = None
                video_path = video.path()
                offset = max(0.0, timeline - started + args.offset_bias)
                entry = {
                    "id": shot_id,
                    "route": shot["route"],
                    "video": str(video_path),
                    "video_content_offset": round(offset, 3),
                    "content_seconds": round(content_seconds, 3),
                    "events": recorder.events,
                }
                merge_events(out_path, entry)
                print(f"[{shot_id}] 录制完成 {content_seconds:.1f}s，事件 "
                      f"{len(recorder.events)} 条 → {video_path}", flush=True)
            except Exception as exc:
                failures.append(shot_id)
                merge_events(out_path, {
                    "id": shot_id,
                    "route": shot.get("route"),
                    "error": str(exc),
                    "events": [],
                })
                print(f"[{shot_id}] 录制失败：{exc}", flush=True)
            finally:
                if context:
                    context.close()
        browser.close()

    print(f"事件文件：{out_path}", flush=True)
    if failures:
        raise SystemExit("录制失败镜头：" + ", ".join(failures))


if __name__ == "__main__":
    main()
