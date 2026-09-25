from __future__ import annotations

import json

import httpx

from frontend.api_client import ApiError, DocAgentClient


def test_api_error_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"code": "llm_not_configured", "message": "LLM_API_KEY missing"}},
        )

    client = DocAgentClient("http://example.test", transport=httpx.MockTransport(handler))
    try:
        client.health()
    except ApiError as exc:
        assert exc.status_code == 503
        assert exc.code == "llm_not_configured"
        assert "LLM_API_KEY" in exc.message
    else:
        raise AssertionError("expected ApiError")


def test_health_rejects_foreign_service():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    client = DocAgentClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
    try:
        client.health()
    except ApiError as exc:
        assert exc.code == "wrong_service"
        assert "不是文档 Agent" in exc.message
    else:
        raise AssertionError("expected ApiError")


def test_not_found_detail_is_wrong_service():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    client = DocAgentClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler))
    try:
        client.chat("你好")
    except ApiError as exc:
        assert exc.code == "wrong_service"
        assert "别的服务" in exc.message
    else:
        raise AssertionError("expected ApiError")


def test_chat_body_includes_options():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = request.read().decode()
        return httpx.Response(200, json={"answer": "ok", "session_id": "s1"})

    client = DocAgentClient("http://example.test", transport=httpx.MockTransport(handler))
    client.chat("hi", "s1", max_tool_calls=3)
    body = json.loads(seen["json"])
    assert body["message"] == "hi"
    assert body["session_id"] == "s1"
    assert body["options"]["max_tool_calls"] == 3
