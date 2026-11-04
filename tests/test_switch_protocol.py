"""
Tests for Switch Protocol Server, Role Leasing & Room Documents
"""

import pytest
from starlette.testclient import TestClient
from core.switch_server import app, store


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_assume_and_release_exclusive_role(client):
    agent_id = "test-agent-alpha"
    room_id = "test-room-101"

    # Assume role
    res = client.post(
        f"/agents/{agent_id}/ops/assume_role",
        json={"room_id": room_id, "role_name": "triage-commander", "exclusive": True}
    )
    assert res.status_code == 200
    assert res.json()["role"] == "triage-commander"

    # Secondary agent attempting to assume exclusive role should be rejected (409 Conflict)
    res_conflict = client.post(
        "/agents/test-agent-beta/ops/assume_role",
        json={"room_id": room_id, "role_name": "triage-commander", "exclusive": True}
    )
    assert res_conflict.status_code == 409

    # Release role
    res_release = client.post(
        f"/agents/{agent_id}/ops/release_role",
        json={"room_id": room_id, "role_name": "triage-commander"}
    )
    assert res_release.status_code == 200
    assert res_release.json()["released"] is True


def test_room_document_lifecycle(client):
    agent_id = "test-agent-alpha"
    room_id = "test-room-docs"
    doc_name = "incident-postmortem.md"

    # Create Room Document
    res_create = client.post(
        f"/agents/{agent_id}/ops/create_room_document",
        json={"room_id": room_id, "name": doc_name, "content": "# Post-Mortem Draft"}
    )
    assert res_create.status_code == 200
    assert res_create.json()["version"] == 1

    # Read Room Document
    res_get = client.get(f"/agents/{agent_id}/ops/get_room_document?room_id={room_id}&name={doc_name}")
    assert res_get.status_code == 200
    assert res_get.json()["content"] == "# Post-Mortem Draft"

    # Mutate Room Document
    res_update = client.post(
        f"/agents/{agent_id}/ops/update_room_document",
        json={"room_id": room_id, "name": doc_name, "content": "# Post-Mortem Resolved (v2)"}
    )
    assert res_update.status_code == 200
    assert res_update.json()["version"] == 2

