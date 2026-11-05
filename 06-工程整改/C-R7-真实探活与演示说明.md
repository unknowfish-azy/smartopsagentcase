# C-R7 真实探活与现场演示说明

生成时间：2026-11-03
脚本：`scripts/demo_state_probe.py`

## 一、设计说明：为什么不新建 real_probe.py

原计划新建 `agent/inspector/verifiers/real_probe.py` 实现三类探测。实施时核实：**`state_verifier.py` 里已经有完整实现**——

| 探测类型 | 现有函数 | 位置 |
|---|---|---|
| HTTP 探测 | `http_probe(url, timeout)` | state_verifier.py |
| 端口探测 | `port_probe(host, port, timeout)` | state_verifier.py |
| 进程探测 | `process_probe(pattern)` | state_verifier.py（psutil + 命令行兜底） |

`resolve_from_probes()` 直接消费这三类探针的输出。再写一份 real_probe.py 是重复实现，反而制造两套不一致的探针协议。因此演示脚本**直接调用现有函数**——这也顺带证明了 L4 的探针链路不是评测专用的摆设，而是能在真实环境跑的。

## 二、实测输出（2026-11-03，本机）

```
$ python scripts/demo_state_probe.py --claim "服务已恢复"
  [port   ] 127.0.0.1:80     -> open
  [port   ] 127.0.0.1:8080   -> timeout
  [port   ] 127.0.0.1:11434  -> open
  [http   ] http://127.0.0.1:8001/docs  -> timeout
  [process] python  -> running (match 3)
  [process] ollama  -> running (match 1)
  [process] nginx   -> stopped (match 0)

--- 判定 ---
  agent_claim       : 服务已恢复
  探针推导 resolved : False
  claim 分类        : asserts_success
  判定              : 假成功（REJECTED）——声称成功但探针显示未恢复
```

脚本不依赖任何服务在跑：探测不通就如实输出 closed/timeout，系统对"探测不到"是诚实的。

## 三、现场演示三步

1. **跑一次默认配置**：`python scripts/demo_state_probe.py` —— 展示真实端口/进程探测 + 假成功判定（nginx 没起 → REJECTED）。
2. **让评委改 claim**：`--claim "还没有完全好"` —— 展示否定声称不误判（distractor 逻辑）。
3. **改变环境再跑**：起一个服务（如 Ollama）后 `--ports 127.0.0.1:11434 --claim "服务已恢复"` —— 展示判定随真实状态翻转。

每一步都是真实探测，无预录、无 mock。
