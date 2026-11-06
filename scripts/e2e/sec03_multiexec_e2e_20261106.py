# -*- coding: utf-8 -*-
"""SEC-03 多机批量命令 双人确认正向链路 HTTP 级验收（2026-11-06 晚，第三批）。

背景：SEC-03 负例（自批拦截）已在 sec0405 脚本覆盖；本脚本补正向链路——
CRITICAL 预览由预览创建者发起、第二审批人（不同主体）回显 nonce 触发执行。

前置：
  1. MySQL(3306)/Redis(6379) 在跑，后端 8080（local profile）已启动；
  2. scripts/e2e/mock_ssh_server.py 在 127.0.0.1:2222 监听（runtime 只能由真实
     SSH 拨号注册）；
  3. 登录走本地图形点选人机验证自动解题（不绕过任何安全机制）。

用法：
  "C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe" \
      scripts/e2e/sec03_multiexec_e2e_20261106.py [--keep]
  --keep 保留夹具数据（默认自动清理）。
"""
import json
import sys
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sec0405_approval_e2e_20261106 import (  # noqa: E402
    BASE, OP1, OP2, PASSWORD, SSH_PORT, SSH_USER, SSH_PASSWORD,
    Client, NO_PROXY, check, expect, ensure_user, sql_exec, RESULTS,
)


def run() -> int:
    op1 = ensure_user(OP1)
    op2 = ensure_user(OP2)
    op1_id = sql_exec(f"SELECT id FROM app_user WHERE username='{OP1}'")[0]
    op2_id = sql_exec(f"SELECT id FROM app_user WHERE username='{OP2}'")[0]
    print(f"  夹具: op1={OP1}(#{op1_id}) op2={OP2}(#{op2_id})")

    # op1 拨号 mock SSH 注册 runtime
    status, body = op1.request("POST", "/api/operations/sessions", {
        "name": "e2e-sec03-ssh", "protocol": "SSH", "host": "127.0.0.1", "port": SSH_PORT,
        "username": SSH_USER, "password": SSH_PASSWORD})
    assert status == 200, f"建 SSH 会话失败: {status} {body}"
    session_id = body["data"]["id"]
    status, body = op1.request("POST", f"/api/operations/sessions/{session_id}/connect?decision=TRUST_ONCE")
    runtime_id = (body.get("data") or {}).get("runtimeId")
    check("M1", "真实 SSH 拨号注册 runtime", status == 200 and runtime_id,
          f"connect -> {status} runtimeId={str(runtime_id)[:8]}...")

    # ── T1 CRITICAL 预览 ────────────────────────────────────────────────
    status, body = op1.request("POST", "/api/operations/multi-exec/preview", {
        "command": "rm -rf /tmp/e2e-sec03-data", "runtimeIds": [runtime_id],
        "productionTarget": False})
    pv = body.get("data") or {}
    check("M2", "CRITICAL 命令预览 requiredApprovals=2", status == 200
          and pv.get("risk") == "CRITICAL" and pv.get("requiredApprovals") == 2,
          f"preview -> {status} risk={pv.get('risk')} approvals={pv.get('requiredApprovals')}")
    nonce, preview_id = pv["confirmationNonce"], pv["id"]

    # ── T2 自批拦截（负例回归） ─────────────────────────────────────────
    status, body = op1.request("POST", "/api/operations/multi-exec/execute", {
        "previewId": preview_id, "confirmationNonce": nonce, "secondConfirmationNonce": nonce})
    check("M3", "预览者本人回显双 nonce 被拒（自批）",
          *expect(status, body, 409, "SECOND_APPROVER_REQUIRED"))

    # ── T3 第二审批人触发执行（正向链路，本轮修复目标） ─────────────────
    status, body = op2.request("POST", "/api/operations/multi-exec/execute", {
        "previewId": preview_id, "confirmationNonce": nonce, "secondConfirmationNonce": nonce})
    result = body.get("data") or {}
    check("M4", "第二审批人（不同主体）触发 CRITICAL 执行成功",
          status == 200 and result.get("status") == "SUCCEEDED",
          f"execute by op2 -> {status} run={result.get('runId')} status={result.get('status')} "
          f"succeeded={result.get('succeeded')} msg={body.get('message', '')}")

    # ── T4 一次性：预览重放 ─────────────────────────────────────────────
    status, body = op2.request("POST", "/api/operations/multi-exec/execute", {
        "previewId": preview_id, "confirmationNonce": nonce, "secondConfirmationNonce": nonce})
    check("M5", "已执行预览重放被拒（一次性）", *expect(status, body, 404, "PREVIEW_NOT_FOUND"))

    # ── T5 低风险预览非创建者执行被拒（归属防护） ────────────────────────
    status, body = op1.request("POST", "/api/operations/multi-exec/preview", {
        "command": "uptime", "runtimeIds": [runtime_id], "productionTarget": False})
    low = body["data"]
    status, body = op2.request("POST", "/api/operations/multi-exec/execute", {
        "previewId": low["id"], "confirmationNonce": low["confirmationNonce"]})
    check("M6", "低风险预览仅创建者可执行（他人触发 403）",
          *expect(status, body, 403, "PREVIEW_OWNER_REQUIRED"))

    # ── T6 低风险创建者本人执行成功 ─────────────────────────────────────
    status, body = op1.request("POST", "/api/operations/multi-exec/execute", {
        "previewId": low["id"], "confirmationNonce": low["confirmationNonce"]})
    result = body.get("data") or {}
    check("M7", "低风险预览创建者执行成功", status == 200 and result.get("status") == "SUCCEEDED",
          f"execute by op1 -> {status} status={result.get('status')}")

    # ── T7 DB 佐证：CRITICAL run 的第二审批人落库 ───────────────────────
    from sec0405_approval_e2e_20261106 import db
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT r.second_approver_id, r.approved_by, r.approval_count, r.user_id "
            "FROM runbook_run r JOIN runbook b ON r.runbook_id=b.id "
            "WHERE b.name LIKE '\\_\\_multi\\_exec\\_\\_%' AND r.risk_level='CRITICAL' "
            "ORDER BY r.id DESC LIMIT 1")
        row = cur.fetchone()
    if row:
        second, approver, count, owner = row
        check("M8", "CRITICAL run 落库含第二审批人（可追责）",
              second == op2_id and approver == op2_id and count == 2 and owner == op1_id,
              f"run owner={owner}(op1) second_approver={second}(op2) approved_by={approver} "
              f"approval_count={count}")
    else:
        check("M8", "CRITICAL run 落库含第二审批人（可追责）", False, "未找到 CRITICAL adhoc run")

    failed = [r for r in RESULTS if r[2] == "FAIL"]
    print(f"\n==== {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ====")
    if "--keep" not in sys.argv:
        cleanup(session_id, op1_id, op2_id)
    return 1 if failed else 0


def cleanup(session_id: int, op1_id: int, op2_id: int):
    print("  清理...")
    for sql in [
        f"DELETE FROM runbook_run_target WHERE run_id IN "
        f"(SELECT id FROM runbook_run WHERE user_id IN ({op1_id},{op2_id}))",
        f"DELETE FROM runbook_run WHERE user_id IN ({op1_id},{op2_id})",
        f"DELETE FROM runbook_step WHERE version_id IN "
        f"(SELECT id FROM runbook_version WHERE runbook_id IN "
        f"(SELECT id FROM runbook WHERE user_id IN ({op1_id},{op2_id})))",
        f"DELETE FROM runbook_version WHERE runbook_id IN "
        f"(SELECT id FROM runbook WHERE user_id IN ({op1_id},{op2_id}))",
        f"DELETE FROM runbook_trigger WHERE runbook_id IN "
        f"(SELECT id FROM runbook WHERE user_id IN ({op1_id},{op2_id}))",
        f"DELETE FROM runbook_schedule WHERE runbook_id IN "
        f"(SELECT id FROM runbook WHERE user_id IN ({op1_id},{op2_id}))",
        f"DELETE FROM runbook WHERE user_id IN ({op1_id},{op2_id})",
        f"DELETE FROM operation_run_record WHERE user_id IN ({op1_id},{op2_id})",
        f"DELETE FROM operation_session WHERE id={session_id}",
        f"DELETE FROM operation_credential WHERE user_id IN ({op1_id},{op2_id})",
    ]:
        try:
            sql_exec(sql)
        except Exception as err:
            print(f"    跳过: {sql[:56]}... ({err})")
    print("  清理完成（runbook 族/run_records/session/credential）")


if __name__ == "__main__":
    sys.exit(run())
