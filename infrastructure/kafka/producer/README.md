# Kafka Producer

Producer建议统一发送JSON事件，至少包含：

```json
{
  "event_id": "uuid",
  "event_type": "agent.task.created",
  "occurred_at": "2026-09-14T00:00:00Z",
  "request_id": "request-id",
  "payload": {}
}