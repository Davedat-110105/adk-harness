"""Production container entrypoints for the receiver service and worker job."""

from __future__ import annotations

import json
from typing import Any

from .handler import firestore_event
from .worker import worker_entry


def receiver_entrypoint(request: Any) -> Any:
    """Functions Framework HTTP/CloudEvent target for Eventarc delivery."""
    return firestore_event(request)


def worker_main() -> int:
    """Cloud Run Job process target; task identity comes from environment."""
    result = worker_entry()
    print(json.dumps({"status": result.status, "task_id": result.task_id, "reason": result.reason}))
    return 0 if result.status in {"completed", "planned", "claimed", "running"} else 1


if __name__ == "__main__":
    raise SystemExit(worker_main())


__all__ = ["receiver_entrypoint", "worker_main"]
