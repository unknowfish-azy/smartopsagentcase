"""MCP 协议层单测：编解码、消息判别、版本协商、错误码。"""

import json

import pytest

from agent.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    MCPError,
    MCPInternalError,
    MCPInvalidParams,
    MCPInvalidRequest,
    MCPMethodNotFound,
    MCPParseError,
    MCP_PROTOCOL_VERSION,
    PARSE_ERROR,
    decode_message,
    encode_message,
    is_notification,
    is_request,
    is_response,
    make_error,
    make_notification,
    make_request,
    make_result,
    negotiate_protocol_version,
)


def test_encode_message_is_single_line():
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "text": "第一行\n第二行"
        },
    }

    encoded = encode_message(message)

    assert "\n" not in encoded
    assert encoded == json.dumps(
        message,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_encode_message_rejects_nan():
    with pytest.raises(ValueError):
        encode_message({"value": float("nan")})


def test_decode_message_round_trip():
    original = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/list",
        "params": {},
    }

    assert decode_message(encode_message(original)) == original


def test_decode_message_rejects_blank_and_non_object():
    with pytest.raises(MCPParseError):
        decode_message("   ")

    with pytest.raises(MCPParseError):
        decode_message("{not json")

    with pytest.raises(MCPInvalidRequest):
        decode_message("[1, 2, 3]")


def test_message_kinds():
    request = make_request(
        message_id=1,
        method="initialize",
        params={},
    )
    notification = make_notification(
        method="notifications/initialized",
    )
    response = make_result(
        message_id=1,
        result={"ok": True},
    )

    assert is_request(request)
    assert not is_notification(request)
    assert not is_response(request)

    assert is_notification(notification)
    assert not is_request(notification)

    assert is_response(response)
    assert not is_request(response)


def test_error_codes_and_shape():
    assert PARSE_ERROR == -32700
    assert INVALID_REQUEST == -32600
    assert METHOD_NOT_FOUND == -32601
    assert INVALID_PARAMS == -32602
    assert INTERNAL_ERROR == -32603

    error = MCPMethodNotFound("没有这个方法")
    assert error.code == METHOD_NOT_FOUND

    payload = make_error(
        message_id=3,
        error=error,
    )

    assert payload["id"] == 3
    assert payload["error"]["code"] == METHOD_NOT_FOUND
    assert "没有这个方法" in payload["error"]["message"]


def test_error_data_is_optional():
    without_data = MCPInternalError("boom").to_dict()
    assert "data" not in without_data

    with_data = MCPInvalidParams(
        "bad",
        data={"field": "name"},
    ).to_dict()
    assert with_data["data"] == {"field": "name"}


def test_negotiate_supported_version_returns_same():
    version, matches = negotiate_protocol_version(
        MCP_PROTOCOL_VERSION
    )

    assert version == MCP_PROTOCOL_VERSION
    assert matches is True


def test_negotiate_unsupported_version_returns_latest():
    version, matches = negotiate_protocol_version("1999-01-01")

    assert version == MCP_PROTOCOL_VERSION
    assert matches is False


def test_negotiate_non_string_returns_latest():
    version, matches = negotiate_protocol_version(None)

    assert version == MCP_PROTOCOL_VERSION
    assert matches is False


def test_error_hierarchy_is_mcp_error():
    for exc in (
        MCPParseError,
        MCPInvalidRequest,
        MCPMethodNotFound,
        MCPInvalidParams,
        MCPInternalError,
    ):
        assert issubclass(exc, MCPError)
