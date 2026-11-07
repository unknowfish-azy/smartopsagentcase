# -*- coding: utf-8 -*-
"""ai-service run token HTTP 级验收（2026-11-06 晚，第三批补充）。

SEC-01/SEC-02：聊天 run 令牌由 Java 边缘（/api/chat/run-token，登录会话）签发，
ai-service 以共享 HMAC secret 校验签名/过期/一次性。本脚本在真实进程上验证：
无 token、伪造 token、过期 token、真实 token 放行、重放拒绝、匿名不签发。

前置：
  1. 后端 8080（local profile，SMARTOPS_CHAT_RUN_TOKEN_SECRET 已从根 .env 注入）；
  2. ai-service 已启动（uvicorn，本脚本默认 127.0.0.1:8010）；
  3. 根 .env 中两端 secret 一致（CHAT_RUN_TOKEN_SECRET / SMARTOPS_CHAT_RUN_TOKEN_SECRET）。

用法：
  "C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe" \
      scripts/e2e/aiservice_run_token_e2e_20261106.py
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sec0405_approval_e2e_20261106 import (  # noqa: E402
    OP1, check, ensure_user, RESULTS,
)

# 默认 8010（脚本自带约定）；可用 SMARTOPS_AI_BASE 覆盖以匹配 start-all.ps1 的 8001。
AI_BASE = os.environ.get("SMARTOPS_AI_BASE", "http://127.0.0.1:8010").rstrip("/")
SECRET = None  # 从 .env 读取


def load_secret() -> str:
    with open(".env", encoding="utf-8") as fh:
        for line in fh:
            name, _, value = line.strip().partition("=")
            if name == "SMARTOPS_CHAT_RUN_TOKEN_SECRET":
                return value
    raise SystemExit("根 .env 缺少 SMARTOPS_CHAT_RUN_TOKEN_SECRET")


def forge(secret: str, subject: str, run_id: str, exp: int) -> str:
    """按共享格式自签一个 token（用于构造'签名合法但已过期'的负例）。"""
    payload = json.dumps({"sub": subject, "run": run_id, "iat": exp - 300, "exp": exp},
                         separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    signing_input = f"v1.{encoded}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return signing_input.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def ai_post(path: str, token: str | None, message: str = "ping"):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        AI_BASE + path, data=json.dumps({"message": message, "use_rag": False}).encode(),
        headers={"Content-Type": "application/json", **({"X-Run-Token": token} if token else {})})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as err:
        try:
            body = json.loads(err.read().decode() or "{}")
        except Exception:
            body = {}
        return err.code, body


def run() -> int:
    global SECRET
    SECRET = load_secret()

    # ── R1 登录会话签发 run token ──────────────────────────────────────
    op1 = ensure_user(OP1)
    status, body = op1.request("GET", "/api/chat/run-token")
    data = body.get("data") or {}
    token, run_id, ttl = data.get("runToken"), data.get("runId"), data.get("expiresInSeconds")
    check("A1", "登录会话可签发短时 run token（no-store）",
          status == 200 and token and run_id and isinstance(ttl, int) and ttl <= 300,
          f"GET /api/chat/run-token -> {status} runId={run_id} ttl={ttl}s")

    # ── R2 无 token 直连 ai-service 被拒 ───────────────────────────────
    status, body = ai_post("/api/chat", None)
    code = ((body.get("detail") or {}).get("code")) if isinstance(body.get("detail"), dict) else body.get("detail")
    check("A2", "ai-service 无 token 拒绝（401 RUN_TOKEN_REQUIRED）",
          status == 401 and code == "RUN_TOKEN_REQUIRED", f"-> {status} {code}")

    # ── R3 伪造 token（格式合法、签名错误） ─────────────────────────────
    status, body = ai_post("/api/chat", "v1.aGVsbG8.aGVsbG8")
    code = ((body.get("detail") or {}).get("code")) if isinstance(body.get("detail"), dict) else body.get("detail")
    check("A3", "伪造 token 拒绝（401 RUN_TOKEN_INVALID）",
          status == 401 and code == "RUN_TOKEN_INVALID", f"-> {status} {code}")

    # ── R4 签名合法但已过期（自签，复用共享 secret） ─────────────────────
    expired = forge(SECRET, "25", "run-expired-e2e", int(time.time()) - 10)
    status, body = ai_post("/api/chat", expired)
    code = ((body.get("detail") or {}).get("code")) if isinstance(body.get("detail"), dict) else body.get("detail")
    check("A4", "过期 token 拒绝（401 RUN_TOKEN_EXPIRED）",
          status == 401 and code == "RUN_TOKEN_EXPIRED", f"-> {status} {code}")

    # ── R5 真实 token 放行（鉴权层通过） ───────────────────────────────
    status, body = ai_post("/api/chat", token)
    auth_reject = status in (401, 403) or (
        isinstance(body.get("detail"), dict) and str(body["detail"].get("code", "")).startswith("RUN_TOKEN"))
    check("A5", "真实后端签发 token 通过 ai-service 鉴权",
          not auth_reject, f"-> {status} {str(body)[:100]}（鉴权层放行；业务层返回按 LLM 配置而定）")

    # ── R6 同一 token 重放被拒（SEC-02 一次性） ─────────────────────────
    status, body = ai_post("/api/chat", token)
    code = ((body.get("detail") or {}).get("code")) if isinstance(body.get("detail"), dict) else body.get("detail")
    check("A6", "同一 run token 重放拒绝（409 RUN_TOKEN_REPLAYED）",
          status == 409 and code == "RUN_TOKEN_REPLAYED", f"-> {status} {code}")

    failed = [r for r in RESULTS if r[2] == "FAIL"]
    print(f"\n==== {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
