from __future__ import annotations

from dataclasses import dataclass

import pytest

from adk_harness.cloud.projects import (
    AccessDenied,
    ProjectLookup,
    ProjectManager,
    ProjectNotFound,
    ProjectOperationTimeout,
    TransientProjectError,
)


@dataclass
class FakeProject:
    project_id: str = "demo-project"
    name: str = "projects/123"
    parent: str = "folders/42"


class NotFoundError(Exception):
    code = 404


class PermissionError(Exception):
    code = 403


class RetryableError(Exception):
    code = 503


class FakeProjectsClient:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get_project(self, *, name: str, timeout: float):
        self.calls.append({"method": "get", "name": name, "timeout": timeout})
        if self.error:
            raise self.error
        return FakeProject()


def test_lookup_returns_project_and_uses_resource_name() -> None:
    client = FakeProjectsClient()
    manager = ProjectManager(client, rpc_timeout=3)

    result = manager.lookup("demo-project")

    assert result == ProjectLookup.found(FakeProject())
    assert client.calls == [{"method": "get", "name": "projects/demo-project", "timeout": 3}]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (NotFoundError(), ProjectNotFound),
        (PermissionError(), AccessDenied),
        (RetryableError(), TransientProjectError),
    ],
)
def test_lookup_classifies_missing_denied_and_transient_errors(
    error: Exception, expected: type[Exception]
) -> None:
    with pytest.raises(expected):
        ProjectManager(FakeProjectsClient(error)).lookup("demo-project")


def test_project_id_validation_rejects_resource_names() -> None:
    with pytest.raises(ValueError, match="project ID"):
        ProjectManager(FakeProjectsClient()).lookup("projects/demo-project")


def test_operation_timeout_is_bounded_and_fail_closed() -> None:
    class TimeoutOperation:
        def result(self, *, timeout: float):
            assert timeout <= 600
            raise TimeoutError

    with pytest.raises(ProjectOperationTimeout):
        ProjectManager(FakeProjectsClient(), operation_timeout=1).wait(TimeoutOperation())


def test_resume_uses_public_operations_client_and_real_lro_proto() -> None:
    from google.longrunning import operations_pb2

    class Operations:
        def get_operation(self, *, name, timeout):
            assert name == "operations/create-1"
            return operations_pb2.Operation(name=name, done=False)

        def cancel_operation(self, name, metadata=None):
            return None

    class Transport:
        operations_client = Operations()

    class Client(FakeProjectsClient):
        transport = Transport()

    operation = ProjectManager(Client()).resume("operations/create-1")
    assert operation.operation.name == "operations/create-1"
