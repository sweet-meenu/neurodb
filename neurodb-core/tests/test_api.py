import pytest
from fastapi.testclient import TestClient

from neurodb_core.app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "neurodb_data")
    with TestClient(app) as c:
        yield c


def register_and_login(client) -> str:
    resp = client.post("/api/control/auth/register", json={"email": "ada@example.com", "password": "supersecret"})
    assert resp.status_code == 201
    resp = client.post("/api/control/auth/login", json={"email": "ada@example.com", "password": "supersecret"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_login_and_get_me(client):
    token = register_and_login(client)
    resp = client.get("/api/control/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "ada@example.com"


def test_duplicate_registration_conflicts(client):
    register_and_login(client)
    resp = client.post("/api/control/auth/register", json={"email": "ada@example.com", "password": "supersecret"})
    assert resp.status_code == 409


def test_login_with_wrong_password_fails(client):
    register_and_login(client)
    resp = client.post("/api/control/auth/login", json={"email": "ada@example.com", "password": "wrongpass"})
    assert resp.status_code == 401


def test_me_requires_session_token(client):
    resp = client.get("/api/control/auth/me")
    assert resp.status_code == 401


def create_project(client, token: str) -> dict:
    resp = client.post(
        "/api/control/projects", json={"name": "my-first-db"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201
    return resp.json()


def test_create_and_list_projects(client):
    token = register_and_login(client)
    project = create_project(client, token)
    assert project["name"] == "my-first-db"
    assert project["api_key"].startswith("ndb_")
    assert project["connection_string"].startswith("neurodb://")

    resp = client.get("/api/control/projects", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) == 1
    assert "api_key" not in projects[0]  # key only ever shown once, at creation


def test_data_plane_requires_api_key(client):
    resp = client.post("/api/data/v1/objects", json={"collection": "docs", "text": "hello", "metadata": {}})
    assert resp.status_code == 401


def test_ingest_query_and_delete_roundtrip(client):
    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"]}

    resp = client.post(
        "/api/data/v1/objects",
        json={"collection": "docs", "text": "NeuroDB is a vector database for semantic search.", "metadata": {"tag": "intro"}},
        headers=headers,
    )
    assert resp.status_code == 201
    object_id = resp.json()["object_id"]

    resp = client.post(
        "/api/data/v1/ingest/text",
        data={
            "collection": "docs",
            "text": (
                "The quarterly earnings report beat market expectations. "
                "Investors were pleased with the strong revenue growth this quarter."
            ),
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["chunks_created"] >= 1

    resp = client.get("/api/data/v1/collections", headers=headers)
    assert resp.status_code == 200
    collections = {c["name"]: c for c in resp.json()}
    assert collections["docs"]["object_count"] >= 2

    resp = client.post(
        "/api/data/v1/query",
        json={"query": "SELECT * FROM docs SEMANTIC SIMILAR TO 'vector database semantic search' LIMIT 3"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy"] in ("semantic_first", "filter_first")
    assert len(body["results"]) >= 1
    assert body["results"][0]["explanation"] is not None

    resp = client.get(f"/api/data/v1/objects/{object_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["metadata"]["tag"] == "intro"

    resp = client.delete(f"/api/data/v1/objects/{object_id}", headers=headers)
    assert resp.status_code == 204
    resp = client.get(f"/api/data/v1/objects/{object_id}", headers=headers)
    assert resp.status_code == 404


def test_query_with_metadata_filter(client):
    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"]}

    for text, category in [("Cats are popular pets.", "animals"), ("Stock prices rose today.", "finance")]:
        client.post(
            "/api/data/v1/objects", json={"collection": "docs", "text": text, "metadata": {"category": category}}, headers=headers
        )

    resp = client.post(
        "/api/data/v1/query", json={"query": "SELECT * FROM docs WHERE category = 'finance'"}, headers=headers
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["metadata"]["category"] == "finance"


def test_invalid_neuroql_returns_400(client):
    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"]}
    resp = client.post("/api/data/v1/query", json={"query": "NOT VALID NEUROQL"}, headers=headers)
    assert resp.status_code == 400


def test_neuroql_lexer_error_returns_400_not_500(client):
    # A character the hand-written lexer doesn't recognize (e.g. '#') must be
    # reported as a clean 400 parse error, not escape as an unhandled 500 —
    # LexError previously wasn't caught alongside ParseError.
    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"]}
    resp = client.post("/api/data/v1/query", json={"query": "SELECT * FROM docs # oops"}, headers=headers)
    assert resp.status_code == 400
    assert "parse error" in resp.json()["detail"].lower()


def test_neuroql_query_tolerates_trailing_semicolon(client):
    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"]}
    client.post(
        "/api/data/v1/objects", json={"collection": "docs", "text": "hello world", "metadata": {}}, headers=headers
    )
    resp = client.post("/api/data/v1/query", json={"query": "SELECT * FROM docs;"}, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


def test_unhandled_exception_still_returns_cors_headers(client, monkeypatch):
    # Regression check for the missing-CORS-header-on-500 issue: Starlette's
    # default error handler sits outside CORSMiddleware, so an unhandled
    # exception would otherwise produce a response with no CORS headers at
    # all (the browser reports that as a confusing CORS failure rather than
    # the real error). The catch-all handler in app.py fixes this — verify a
    # genuine crash still comes back with Access-Control-Allow-Origin set.
    import neurodb_core.dataplane.service as service_module

    def boom(*args, **kwargs):
        raise RuntimeError("simulated unexpected crash")

    monkeypatch.setattr(service_module, "run_query", boom)

    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"], "Origin": "http://localhost:3000"}

    # TestClient re-raises server exceptions by default (useful for surfacing
    # bugs during normal test runs) — that bypasses the exception-handler path
    # a real HTTP client would hit, which is exactly what this test needs to
    # observe, so disable it here.
    no_raise_client = TestClient(client.app, raise_server_exceptions=False)
    resp = no_raise_client.post("/api/data/v1/query", json={"query": "SELECT * FROM docs"}, headers=headers)
    assert resp.status_code == 500
    assert resp.headers.get("access-control-allow-origin") is not None


def test_dashboard_can_query_project_data_via_session_without_api_key(client):
    token = register_and_login(client)
    project = create_project(client, token)
    auth_headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/control/projects/{project['id']}/data/objects",
        json={"collection": "docs", "text": "NeuroDB dashboard smoke test document.", "metadata": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp = client.get(f"/api/control/projects/{project['id']}/data/collections", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "docs"

    resp = client.post(
        f"/api/control/projects/{project['id']}/data/query",
        json={"query": "SELECT * FROM docs SEMANTIC SIMILAR TO 'dashboard test'"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


def test_dashboard_data_routes_reject_non_owner(client):
    token_a = register_and_login(client)
    project = create_project(client, token_a)

    resp = client.post("/api/control/auth/register", json={"email": "eve@example.com", "password": "supersecret"})
    assert resp.status_code == 201
    resp = client.post("/api/control/auth/login", json={"email": "eve@example.com", "password": "supersecret"})
    token_b = resp.json()["access_token"]

    resp = client.get(
        f"/api/control/projects/{project['id']}/data/collections", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404


def test_project_deletion_evicts_runtime_and_blocks_new_use(client):
    token = register_and_login(client)
    project = create_project(client, token)
    headers = {"X-NeuroDB-Api-Key": project["api_key"]}
    client.post("/api/data/v1/objects", json={"collection": "docs", "text": "temp", "metadata": {}}, headers=headers)

    resp = client.delete(f"/api/control/projects/{project['id']}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204

    resp = client.post("/api/data/v1/objects", json={"collection": "docs", "text": "temp", "metadata": {}}, headers=headers)
    assert resp.status_code == 401
