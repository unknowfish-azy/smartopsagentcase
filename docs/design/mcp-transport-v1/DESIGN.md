# MCP 传输层落地设计 v1（stdio server + client）

> 定位：把项目的 MCP 能力从「适配器骨架」升级为**可互操作协议实现**。
> 关联：竞赛 AI 技术分项 MCP 4 分（`docs/competition/fact-sheet.md` F09）。
> 状态：**已落地并通过官方 SDK 互操作验证**（2026-11-21）。

---

## 1. 背景与缺口

原实现只有 `agent/tools/adapters/mcp.py`：`MCPTransport` Protocol + `MCPToolAdapter`，
**没有任何 transport 实现**（无 stdio / SSE / HTTP），后端与 ai-service 零命中。
竞赛材料宣称「MCP 适配器与 AgentPlugin 契约」，但缺少可验证的协议能力。

本轮补齐：**stdio 传输 + 服务端 + 客户端**，并证明标准 MCP 客户端能连上并调用。

## 2. 协议范围（诚实边界）

| 项 | 实现 |
|---|---|
| JSON-RPC 2.0 | ✅ 请求 / 通知 / 响应 / 错误 / 标准错误码 |
| MCP `initialize`（版本协商） | ✅ 支持 `2025-03-26` / `2024-11-05`，不支持时回服务端最新版 |
| `notifications/initialized` | ✅ |
| `ping` | ✅ |
| `tools/list` | ✅ 从工具目录生成 |
| `tools/call` | ✅ 走 executor 安全链 |
| stdio 分帧纪律 | ✅ 单行 JSON、UTF-8、stdout 只写 MCP、日志走 stderr |
| Streamable HTTP | ❌ **未实现**（不预留假接口） |
| prompts / resources / sampling | ❌ 未实现（返回 `-32601`） |

## 3. 架构

```
外部 MCP 客户端（Claude Desktop / Cursor / 官方 SDK）
        │ stdio（换行分帧 JSON-RPC）
        ▼
agent/mcp/transport.py  StdioServerTransport（stdout 只写 MCP，日志 stderr）
        ▼
agent/mcp/server.py     SmartOpsMCPServer
        │ initialize / tools/list / tools/call
        ▼
agent/mcp/catalog.py    ToolCatalog（暴露面控制）
        ▼
AgentExecutor.execute  → 安全基线 L0/L2/L1 → PolicyEngine → 工具 → 审计
```

反向（外部 MCP server 接入 SmartOps）：

```
agent/mcp/client.py  MCPClient → StdioClientTransport
        → as_tool_adapter() → 既有 MCPToolAdapter（agent/tools/adapters/mcp.py）
        → 外部工具进入 SmartOps 工具层，同样受安全链管辖
```

## 4. 安全纪律（不绕过既有体系）

`tools/call` **不直接调工具**，而是构造 `PlanStep` + `ExecutionContext` 交给
`AgentExecutor.execute`，因此完整经过：

    L0 合规 → L2 运维红线 → L1 限流 → 风险/审批（PolicyEngine）→ 执行 → 审计

- 默认 **dry_run=True**（演练态，fail-safe）；
- 默认只读暴露面：`REAL` + `risk ∈ {LOW, MEDIUM}` + `SAFE_RETRY`；
  HIGH/CRITICAL、`AT_MOST_ONCE` 必须显式 allowlist 才可见；
- 无 `definition` 的工具不进暴露面；
- 调用身份固定 `mcp-client`，`request_id=mcp-<uuid>`，可审计。

## 5. 用法

```bash
# 查看将暴露的工具
py -3.14 -m agent.mcp --list-tools

# 启动（默认 dry-run、只读）
py -3.14 -m agent.mcp

# 显式白名单
py -3.14 -m agent.mcp --allowlist nginx.status,redis.info

# 允许真实执行（谨慎）
py -3.14 -m agent.mcp --no-dry-run

# 挂载安全基线（需可用审计存储）
py -3.14 -m agent.mcp --security
```

## 6. 验证（可复现）

```bash
# 1) 单测（33 条）
py -3.14 -m pytest tests/agent/mcp/ -v

# 2) 官方 mcp SDK 互操作（隔离安装，不污染主环境）
py -3.14 -m pip install --target .runtime/mcp-sdk mcp
MCP_SDK_PATH=.runtime/mcp-sdk py -3.14 -m pytest \
    tests/agent/mcp/test_interop_official_sdk.py -v
```

**互操作实测结果（2026-11-21）**：官方 SDK 客户端请求 `2025-11-25`，
服务端按 spec 协商回 `2025-03-26`；`tools/list` 返回 8 个只读工具；
`tools/call nginx.status` 在 dry-run 下 `is_error=False`。
未设置 `MCP_SDK_PATH` 时该测试**显式 skip**（不伪造通过）。

## 7. 测试清单

| 文件 | 覆盖 |
|---|---|
| `test_protocol.py` | 单行编解码、NaN 拒绝、消息判别、错误码、版本协商 |
| `test_catalog.py` | 默认只读策略、allowlist 覆盖、非 PluginTool 忽略 |
| `test_server.py` | 握手、未初始化拒绝、ping、tools/list、tools/call、执行错误、executor 留痕 |
| `test_client_server_e2e.py` | 真实子进程握手 + list + call + 适配器桥接 |
| `test_interop_official_sdk.py` | 官方 SDK 互操作（可选，无 SDK 时 skip） |

## 8. 建议的 fact-sheet 口径（待合并）

> 本轮 fact-sheet 已有并行改动（+75 行），为避免版本交织，条目先落此文档，
> 合并时抄入 fact-sheet 并注明来源命令。

```text
| F32 | MCP 协议能力 | **已实现 stdio server + client**：JSON-RPC 2.0 + MCP
      initialize/ping/tools.list/tools/call；stdio 单行分帧，stdout 只写 MCP、
      日志走 stderr；tools/call 复用 AgentExecutor 安全链（L0/L2/L1 + 审批 + 审计）。
      暴露面默认只读（REAL + LOW/MEDIUM + SAFE_RETRY），写操作须显式 allowlist。
      **官方 mcp SDK 互操作实测通过（2026-11-21）**：协商 2025-03-26、list 8 工具、
      call nginx.status dry-run is_error=False | `agent/mcp/{protocol,transport,catalog,server,client}.py`；
      `py -3.14 -m pytest tests/agent/mcp/ -v`（33 passed）；
      `MCP_SDK_PATH=.runtime/mcp-sdk pytest tests/agent/mcp/test_interop_official_sdk.py`（1 passed，
      无 SDK 时 skip） | 新增；旧「仅适配器骨架」表述作废 |
```

## 9. 后续（不在本轮）

1. Streamable HTTP transport（若需把 MCP 挂到 ai-service 对外端点）。
2. 把 MCP server 接入 ai-service lifespan，提供 `/mcp` 端点（需先定鉴权与 Origin 校验）。
3. 暴露面可配置化（配置文件而非仅环境变量）。
