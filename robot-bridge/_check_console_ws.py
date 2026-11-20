"""完整登录流程：先 GET session 拿 CSRF，再 POST login 带 CSRF"""
import asyncio, json, websockets, sys
import http.cookiejar, urllib.request

BACKEND = "http://127.0.0.1:8080"

def http_opener():
    cj = http.cookiejar.CookieJar()
    return cj, urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def get_csrf(opener):
    resp = opener.open(f"{BACKEND}/api/auth/session")
    body = json.loads(resp.read().decode())
    csrf = body.get("data", {}).get("csrfToken", "")
    return csrf

def login(opener, csrf):
    data = json.dumps({"username": "admin", "password": "Admin@2026Secure!", "portal": "user", "humanToken": ""}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/auth/login", data=data,
        headers={"Content-Type": "application/json", "X-CSRF-TOKEN": csrf}, method="POST",
    )
    resp = opener.open(req)
    return json.loads(resp.read().decode())

async def main():
    cj, opener = http_opener()
    
    # 1. GET session → 拿 JSESSIONID + CSRF
    print("=== 1. GET session ===")
    try:
        csrf = get_csrf(opener)
        print(f"CSRF token: {csrf[:20]}...")
        print(f"Cookies after session: {[(c.name, c.value[:20]) for c in cj]}")
    except Exception as e:
        print(f"Session failed: {e}")
        return
    
    # 2. POST login 带 CSRF
    print("\n=== 2. POST login ===")
    try:
        body = login(opener, csrf)
        print(f"Login response code: {body.get('code')}")
        print(f"Cookies after login: {[(c.name, c.value[:20]) for c in cj]}")
    except urllib.error.HTTPError as e:
        print(f"Login HTTP {e.code}: {e.read().decode()[:200]}")
        return
    except Exception as e:
        print(f"Login failed: {e}")
        return
    
    # 3. 连 console websocket
    print("\n=== 3. Connect console websocket ===")
    cookie_str = "; ".join(f"{c.name}={c.value}" for c in cj)
    print(f"Cookie header: {cookie_str[:60]}...")
    try:
        async with websockets.connect(
            "ws://127.0.0.1:8080/ws/robot/console",
            additional_headers={"Cookie": cookie_str},
        ) as ws:
            print("✅ Connected!")
            for i in range(8):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    data = json.loads(msg)
                    t = data.get("type")
                    if t == "hello":
                        print(f"  #{i}: hello caps={data.get('payload',{}).get('capabilities')}")
                    elif t == "telemetry":
                        p = data.get("payload", {})
                        has_j = "joints" in p
                        j_count = len(p.get("joints", {})) if has_j else 0
                        print(f"  #{i}: telemetry battery={p.get('battery')} pose=({p.get('pose',{}).get('x')},{p.get('pose',{}).get('y')}) joints={'YES('+str(j_count)+')' if has_j else 'NONE'}")
                    elif t == "subscribe":
                        print(f"  #{i}: subscribe ack deviceKey={data.get('payload',{}).get('deviceKey')}")
                    else:
                        print(f"  #{i}: type={t}")
                except asyncio.TimeoutError:
                    print(f"  #{i}: timeout")
    except Exception as e:
        print(f"❌ WS error: {type(e).__name__}: {e}")

asyncio.run(main())
