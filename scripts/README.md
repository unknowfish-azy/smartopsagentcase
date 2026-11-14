# SmartOpsAgent Scripts

本目录保存 SmartOpsAgent 项目在开发、测试、部署和服务器监控过程中使用的辅助脚本。

## 新手请看这里（第一次接触项目）

**不要**直接翻看本目录下的脚本——脚本数量多、用途各异，新手容易混淆。

### 推荐路径（Windows）

进入 [`handoff-kit/`](./handoff-kit/) 目录，按顺序双击四个 `.bat` 文件即可：

1. **`1-检查环境.bat`** — 体检环境，缺什么给安装命令
2. **`2-安装环境.bat`** — 装依赖、生成 `.env`、建库（只需跑一次）
3. **`3-启动平台.bat`** — 一键启动全部服务
4. **`4-停止平台.bat`** — 一键停止全部服务

这四个脚本是项目对新手最友好的入口，会自动处理 `.env` 密钥生成、数据库创建、依赖安装等所有繁琐步骤。

### 脚本怎么选？

| 你想做什么 | 用哪个脚本 |
|---|---|
| 第一次跑起来项目 | `handoff-kit/` 四个 bat |
| 日常启停全栈（已装好环境） | `windows/start-platform.ps1`（或双击 `start-platform.cmd`） |
| 只看服务状态 | `windows/start-platform.ps1 -Status` |
| 检查环境/端口/内存 | `windows/check-env.ps1` 或 `windows/status-local.ps1` |
| 单独重启知识服务 | `windows/restart-knowledge.ps1` |
| 单独重启后端 | `windows/restart-local-backend.ps1` |
| 只启动管理员前端 | `windows/start-admin-frontend.ps1` |
| 启动本地 Ollama 推理 | `windows/start-mini.ps1` |

> ⚠️ **不要同时用 `start-platform.ps1` 和 `handoff-kit/3-启动平台.bat` 启动**——它们会争抢相同端口。选一个用到底即可。日常开发推荐 `start-platform.ps1`（功能更全、支持状态查询）。

## 目录结构

```text
scripts/
├── README.md              # 本文件（脚本导航）
├── handoff-kit/           # ⭐ 新手一键脚本（检查/安装/启动/停止）
├── windows/               # Windows 开发运维脚本（启停、重启、体检）
├── linux/                 # Linux 服务器监控脚本
├── common/                # 跨平台公共脚本（SQL 等）
├── e2e/                   # 端到端测试脚本（Playwright / HTTP）
├── research/              # 研究实验脚本（恢复契约、数据采集）
├── knowledge/             # 知识库目录与导出脚本
├── backup/                # 备份清单生成
├── observability/         # 可观测性启动
├── check_*.py             # 各类一致性 / 合规检查
├── eval_*.py              # 模型与检索评测
├── fact_ledger.py         # 事实台账生成
└── ...
```

## 各子目录说明

### handoff-kit/ — 新手一键包

四个编号 `.bat` 文件 + 对应 `.ps1` 实现。所有路径按脚本位置推导，整个目录可拷到任意盘任意目录。
详见 [`handoff-kit/README.txt`](./handoff-kit/README.txt)。

### windows/ — Windows 开发运维

面向已熟悉项目的开发者，提供更细粒度的控制：全栈启停、单服务重启、环境体检、配置检查等。
详见 [`windows/README.md`](./windows/README.md)。

### linux/ — Linux 服务器

服务器监控 Agent 的基础能力脚本（指标采集、监控安装）。

### e2e/ — 端到端测试

UI 走查（Playwright）、HTTP 接口、审批链路、安全 fixture 等测试脚本。

### 根目录 Python 脚本

`check_*.py` / `eval_*.py` / `fact_ledger.py` / `rollback_defense.py` 等，每个脚本顶部有 docstring 说明用途。多为只读检查或评测，不会修改业务数据。

## Live LLM check

With Ollama running and `LLM_PROVIDER=ollama`, run five real streaming prompts:

```powershell
python .\scripts\check_llm_live.py
```

The checker prints the effective provider, degradation flag, first-token latency,
and total latency for every prompt. It exits non-zero when Ollama is unavailable,
the provider is `mock`, or a request falls back to mock.
