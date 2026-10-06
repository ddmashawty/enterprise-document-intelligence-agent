from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from doc_agent import __version__
from doc_agent.api import create_app
from doc_agent.api.routes_kaoyan import kaoyan_query
from doc_agent.kaoyan.db import KaoyanStore
from doc_agent.kaoyan.query import KaoyanQuery


@pytest.fixture()
def client(kaoyan_store: KaoyanStore) -> TestClient:
    app = create_app()
    app.dependency_overrides[kaoyan_query] = lambda: KaoyanQuery(kaoyan_store)
    return TestClient(app)


def _error(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    body = r.json()
    assert body["error"]["code"] == code and body["error"]["message"]
    return body


def test_app_version_and_health() -> None:
    app = create_app()
    assert app.version == __version__ == "0.4.0"
    data = TestClient(app).get("/health").json()
    assert data["status"] == "ok" and data["version"] == "0.4.0"
    for key in ("kaoyan_db", "programs", "documents"):
        assert key in data


def test_programs_filter(client: TestClient) -> None:
    r = client.get("/v1/programs", params={"is_408": "true", "study_mode": "全日制", "min_public_plan": 21})
    assert r.status_code == 200
    data = r.json()
    ids = {p["program_id"] for p in data["programs"]}
    assert "sysu-670-085404" in ids and "scut-cs-085404" in {p["program_id"] for p in data["unknown"]}
    assert data["programs"][0]["plans"] and data["public_plan_rule"]


def test_program_detail_and_404(client: TestClient) -> None:
    r = client.get("/v1/programs/sysu-670-085404")
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == "085404" and any(ln["total"] == 379 for ln in data["score_lines"])
    assert all(p["source"]["doc_id"] for p in data["plans"])
    _error(client.get("/v1/programs/nope"), 404, "program_not_found")


def test_score_lines(client: TestClient) -> None:
    r = client.get("/v1/score-lines", params={"school": "华工", "code": "085404"})
    assert r.status_code == 200
    (p,) = r.json()["programs"]
    assert p["lines"][0]["scope"] == "school_baseline" and p["lines"][0]["total"] == 305


def test_score_lines_requires_school(client: TestClient) -> None:
    body = _error(client.get("/v1/score-lines", params={"code": "085404"}), 422, "validation_error")
    assert body["error"]["details"]
    _error(client.get("/v1/score-lines", params={"school": "北大"}), 404, "school_not_found")
    _error(client.get("/v1/score-lines", params={"school": "sysu", "year": 1800}), 422, "validation_error")


def test_documents(client: TestClient) -> None:
    r = client.get("/v1/documents", params={"school": "jnu", "doc_type": "retest_rules"})
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert docs and all(d["school"] == "jnu" and d["content_available"] is False for d in docs)
    personal = client.get("/v1/documents/jnu-005").json()
    assert personal["contains_personal_data"] is True and personal["content_available"] is False
    assert "local_path" not in personal and "fact_counts" in personal
    _error(client.get("/v1/documents/nope"), 404, "document_not_found")


def test_kaoyan_db_missing_is_503(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    import doc_agent.api.routes_kaoyan as rk

    monkeypatch.setattr(rk, "get_settings", lambda: SimpleNamespace(kaoyan_db_path=tmp_path / "missing.db"))
    _error(TestClient(create_app()).get("/v1/programs"), 503, "kaoyan_db_missing")
    assert not (tmp_path / "missing.db").exists()
