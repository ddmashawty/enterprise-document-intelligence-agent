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


def _recording_client(payload: dict) -> tuple[DocAgentClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    return DocAgentClient("http://example.test", transport=httpx.MockTransport(handler)), seen


def test_list_programs_drops_empty_filters():
    client, seen = _recording_client({"count": 0, "programs": []})
    client.list_programs(school="sysu", code="", is_408=True, min_public_plan=20, year=None, study_mode="全日制")
    (req,) = seen
    assert req.method == "GET" and req.url.path == "/v1/programs"
    assert dict(req.url.params) == {"school": "sysu", "is_408": "true", "min_public_plan": "20", "study_mode": "全日制"}


def test_program_score_lines_documents_paths():
    client, seen = _recording_client({"count": 0})
    client.get_program("sysu-670-085404")
    client.score_lines("scnu", code="085404")
    client.list_documents(school="jnu", doc_type="catalog", year=2027)
    assert [r.url.path for r in seen] == ["/v1/programs/sysu-670-085404", "/v1/score-lines", "/v1/documents"]
    assert dict(seen[1].url.params) == {"school": "scnu", "code": "085404", "year": "2026"}
    assert dict(seen[2].url.params) == {"school": "jnu", "doc_type": "catalog", "year": "2027"}


def test_program_not_found_envelope():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "program_not_found", "message": "专业不存在: x"}})

    client = DocAgentClient("http://example.test", transport=httpx.MockTransport(handler))
    try:
        client.get_program("x")
    except ApiError as exc:
        assert exc.status_code == 404 and exc.code == "program_not_found"
    else:
        raise AssertionError("expected ApiError")
