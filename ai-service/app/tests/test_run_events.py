import logging

import pytest
from app.core.exceptions import LLMException
from app.schemas.chat import ChatRequest
from app.services.chat import ChatService


@pytest.mark.asyncio
async def test_sse_terminal_error_keeps_the_same_run_as_initial_event(caplog):
    caplog.set_level(logging.INFO)
    class Interrupted:
        async def generate_stream(self, *args, **kwargs):
            yield "real partial"
            raise LLMException("provider secret must not enter event")

    service = ChatService(llm_service=Interrupted())
    request = ChatRequest(message="nginx", use_rag=False, metadata={"request_id": "request-1", "task_id": "task-1", "api_key": "never-copy"})
    events = [e async for e in service.chat_stream(request)]
    initial = next(e["data"] for e in events if e["event"] == "run")
    error = next(e["data"]["run_event"] for e in events if e["event"] == "error")
    assert initial["request_id"] == error["request_id"] == "request-1"
    assert initial["run_id"] == error["run_id"]
    assert error["status"] == "failed"
    assert not any(e["event"] == "done" for e in events)
    assert "never-copy" not in str(events)
    assert "provider secret" not in str(error)
    assert "request_id=request-1" in caplog.text
    assert initial["run_id"] in caplog.text
    assert "status=failed code=LLM_STREAM_INTERRUPTED" in caplog.text
    assert "provider secret" not in caplog.text


def test_http_chat_and_sse_preserve_minimal_correlation(client, auth_headers):
    body = {"message": "hello", "use_rag": False, "metadata": {"request_id": "request-2", "task_id": "task-2"}}
    response = client.post("/api/chat", json=body, headers=auth_headers())
    assert response.status_code == 200
    event = response.json()["metadata"]["run_event"]
    assert event["request_id"] == "request-2"
    assert event["status"] == "succeeded"
    streamed = client.post("/api/chat/stream", json=body, headers=auth_headers())
    assert "event: run\n" in streamed.text
    assert '"task_id": "task-2"' in streamed.text


@pytest.mark.asyncio
async def test_rag_failure_has_a_terminal_correlated_error(caplog):
    caplog.set_level(logging.INFO)

    class BrokenRetrieval:
        async def retrieve(self, **kwargs):
            raise RuntimeError("private retrieval details")

    events = [e async for e in ChatService(rag_service=BrokenRetrieval()).chat_stream(ChatRequest(message="nginx"))]
    assert events[0]["event"] == "run"
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["run_event"]["run_id"] == events[0]["data"]["run_id"]
    assert "private retrieval" not in str(events)
    assert events[0]["data"]["run_id"] in caplog.text
    assert "status=failed" in caplog.text
    assert "private retrieval" not in caplog.text
