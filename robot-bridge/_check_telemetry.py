"""临时脚本：连后端 bridge websocket 模拟 console 订阅，看遥测有没有 joints。"""
import asyncio
import json
import websockets


async def main():
    # 用 console endpoint，但用另一种方式——让我直接看 actuator 日志
    # 或者，看看后端 RobotBridgeWebSocketHandler 收到的原始 payload
    
    # 方案：用 bridge 端 token 连 /ws/robot/bridge，声明一个新设备
    # 但这样会干扰现有 sim 连接... 
    # 
    # 换个思路：直接 curl actuator 看遥测快照
    import urllib.request
    import urllib.error
    
    # 尝试 actuator endpoint (不需要认证)
    urls = [
        "http://127.0.0.1:8080/actuator/robot/telemetry",
        "http://127.0.0.1:8080/actuator/robot",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=3)
            body = resp.read().decode()
            print(f"=== {url} ===")
            print(body[:2000])
            print()
        except Exception as e:
            print(f"{url}: {e}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
