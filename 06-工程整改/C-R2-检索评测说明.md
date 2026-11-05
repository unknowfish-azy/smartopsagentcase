# C-R2 检索评测口径

采用方案允许的原始 14 问降级口径：Recall@3=0.6429、MRR=0.4167（n=14，7 个 Linux JSONL，种子样本均为 DRAFT，仅验证链路）。

`python scripts/eval_retrieval.py` 默认仅运行原句。`--include-variants` 为补充实验：14 原句+56 条 AI 生成变体，共 70 query；有效独立样本≈14；Recall@3=0.6000、MRR=0.4262。CSV 来源分别为 dataset:canonical 和 generated:，没有人工改写来源。

没有第二个人提供的独立改写，不声明满足 human: 比例要求。此前 human:56 条的记录为错误来源标记，已更正。评测使用每条种子响应的首切片和 HashEmbedding+BM25 混合基线，既不代表大规模知识库检索，也不代表语义模型基准结果。
