"""Lab 11 — SDLC / API contract: schemas, validation, honest error responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_project_crud_roundtrip(client):
    created = client.post(
        "/api/projects",
        json={"name": "API project", "topic": "Retrieval-augmented generation", "domain": "computer_science"},
    )
    assert created.status_code == 200
    project = created.json()
    assert project["paper_count"] == 0

    listed = client.get("/api/projects")
    assert any(p["id"] == project["id"] for p in listed.json())

    fetched = client.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200 and fetched.json()["topic"] == "Retrieval-augmented generation"

    patched = client.patch(f"/api/projects/{project['id']}", json={"name": "Renamed"})
    assert patched.json()["name"] == "Renamed"

    assert client.delete(f"/api/projects/{project['id']}").status_code == 200
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_validation_errors_are_structured(client):
    bad = client.post("/api/projects", json={"name": "", "topic": "x"})
    assert bad.status_code == 422
    assert bad.json()["error"] == "validation_error"

    project = client.post(
        "/api/projects", json={"name": "Run config test", "topic": "Federated learning"}
    ).json()
    bad_run = client.post(f"/api/projects/{project['id']}/runs", json={"result_limit": 999})
    assert bad_run.status_code == 422


def test_unknown_resources_return_404(client):
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/projects/nope/papers").status_code == 404


def test_empty_states_are_explicit_not_faked(client):
    project = client.post(
        "/api/projects", json={"name": "Empty state", "topic": "Graph neural networks"}
    ).json()
    papers = client.get(f"/api/projects/{project['id']}/papers").json()
    assert papers["count"] == 0 and papers["papers"] == []
    draft = client.get(f"/api/projects/{project['id']}/draft").json()
    assert draft == {"exists": False, "draft": None}
    gaps = client.get(f"/api/projects/{project['id']}/gaps").json()
    assert gaps["count"] == 0


def test_openapi_and_lab_map_available(client):
    spec = client.get("/openapi.json").json()
    assert "/api/projects" in spec["paths"]
    labs = client.get("/api/labs").json()["labs"]
    assert len(labs) == 14
    assert {l["lab"] for l in labs} == set(range(1, 15))
    assert all(l["files"] for l in labs)


def test_tools_endpoint_exposes_validated_schemas(client):
    tools = client.get("/api/system/tools").json()
    assert tools["registered"] >= 14
    names = {t["name"] for t in tools["registry"]}
    assert {"search_openalex", "save_research_results", "find_collaborators"} <= names
    sample = next(t for t in tools["registry"] if t["name"] == "search_openalex")
    assert sample["description"] and sample["input_schema"]["properties"]["query"]
