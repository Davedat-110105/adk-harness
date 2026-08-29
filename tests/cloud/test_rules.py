from __future__ import annotations

import json
from importlib.resources import files

import pytest

from adk_harness.cloud.bootstrap import CheckpointStore
from adk_harness.cloud.rules import RulesPublicationError, RulesPublisher


class FakeRequest:
    def __init__(self, result):
        self.result = result

    def execute(self, **kwargs):
        return self.result


class FakeRulesets:
    def __init__(self, state):
        self.state = state
        self.create_calls = []
        self.get_calls = []

    def create(self, *, name, body):
        self.create_calls.append((name, body))
        self.state["ruleset"] = {
            "name": "projects/demo/rulesets/r1",
            "attachmentPoint": body["attachmentPoint"],
            "source": body["source"],
        }
        return FakeRequest(self.state["ruleset"])

    def get(self, *, name):
        self.get_calls.append(name)
        return FakeRequest(self.state["ruleset"])


class FakeReleases:
    def __init__(self, state):
        self.state = state
        self.create_calls = []
        self.patch_calls = []

    def get(self, *, name):
        return FakeRequest(self.state.get("release", {}))

    def create(self, *, name, body):
        self.create_calls.append((name, body))
        self.state["release"] = {"name": body["name"], "rulesetName": body["rulesetName"]}
        return FakeRequest(self.state["release"])

    def patch(self, *, name, body):
        self.patch_calls.append((name, body))
        self.state["release"] = {"name": name, "rulesetName": body["release"]["rulesetName"]}
        return FakeRequest(self.state["release"])


class FakeService:
    def __init__(self):
        self.state = {}
        self.rulesets_api = FakeRulesets(self.state)
        self.releases_api = FakeReleases(self.state)

    def projects(self):
        return self

    def rulesets(self):
        return self.rulesets_api

    def releases(self):
        return self.releases_api


def make_publisher(tmp_path, service, source="rules_version = '2';"):
    return RulesPublisher(
        project_id="demo",
        project_number="123",
        source=source,
        credentials=object(),
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        discovery_build=lambda *args, **kwargs: service,
    )


def test_publisher_uses_named_attachment_and_verifies_source(tmp_path):
    service = FakeService()
    result = make_publisher(tmp_path, service).publish("control")

    assert result["release_name"] == "projects/demo/releases/cloud.firestore/control"
    assert service.rulesets_api.create_calls[0][1]["attachmentPoint"] == (
        "firestore.googleapis.com/projects/123/databases/control"
    )
    assert service.releases_api.create_calls[0][1]["rulesetName"] == "projects/demo/rulesets/r1"


def test_publisher_restart_reconciles_without_duplicate_ruleset(tmp_path):
    service = FakeService()
    publisher = make_publisher(tmp_path, service)
    publisher.publish("runtime")
    publisher.publish("runtime")

    assert len(service.rulesets_api.create_calls) == 1


def test_publisher_updates_existing_release_with_official_request_body(tmp_path):
    service = FakeService()
    publisher = make_publisher(tmp_path, service)
    publisher.publish("control")
    service.state["release"]["rulesetName"] = "projects/demo/rulesets/old"
    publisher.publish("control")
    assert service.releases_api.patch_calls[0][1]["release"]["rulesetName"].endswith("/r1")


def test_publisher_rejects_changed_source_checkpoint(tmp_path):
    service = FakeService()
    publisher = make_publisher(tmp_path, service)
    publisher.publish("control")

    with pytest.raises(RulesPublicationError, match="source hash"):
        make_publisher(tmp_path, service, source="changed").publish("control")


def test_publisher_rejects_source_mutation_after_approval(tmp_path):
    service = FakeService()
    publisher = make_publisher(tmp_path, service)
    publisher.approval_binding()
    publisher.source = "changed after approval"
    with pytest.raises(RulesPublicationError, match="changed after approval"):
        publisher.publish("control")
    assert service.rulesets_api.create_calls == []


def test_publisher_accepts_explicitly_approved_source_revision(tmp_path):
    service = FakeService()
    make_publisher(tmp_path, service).publish("control")
    source = "rules_version = '2'; match /databases/{database}/documents { allow read: if false; }"
    import hashlib

    revised = RulesPublisher(
        project_id="demo",
        project_number="123",
        source=source,
        credentials=object(),
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        discovery_build=lambda *args, **kwargs: service,
        approved_source_hash=hashlib.sha256(source.encode()).hexdigest(),
        source_version="phase5",
    )
    result = revised.publish("control")
    assert result["source_version"] == "phase5"
    assert CheckpointStore(tmp_path / "setup.db").get(
        "rules:control:" + result["source_hash"]
    )["status"] == "complete"


def test_publisher_requires_real_credentials_and_distinct_databases(tmp_path):
    with pytest.raises(ValueError):
        RulesPublisher(
            project_id="demo",
            project_number="123",
            source="deny",
            credentials=None,
            checkpoints=CheckpointStore(tmp_path / "none.db"),
        )
    publisher = make_publisher(tmp_path, FakeService())
    with pytest.raises(ValueError, match="distinct"):
        publisher.publish_both("control", "control")


def test_publisher_uses_real_discovery_http_request_shape(tmp_path):
    """Use the installed discovery document and fake transport, never a live API."""
    from googleapiclient.discovery import build_from_document

    class Response:
        status = 200
        reason = "OK"

    class Transport:
        def __init__(self):
            self.calls = []
            self.release_gets = 0
            self.closed = False

        def request(self, uri, method="GET", body=None, headers=None, **kwargs):
            del headers, kwargs
            self.calls.append((method, uri, body))
            if method == "GET" and "/releases/" in uri:
                self.release_gets += 1
                payload = {
                    "name": "projects/demo/releases/cloud.firestore/control",
                    "rulesetName": (
                        "projects/demo/rulesets/old"
                        if self.release_gets == 1
                        else "projects/demo/rulesets/r1"
                    ),
                }
            elif method == "GET" and "/rulesets/" in uri:
                payload = {
                    "name": uri.rsplit("/", 1)[-1],
                    "attachmentPoint": "firestore.googleapis.com/projects/123/databases/control",
                    "source": {"files": [{"name": "firestore.rules", "content": "rules"}]},
                }
            elif method == "POST" and "/rulesets" in uri:
                payload = {
                    "name": "projects/demo/rulesets/r1",
                    "attachmentPoint": "firestore.googleapis.com/projects/123/databases/control",
                    "source": {"files": [{"name": "firestore.rules", "content": "rules"}]},
                }
            else:
                payload = {}
            return Response(), json.dumps(payload).encode()

        def close(self):
            self.closed = True

    transport = Transport()
    document = (
        files("googleapiclient.discovery_cache")
        .joinpath("documents/firebaserules.v1.json")
        .read_text()
    )
    service = build_from_document(document, http=transport)
    result = RulesPublisher(
        project_id="demo",
        project_number="123",
        source="rules",
        credentials=object(),
        checkpoints=CheckpointStore(tmp_path / "setup.db"),
        discovery_build=lambda *args, **kwargs: service,
    ).publish("control")

    assert result["release_name"].endswith("/control")
    patch_calls = [call for call in transport.calls if call[0] == "PATCH"]
    assert len(patch_calls) == 1
    assert "updateMask" not in patch_calls[0][1]
    assert json.loads(patch_calls[0][2])["release"]["rulesetName"].endswith("/r1")
    assert transport.closed
