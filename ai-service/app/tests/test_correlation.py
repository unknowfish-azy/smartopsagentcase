"""Cross-layer correlation contract: headers, SSE events and log lines."""

import json
import logging

import pytest


def _first_event(text, name):
    for block in text.split("\n\n"):
        lines = block.splitlines()
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
        data = next((line[5:].strip() for line in lines if line.startswith("data:")), None)
        if event == name and data:
            return json.loads(data)
    return None


def test_chat_echoes_headers_and_logs_ids_without_prompt(client, caplog):
    caplog.set_level(logging.INFO)
    secret_prompt = "private-prompt-must-not-be-logged"
    body = {
        "message": secret_prompt,
        "use_rag": False,
        "metadata": {
            "request_id": "req-log-1",
            "task_id": "task-log-1",
            "api_key": "never-copy",
        },
    }
    response = client.post(
        "/api/chat",
        json=body,
        headers={"X-Request-ID": "req-log-1", "X-Task-ID": "task-log-1"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-log-1"
    assert response.headers["X-Task-ID"] == "task-log-1"
    run_id = response.headers["X-Run-ID"]
    event = response.json()["metadata"]["run_event"]
    assert event["request_id"] == "req-log-1"
    assert event["task_id"] == "task-log-1"
    assert event["run_id"] == run_id

    assert "chat.start request_id=req-log-1 task_id=task-log-1" in caplog.text
    assert f"run_id={run_id}" in caplog.text
    assert "status=succeeded" in caplog.text
    assert secret_prompt not in caplog.text
    assert "never-copy" not in caplog.text


def test_header_only_correlation_is_used(client):
    response = client.post(
        "/api/chat",
        json={"message": "hello", "use_rag": False},
        headers={
            "X-Request-ID": "req-header-1",
            "X-Task-ID": "task-header-1",
            "X-Run-ID": "run-header-1",
        },
    )

    assert response.status_code == 200
    event = response.json()["metadata"]["run_event"]
    assert event["request_id"] == "req-header-1"
    assert event["task_id"] == "task-header-1"
    assert event["run_id"] == "run-header-1"
    assert response.headers["X-Run-ID"] == "run-header-1"


def test_stream_uses_the_same_run_id_in_header_and_events(client):
    response = client.post(
        "/api/chat/stream",
        json={
            "message": "hello",
            "use_rag": False,
            "metadata": {"request_id": "req-stream-1", "task_id": "task-stream-1"},
        },
        headers={"X-Request-ID": "req-stream-1", "X-Task-ID": "task-stream-1"},
    )

    assert response.status_code == 200
    run_id = response.headers["X-Run-ID"]
    run = _first_event(response.text, "run")
    done = _first_event(response.text, "done")
    assert run["run_id"] == run_id
    assert run["request_id"] == "req-stream-1"
    assert done["metadata"]["run_event"]["run_id"] == run_id
    assert done["metadata"]["run_event"]["status"] == "succeeded"


@pytest.mark.parametrize(
    "header",
    [
        "bad id with spaces",
        "x" * 120,
        "",
    ],
)
def test_invalid_correlation_ids_are_replaced(client, header):
    response = client.post(
        "/api/chat",
        json={"message": "hello", "use_rag": False},
        headers={"X-Request-ID": header},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != header
    assert " " not in response.headers["X-Request-ID"]
