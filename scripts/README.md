# SmartOpsAgent Scripts

本目录保存 SmartOpsAgent 项目在开发、测试、部署和服务器监控过程中使用的辅助脚本。

## 目录结构

```text
scripts/
├── README.md
│
├── common/
│   ├── init-db.sql
│   └── README.md
│
├── linux/
│   ├── README.md
│   ├── collect-metrics.sh
│   └── install-monitor.sh
│
└── windows/
    ├── README.md
    ├── check-env.ps1
    └── start-dev.ps1

## Live LLM check

With Ollama running and `LLM_PROVIDER=ollama`, run five real streaming prompts:

```powershell
python .\scripts\check_llm_live.py
```

The checker prints the effective provider, degradation flag, first-token latency,
and total latency for every prompt. It exits non-zero when Ollama is unavailable,
the provider is `mock`, or a request falls back to mock.
