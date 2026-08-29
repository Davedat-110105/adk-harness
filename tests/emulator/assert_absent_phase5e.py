"""Verify rejected Rules batches did not leave control documents behind."""

from __future__ import annotations

import os
import sys

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore


def main() -> int:
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    project = os.environ.get("FIRESTORE_PROJECT", "demo-adk-wire")
    if not (emulator.startswith("127.0.0.1:") or emulator.startswith("localhost:")):
        raise SystemExit("FIRESTORE_EMULATOR_HOST must be loopback")
    if not project.startswith("demo-"):
        raise SystemExit("absence check requires a demo project")
    client = firestore.Client(
        project=project, database="control", credentials=AnonymousCredentials()
    )
    try:
        present = [path for path in sys.argv[1:] if client.document(path).get().exists]
        if present:
            print("unexpected documents: " + ", ".join(present))
            return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
