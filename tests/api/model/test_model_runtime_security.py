from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_runtime_response_dto_contains_no_secret_fields():
    source = (
        ROOT
        / "backend/src/main/java/com/smartops/dto/model/RuntimeModelConnectionResponse.java"
    ).read_text(encoding="utf-8")

    assert "apiKeyCiphertext" not in source
    assert "apiKeyPlaintext" not in source
    assert "decryptedKey" not in source
    assert "keyLast4" in source


def test_runtime_route_uses_internal_token_filter():
    source = (
        ROOT
        / "backend/src/main/java/com/smartops/security/InternalTokenAuthenticationFilter.java"
    ).read_text(encoding="utf-8")

    assert "X-SmartOps-Internal-Token" in source
    assert "SC_UNAUTHORIZED" in source
    assert "SC_FORBIDDEN" in source
    assert "MessageDigest.isEqual" in source
