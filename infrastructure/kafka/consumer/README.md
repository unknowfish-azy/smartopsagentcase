# Kafka Consumer

Consumer建议：

1. 使用明确consumer group。
2. 做幂等处理。
3. 对不可重试错误进入死信主题/人工处理流程。
4. 不在Consumer中直接执行高风险运维命令。