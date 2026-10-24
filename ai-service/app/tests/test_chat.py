def test_chat(client):

    response = client.post(
        "/api/chat",
        json={
            "message": "如何检查 nginx 状态？",
            "use_rag": False,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "answer" in data

    assert "conversation_id" in data

    assert data["provider"] == "mock"

    assert data["model"] == "mock-model"


def test_chat_validation(client):

    response = client.post(
        "/api/chat",
        json={
            "message": "",
        },
    )

    assert response.status_code == 422