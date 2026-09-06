from __future__ import annotations

from fastapi.testclient import TestClient

from doc_agent.api import create_app


def test_health_ok():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "memory_db" in data


def test_chat_empty_or_llm_missing_error_shape():
    client = TestClient(create_app())
    r = client.post("/v1/chat", json={"message": "   "})
    # empty message checked before or after LLM depending on order; both must be error envelope
    assert r.status_code in {400, 503}
    body = r.json()
    assert "error" in body
    assert "code" in body["error"]


def test_task_not_found_error_shape():
    client = TestClient(create_app())
    r = client.get("/v1/tasks/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "task_not_found"


def test_validation_error_shape():
    client = TestClient(create_app())
    r = client.post("/v1/chat", content="{bad", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
