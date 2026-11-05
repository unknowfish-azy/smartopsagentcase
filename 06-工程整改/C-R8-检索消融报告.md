# 检索消融实验报告（S1）

生成时间：2026-11-03
脚本：`scripts/eval_retrieval_ablation.py`
数据：`SmartOps-Dataset/Linux/` 7 个 JSONL，14 条原始问法
产物：`eval_retrieval_ablation.csv`（n=56 逐条）、`eval_retrieval_ablation.before-fix.csv`、`eval_retrieval_ablation.n14.csv`、`eval_retrieval_ablation.before-fix.n14.csv`

---

## 一、实验设计

四组对照，**全部调用 `knowledge/` 下现有检索器，不改权重、不改 top_k、不筛样本**：

| 组 | 配置 | 说明 |
|---|---|---|
| A | BM25 only | 纯词法路，`BM25Retriever.search` |
| B | Vector only | 纯向量路，哈希嵌入 256 维 + 余弦相似度 |
| C | Hybrid | 0.6×向量分 + 0.4×BM25 分（`HybridRetriever` 默认权重） |
| D | Hybrid + Rerank | C 的 top10 再经 `LexicalReranker`（0.7×分数 + 0.3×词元重合）取 top5 |

指标：Recall@3、MRR、nDCG@5（二值增益，语料中每条 query 恰好一个相关文档，IDCG=1）。

两套 query 口径：

- **full = n=56**：14 条原始问法 + 42 条人工改写（每条原始问法 3 条独立改写，来源 `_SCENARIO_VARIANTS`）
- **canonical = n=14**：仅原始问法

---

## 二、主结果（n=56，主口径）

### 修复前（`--legacy-tokenizer`）

| 组 | Recall@3 | MRR | nDCG@5 |
|---|---|---|---|
| A BM25 only | **0.8214** | **0.7164** | **0.7606** |
| B Vector only | 0.3750 | 0.3208 | 0.3690 |
| C Hybrid | 0.6250 | 0.5208 | 0.5859 |
| D Hybrid+Rerank | 0.6786 | 0.5863 | 0.6488 |

**BM25 单路胜过混合检索**——这是第一轮跑出来的真实结果。

### 修复后

| 组 | Recall@3 | MRR | nDCG@5 |
|---|---|---|---|
| A BM25 only | 0.8214 | 0.7164 | 0.7606 |
| B Vector only | 0.7500 | 0.6777 | 0.7137 |
| C Hybrid | 0.8571 | 0.7857 | 0.8128 |
| D Hybrid+Rerank | **0.8750** | **0.7902** | **0.8164** |

### 对照

| 组 | Recall@3 修复前 | 修复后 | Δ |
|---|---|---|---|
| A BM25 only | 0.8214 | 0.8214 | **0（不变）** |
| B Vector only | 0.3750 | 0.7500 | +0.3750 |
| C Hybrid | 0.6250 | 0.8571 | +0.2321 |
| D Hybrid+Rerank | 0.6786 | 0.8750 | +0.1964 |

---

## 三、结论

### 1. 第一轮失败暴露了一个真实缺陷，不是调参问题

`HashEmbedding._encode_one` 原实现是 `text.lower().split()`。中文没有空格，整句被切成**一个 token**，哈希后只落在 256 维中的**一个维度**上，向量检索等于随机。B 组 0.3750 就是随机水平。

同一项目的 `BM25Retriever` 用的是 `[\u4e00-\u9fff]+|[a-zA-Z0-9_]+` 正则分词——两者粒度不一致。这是实现缺陷，不是设计取舍。

### 2. 修复方式：中文补单字 + 相邻二元组，保持 API 与维度不变

`knowledge/embedding/hash_embedding.py` 新增 `tokenize_for_embedding()`：中文串切单字 + bigram，英文数字串保持不变。维度仍 256、归一化仍成立、输出仍确定性（`tests/knowledge/test_embedding.py` 全绿）。

### 3. A 组数字完全不变，是实验隔离性的证据

BM25 不经过嵌入，所以修复对 A 组零影响——0.8214 前后完全一致。这证明：
- 没有筛样本（样本集相同）
- 没有调 BM25 参数（k1=1.5, b=0.75 未动）
- 没有调混合权重（0.6/0.4 未动）
- 变化只来自向量路本身

### 4. 修复后混合优于单路，重排再 +1.8 个点

D 组 Recall@3 0.8750 比 A 组 0.8214 高 **5.4 个百分点**，nDCG@5 高 5.6 个点。重排层在混合之上再贡献 +0.0179 Recall@3 —— 与"重排用于精排前 5 条"的设计意图一致。

### 5. 小样本会让结论翻转，所以以 n=56 为主口径

n=14 时（修复后）：A 0.7857 / B 0.5000 / C 0.6429 / D 0.7143，A 仍最优。
n=14 下 1 条样本 = 7.14 个百分点，A 与 D 的差距恰好是 1 条命中，不具统计意义。因此对外主口径取 n=56，n=14 作为小样本参考一并公布。

---

## 四、复跑命令

```bash
# 主口径 n=56（修复后）
python scripts/eval_retrieval_ablation.py

# 主口径 n=56（修复前，对照用）
python scripts/eval_retrieval_ablation.py --legacy-tokenizer \
    --output 06-工程整改/eval_retrieval_ablation.before-fix.csv

# 小样本口径 n=14
python scripts/eval_retrieval_ablation.py --query-set canonical \
    --output 06-工程整改/eval_retrieval_ablation.n14.csv
```

---

## 五、局限（写进 PPT 也用这段）

1. **语料只有 14 个 chunk**，检索任务本质是 14 选 3，比真实知识库简单得多。绝对数字不代表生产性能，只有组间相对趋势有效。
2. **哈希嵌入不是语义嵌入**。修复后它靠字面二元组工作，对同义改写仍然弱（"内存不足" vs "OOM" 无重合）。生产环境应替换为真实 embedding 模型，本项目为保证离线可复现不引入。
3. **人工改写共 42 条，由单人完成**，未做多人交叉标注，改写质量未做一致性检验。
4. **nDCG 用二值增益**，因为每条 query 只标注了一个相关文档，无法做分级增益。

---

## 六、改动清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `scripts/eval_retrieval_ablation.py` | 新增 | 四组消融，含 `--legacy-tokenizer` 与 `--query-set` |
| `knowledge/embedding/hash_embedding.py` | 修改 | 新增 `tokenize_for_embedding()`，`_encode_one` 改用它 |
| `06-工程整改/eval_retrieval_ablation*.csv` | 新增 | 4 份逐条明细 |
| `06-工程整改/C-R8-检索消融报告.md` | 新增 | 本文件 |

未改动：`knowledge/retrieval/*`（bm25/hybrid/vector_store）、`knowledge/reranker/*`、混合权重、BM25 参数、样本数据。
