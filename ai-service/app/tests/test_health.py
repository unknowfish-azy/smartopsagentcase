def test_root(client):

    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["name"] == (
        "SmartOpsAgent AI Service"
    )

    assert data["status"] == "running"


def test_health(client):

    response = client.get(
        "/api/health"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "UP"

    assert data["service"] == (
        "smartops-ai-service"
    )