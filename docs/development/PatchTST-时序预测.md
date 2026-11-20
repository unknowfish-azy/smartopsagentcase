# PatchTST 时序预测接入与使用说明

> 更新日期：2026-11-18  
> 适用范围：`ai-service` 单指标多步预测接口与 Agent `nn.forecast` 工具  
> 当前状态：**软件链路已实现并通过相关测试；真实运维权重、真实数据效果和区间覆盖率尚未完成训练评测。**

## 1. 定位与边界

PatchTST 在本项目中是 Agent 的“时序预测感官”，负责把一段历史指标转换为未来点值、残差近似区间、趋势和阈值越界证据，供上层 LLM 研判。

它与 AnomalyTransformer 的任务不同：

| 模块 | 输入 | 主要输出 | 适用问题 |
|---|---|---|---|
| AnomalyTransformer | 历史指标 | 异常分数、异常时段 | 当前是否异常 |
| PatchTST | 历史指标 | 未来点值、预测区间、趋势 | 接下来可能如何变化 |

当前实现遵循以下边界：

- 单变量、按时间升序的等间隔序列；接口不接收时间戳，也不会自动补齐缺失点。
- 直接多步预测，不进行自回归滚动预测。
- 不直接执行扩容、重启、限流等处置动作。
- `risk_score` 是趋势变化、不确定性和可选阈值越界组成的**启发式风险分**，不是故障概率或校准后的恶化概率。
- 95% 区间来自残差正态近似，不等于经过覆盖率校准的置信区间。

## 2. 架构与代码位置

```text
历史指标
   │
   ▼
Agent nn.forecast（只读、SAFE_RETRY）
   │ HTTP
   ▼
POST /api/nn/forecast
   │
   ├─ checkpoint 可用且输入满足约束 → PatchTST
   │
   └─ 无权重 / 输入不匹配 / 推理失败 → linear 或 seasonal_naive
   │
   ▼
点预测 + 95% 残差近似区间 + 趋势 + 风险依据
   │
   ▼
结构化证据返回 Agent，由 LLM 决定后续诊断
```

| 文件 | 职责 |
|---|---|
| `ai-service/app/training/patchtst_model.py` | Patch 化、Transformer 编码器、多步预测头、归一化 |
| `ai-service/app/services/forecast_detector.py` | 权重加载、推理、显式降级、区间与趋势风险证据 |
| `ai-service/app/schemas/forecast.py` | 请求、响应和模型状态 Schema |
| `ai-service/app/api/nn.py` | `/forecast-info` 与 `/forecast` 路由 |
| `agent/tools/builtin/nn_perception.py` | Agent `nn.forecast` 工具 |
| `ai-service/scripts/train_patchtst.py` | 合成数据训练、基线对比和 checkpoint 保存 |
| `ai-service/app/tests/test_forecast_detector.py` | 模型形状、降级、区间、阈值和 checkpoint 测试 |
| `tests/agent/test_nn_perception.py` | Agent 工具负载与短序列错误测试 |

## 3. 模型与 checkpoint

默认架构参数：

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `context_length` | 64 | 训练时历史上下文长度 |
| `horizon` | 12 | checkpoint 支持的最大直接预测步数 |
| `patch_len` | 16 | 每个 Patch 的点数 |
| `stride` | 8 | 相邻 Patch 的步长，允许重叠 |
| `d_model` | 64 | Transformer 隐层维度 |
| `nhead` | 4 | 注意力头数 |
| `num_layers` | 2 | Transformer Encoder 层数 |
| `max_patches` | 128 | 位置嵌入支持的最大 Patch 数 |

每个窗口使用自身上下文的 mean/std 归一化，预测后通过对应 `center`、`scale` 逆变换回原始指标单位。服务默认读取：

```text
ai-service/models/patchtst.pt
```

checkpoint 必须包含：

| 字段 | 内容 |
|---|---|
| `config` | 完整模型架构参数，用于重建 PatchTST |
| `model_state` | PyTorch 参数 |
| `normalization` | `{"method": "mean_std", "eps": 1e-6}` |
| `residual_std` | 独立测试集上各预测步的归一化残差标准差，长度必须等于训练 `horizon` |

模型采用进程内单例。替换权重后需要重启 `ai-service`，或在未来接入受控的热加载机制；不要在请求路径中并发改写全局模型状态。

## 4. HTTP API

### 4.1 查询模型状态

```http
GET /api/nn/forecast-info
```

```powershell
curl.exe -s http://127.0.0.1:8001/api/nn/forecast-info
```

关键字段：

- `kind=patchtst`：checkpoint 已加载。
- `kind=fallback`：服务仍可提供统计预测，`reason` 说明降级原因。
- `context_length` / `horizon`：已加载模型要求的历史长度和最大预测步数；fallback 状态下可以为 `null`。
- `available` 只表示预测能力是否可用，**不能据此判断正在使用神经模型**；应同时检查 `kind`。

### 4.2 单指标预测

```http
POST /api/nn/forecast
Content-Type: application/json
```

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/api/nn/forecast `
  -H "Content-Type: application/json" `
  -d '{"values":[42,43,44,45,46,47,48,49,50,51,52,53],"horizon":3,"metric_name":"cpu_usage","upper_threshold":80,"seasonal_period":0}'
```

请求字段：

| 字段 | 必填 | 默认值 | 约束与含义 |
|---|---|---:|---|
| `values` | 是 | — | 8–4096 个有限数值，按时间升序 |
| `horizon` | 否 | 6 | 1–64；超过 checkpoint 的训练 horizon 会降级 |
| `metric_name` | 否 | `unknown` | 指标名称，仅用于证据标识 |
| `seasonal_period` | 否 | 0 | 0–512；降级时大于 1 且历史点不少于两个周期，使用季节朴素预测 |
| `upper_threshold` | 否 | `null` | 可选业务上限，用于识别预测越界 |
| `lower_threshold` | 否 | `null` | 可选业务下限；同时提供时必须小于上限 |

响应结构示例（**数值仅用于说明结构，不是模型实测结果**）：

```json
{
  "ok": true,
  "mode": "patchtst",
  "model_status": "ok",
  "model_status_detail": null,
  "metric_name": "cpu_usage",
  "horizon": 2,
  "points": [
    {"step": 1, "value": 54.0, "lower": 51.0, "upper": 57.0},
    {"step": 2, "value": 55.0, "lower": 50.0, "upper": 60.0}
  ],
  "trend": "rising",
  "trend_slope": 1.0,
  "risk_score": 0.25,
  "risk_level": "low",
  "risk_basis": ["预测末端相对最后观测值变化 2"],
  "interval_level": 0.95,
  "interval_method": "gaussian_residual_approximation",
  "explanation": "[patchtst] 未来 2 点趋势为 rising"
}
```

响应判读：

| 字段 | 含义 |
|---|---|
| `mode` | 本次实际执行方式：`patchtst` / `linear` / `seasonal_naive` |
| `model_status` | `ok` 仅对应 PatchTST；统计预测一律为 `fallback` |
| `model_status_detail` | 降级原因；成功使用 PatchTST 时为 `null` |
| `points[].step` | 相对最后观测点的未来步数，不是绝对时间戳 |
| `points[].lower/upper` | `value ± 1.96 × residual_std` 的近似区间 |
| `trend` / `trend_slope` | 预测曲线方向和每采样间隔斜率 |
| `risk_score` / `risk_level` | 0–1 启发式分数；low `<0.33`，medium `[0.33,0.67)`，high `≥0.67` |
| `risk_basis` | 分数依据；未传业务阈值时会明确提示其非概率语义 |

## 5. 降级矩阵

| 条件 | 实际模式 | 状态说明 |
|---|---|---|
| torch 未安装 | `linear` 或 `seasonal_naive` | `fallback`，说明 torch 不可用 |
| 默认 checkpoint 不存在 | `linear` 或 `seasonal_naive` | `fallback`，说明未找到权重 |
| checkpoint 字段、归一化或残差长度不合法 | `linear` 或 `seasonal_naive` | `fallback`，说明加载失败 |
| 历史长度小于 checkpoint `context_length` | 统计预测 | 不做隐式填充，明确说明上下文不足 |
| 请求 horizon 大于 checkpoint 训练 horizon | 统计预测 | 不伪造模型未训练的预测步 |
| PatchTST 推理异常 | 统计预测 | 返回推理失败原因 |
| 降级且季节周期有效 | `seasonal_naive` | 重复最后一个完整周期 |
| 其他降级情况 | `linear` | 最近最多 64 点做最小二乘线性外推 |

统计降级是可用性保障，不代表神经网络效果，也不能纳入 PatchTST 的神经模型指标。

## 6. Agent 工具调用

工具名：`nn.forecast`。风险等级为 `LOW`，目标为 `AI_SERVICE`，幂等策略为 `SAFE_RETRY`。

```json
{
  "values": [42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53],
  "horizon": 6,
  "metric_name": "cpu_usage",
  "upper_threshold": 80
}
```

给 LLM 的使用约束：

1. 先检查 `mode` 和 `model_status_detail`，再引用预测结论。
2. 将输出作为诊断证据，不直接转写为处置指令。
3. 未提供业务上下限时，不把 `risk_score` 描述为“故障概率”。
4. 上升不必然意味着恶化，下降也不必然意味着恢复；语义由指标方向和业务阈值决定。
5. 需要异常告警时调用异常检测工具，不能用 PatchTST 的 MAE/MSE 替代异常检测 PR-AUC/F1。

## 7. 训练与保存

当前训练入口只支持合成数据冒烟和流程验证，**尚未实现真实指标数据集读取**。

在 `ai-service` 目录执行：

```powershell
# 不保存权重：最小训练冒烟
python scripts/train_patchtst.py --mock --num-series 2 --epochs 1 --batch-size 8

# 保存合成数据权重与指标，隔离到 mock 目录，避免覆盖生产权重
python scripts/train_patchtst.py --mock --num-series 64 --epochs 20 --model-dir models/mock --json reports/patchtst-mock-metrics.json
```

主要参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--num-series` | 64 | 合成训练序列数量；测试序列为 `max(num_series/4, 4)` |
| `--epochs` | 20 | 训练轮数 |
| `--lr` | 0.001 | Adam 学习率 |
| `--batch-size` | 32 | 批大小 |
| `--context-length` | 64 | 上下文长度 |
| `--horizon` | 12 | 训练预测步数 |
| `--patch-len` | 16 | Patch 长度 |
| `--stride` | 8 | Patch 步长 |
| `--d-model` | 64 | 隐层维度 |
| `--seed` | 42 | 随机种子 |
| `--model-dir` | 不保存 | 保存为 `<model-dir>/patchtst.pt` |
| `--json` | 不保存 | 保存 MAE/MSE 与基线报告 |

训练输出同时包含：

- `patchtst.mae/mse`：逆归一化后的原始指标单位误差。
- `last_value_naive.mae/mse`：最后观测值重复的朴素基线。
- `num_samples`：测试窗口数。
- checkpoint 内的 `residual_std`：归一化空间的逐步残差标准差，用于推理区间。

合成数据指标不能写成生产指标。只有 PatchTST 在独立真实测试集上优于朴素基线、完成区间覆盖率和安全性评测后，才能将权重部署为生产感知能力。

## 8. 评测要求

PatchTST 使用回归与区间指标，不使用异常检测的 PR-AUC、事件级 F1、TTD 或 NAB Score 评价预测本身。

最低评测集合：

| 指标 | 用途 |
|---|---|
| MAE | 原始单位平均绝对误差，便于运维解释 |
| MSE | 强调较大预测偏差 |
| 逐步 MAE | 检查误差随 horizon 增长的情况 |
| 95% 区间覆盖率 | 实际真值落入区间的比例，与标称 0.95 对比 |
| 平均区间宽度 | 防止用过宽区间换取覆盖率 |
| 相对最后值/季节朴素基线提升 | 判断神经模型是否真正增益 |
| 推理 P50/P95 延迟 | 判断在线调用成本 |

真实数据实验应固定时间顺序，按指标实体和时间切分训练、验证、测试集，避免重叠窗口跨集合造成泄漏；同时记录数据集版本、采样周期、缺失值处理、归一化方式、训练配置、随机种子和 checkpoint 哈希。详细公式见 `docs/evaluation-metrics.md`。

## 9. 测试命令

在 `ai-service` 目录：

```powershell
python -m pytest app/tests/test_forecast_detector.py -q
python -m pytest app/tests/test_rootcause_status.py app/tests/test_trace_detector.py app/tests/test_tgat_detector.py -q
```

在项目根目录：

```powershell
python -m pytest tests/agent/test_nn_perception.py -q
python -m compileall -q ai-service/app/training/patchtst_model.py ai-service/app/services/forecast_detector.py ai-service/app/schemas/forecast.py ai-service/scripts/train_patchtst.py agent/tools/builtin/nn_perception.py
```

这些测试验证软件契约和降级行为，不证明真实数据精度、区间校准或生产稳定性。

## 10. 后续生产化清单

1. 接入带时间戳的真实指标数据集，处理缺失点、非等间隔采样和异常值。
2. 增加真实数据训练入口及按时间、实体隔离的数据切分。
3. 增加逐步 MAE/MSE、区间覆盖率、区间宽度和多基线对比。
4. 必要时使用验证集做区间校准，不能直接把残差正态近似称为校准置信区间。
5. 记录权重版本、数据血缘、训练配置和评测报告，再接入模型注册与发布门禁。
6. 在 Agent 端到端实验中比较启用预测前后的处置成功率、MTTR、无效工具调用和误判率。
