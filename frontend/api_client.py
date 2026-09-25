from __future__ import annotations

from typing import Any

import httpx


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{status_code} {code}: {message}")


def is_doc_agent_health(payload: dict[str, Any]) -> bool:
    return "version" in payload and "llm" in payload and "retrieval_backend" in payload


def _error_from_response(response: httpx.Response) -> ApiError:
    code = "http_error"
    message = response.text[:500] or response.reason_phrase
    details = None
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code = str(err.get("code") or code)
            message = str(err.get("message") or message)
            details = err.get("details")
        elif body.get("detail") == "Not Found":
            code = "wrong_service"
            message = "这个地址没有文档 Agent 的接口。侧栏 API 指向了别的服务。"
            details = body
    return ApiError(response.status_code, code, message, details)


class DocAgentClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(transport=self._transport, timeout=timeout or self.timeout) as client:
                response = client.request(method, url, json=json, params=params)
        except httpx.HTTPError as exc:
            raise ApiError(0, "connection_error", str(exc)) from exc
        if response.status_code >= 400:
            raise _error_from_response(response)
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    def health(self) -> dict[str, Any]:
        data = self._request("GET", "/health", timeout=10)
        if not is_doc_agent_health(data):
            raise ApiError(
                200,
                "wrong_service",
                f"{self.base_url} 不是文档 Agent：/health 没有 version、llm、retrieval_backend。",
                data,
            )
        return data

    def chat(
        self,
        message: str,
        session_id: str | None = None,
        *,
        max_tool_calls: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/chat",
            json=_chat_body(message, session_id, max_tool_calls),
        )

    def chat_async(
        self,
        message: str,
        session_id: str | None = None,
        *,
        max_tool_calls: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/chat/async",
            json=_chat_body(message, session_id, max_tool_calls),
            timeout=30,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/tasks/{task_id}", timeout=15)

    def list_tasks(self, session_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if session_id:
            params["session_id"] = session_id
        return self._request("GET", "/v1/tasks", params=params, timeout=15)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/sessions/{session_id}", timeout=15)

    def ingest(self, paths: list[str], *, reindex: bool = False) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/ingest",
            json={"paths": paths, "reindex": reindex},
            timeout=300,
        )


def _chat_body(
    message: str,
    session_id: str | None,
    max_tool_calls: int | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"message": message}
    if session_id:
        body["session_id"] = session_id
    if max_tool_calls is not None:
        body["options"] = {"max_tool_calls": max_tool_calls}
    return body
